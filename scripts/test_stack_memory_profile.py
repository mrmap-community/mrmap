"""Offline checks for scripts/stack_memory_profile (#1613).

Every docker call is stubbed and every cgroup file is a temp file: the
suite answers without a stack, without docker and without the network,
like the rest of the scripts/ tooling. What it pins is the reading math -
percentiles, the committed split of #1054, the cgroup path of a pid, the
phase report shape - and the report command's table.
"""

import importlib.machinery
import importlib.util
import io
import json
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_loader(
    "stack_memory_profile",
    importlib.machinery.SourceFileLoader(
        "stack_memory_profile", str(ROOT / "scripts" / "stack_memory_profile")))
profile = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(profile)


def make_cgroup(root, path, current=None, peak=None, limit=None,
                stat=None, events=None, cpu=None, procs=None):
    directory = Path(root) / path.lstrip("/")
    directory.mkdir(parents=True, exist_ok=True)
    if current is not None:
        (directory / "memory.current").write_text(f"{current}\n")
    if peak is not None:
        (directory / "memory.peak").write_text(f"{peak}\n")
    if limit is not None:
        (directory / "memory.max").write_text(f"{limit}\n")
    if stat is not None:
        (directory / "memory.stat").write_text(stat)
    if events is not None:
        (directory / "memory.events").write_text(events)
    if cpu is not None:
        (directory / "cpu.stat").write_text(cpu)
    if procs is not None:
        (directory / "cgroup.procs").write_text("".join(f"{p}\n" for p in procs))
    return directory


def make_proc(root, pid, comm, vmrss=None, anon=None, file_=None, shmem=None,
              pss=None):
    """A /proc/<pid> with the two files the process view reads."""
    process = Path(root) / str(pid)
    process.mkdir(parents=True, exist_ok=True)
    (process / "stat").write_text(f"{pid} ({comm}) S 1 1 0 0 -1 4194560 100 0\n")
    lines = []
    if vmrss is not None:
        lines.append(f"VmRSS:\t{vmrss} kB")
    if anon is not None:
        lines.append(f"RssAnon:\t{anon} kB")
    if file_ is not None:
        lines.append(f"RssFile:\t{file_} kB")
    if shmem is not None:
        lines.append(f"RssShmem:\t{shmem} kB")
    (process / "status").write_text(f"Name:\t{comm}\n" + "".join(l + "\n" for l in lines))
    if pss is not None:
        (process / "smaps_rollup").write_text(f"Pss:\t{pss} kB\n")
    return process


class ProcessViewTests(unittest.TestCase):
    """The /proc side of a sample: which process, how much of it is shared."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cgroup_root = self.root / "cgroup"
        self.proc_root = self.root / "proc"
        # a postgres container: the postmaster plus two backends, and a
        # child cgroup, because that is how a nested cgroup shows up
        make_cgroup(self.cgroup_root, "/docker/pg", procs=[11])
        make_cgroup(self.cgroup_root, "/docker/pg/system.slice", procs=[12, 13])
        make_proc(self.proc_root, 11, "postgres", vmrss=27440, anon=1980,
                  file_=12020, shmem=13440, pss=15000)
        make_proc(self.proc_root, 12, "postgres", vmrss=30552, anon=2256,
                  file_=2952, shmem=25344, pss=17500)
        make_proc(self.proc_root, 13, "postgres", vmrss=10656, anon=2000,
                  file_=3000, shmem=5000, pss=9000)

    def test_the_cgroup_lists_its_own_and_its_childrens_processes(self):
        self.assertEqual({11, 12, 13},
                         set(profile.procs_of_cgroup("/docker/pg",
                                                     cgroup_root=str(self.cgroup_root))))

    def test_status_gives_rss_and_the_shared_part_in_bytes(self):
        status = profile.read_proc_status(12, proc_root=str(self.proc_root))
        self.assertEqual(30552 * 1024, status["VmRSS"])
        self.assertEqual(25344 * 1024, status["RssShmem"])

    def test_a_dead_process_is_none(self):
        self.assertIsNone(profile.read_proc_status(999999,
                                                   proc_root=str(self.proc_root)))

    def test_comm_survives_spaces_and_parentheses_in_its_name(self):
        process = self.proc_root / "77"
        process.mkdir()
        (process / "stat").write_text("77 (celery worker (F)) S 1 1 0 0 -1\n")
        self.assertEqual("celery worker (F)",
                         profile.read_proc_comm(77, proc_root=str(self.proc_root)))

    def test_processes_are_aggregated_by_command_name(self):
        by_comm = profile.sample_processes("/docker/pg",
                                           cgroup_root=str(self.cgroup_root),
                                           proc_root=str(self.proc_root))
        self.assertEqual(["postgres"], list(by_comm))
        row = by_comm["postgres"]
        self.assertEqual(3, row["processes"])
        self.assertEqual(30552 * 1024, row["vmrss_peak"])
        # the shared segment of all three backends, which is the number the
        # cgroup charge cannot answer on its own
        self.assertEqual((13440 + 25344 + 5000) * 1024, row["shmem"])

    def test_pss_is_summed_only_when_every_process_is_readable(self):
        complete = profile.sample_processes(
            "/docker/pg", cgroup_root=str(self.cgroup_root),
            proc_root=str(self.proc_root), include_pss=True)
        self.assertEqual((15000 + 17500 + 9000) * 1024,
                         complete["postgres"]["pss"])
        self.assertEqual(3, complete["postgres"]["pss_readable"])

        (self.proc_root / "13" / "smaps_rollup").unlink()
        partial = profile.sample_processes(
            "/docker/pg", cgroup_root=str(self.cgroup_root),
            proc_root=str(self.proc_root), include_pss=True)
        self.assertIsNone(partial["postgres"]["pss"])
        self.assertEqual(2, partial["postgres"]["pss_readable"])

    def test_the_phase_keeps_the_peak_of_each_command(self):
        sampler = profile.Sampler("proj", "p", interval=1,
                                  cgroup_root=str(self.cgroup_root),
                                  proc_root=str(self.proc_root))
        sampler.merge_procs("pg", {"postgres": {"processes": 3, "vmrss_peak": 10,
                                                "anon": 1, "file": 2, "shmem": 3}})
        sampler.merge_procs("pg", {"postgres": {"processes": 2, "vmrss_peak": 40,
                                                "anon": 9, "file": 1, "shmem": 1}})
        kept = sampler.procs["pg"]["postgres"]
        self.assertEqual((3, 40, 9, 2, 3),
                         (kept["processes"], kept["vmrss_peak"], kept["anon"],
                          kept["file"], kept["shmem"]))

    def test_the_phase_keeps_complete_pss_peaks_and_readability(self):
        sampler = profile.Sampler("proj", "p", interval=1,
                                  cgroup_root="/missing",
                                  proc_root="/missing", include_pss=True)
        sampler.merge_procs("pg", {"postgres": {
            "processes": 3, "vmrss_peak": 10, "anon": 1, "file": 2,
            "shmem": 3, "pss": 30, "pss_readable": 3}})
        sampler.merge_procs("pg", {"postgres": {
            "processes": 3, "vmrss_peak": 9, "anon": 1, "file": 2,
            "shmem": 3, "pss": None, "pss_readable": 2}})
        row = sampler.procs["pg"]["postgres"]
        self.assertEqual((30, 3, 1),
                         (row["pss_peak"], row["pss_readable_peak"],
                          row["pss_complete_samples"]))


class MathTests(unittest.TestCase):

    def test_percentile_picks_the_sorted_element(self):
        self.assertEqual(20, profile.percentile([30, 10, 20], 0.5))
        self.assertEqual(30, profile.percentile([30, 10, 20], 1.0))
        self.assertEqual(7, profile.percentile([7], 0.0))
        self.assertIsNone(profile.percentile([], 0.5))

    def test_kv_parsing_keeps_the_numbers_and_drops_the_noise(self):
        stat = profile.parse_kv(
            "anon 100\nfile 200\nslab_reclaimable 30\n\nbroken line here\n"
            "sock not_a_number\n")
        self.assertEqual({"anon": 100, "file": 200, "slab_reclaimable": 30}, stat)

    def test_committed_is_the_unreclaimable_part(self):
        stat = {"anon": 100, "file": 500, "sock": 5, "kernel_stack": 7,
                "slab_reclaimable": 999, "slab_unreclaimable": 11}
        self.assertEqual(123, profile.committed_bytes(stat))


class PathTests(unittest.TestCase):

    def test_cgroup_path_of_reads_the_unified_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = Path(tmp) / "proc" / "42"
            proc.mkdir(parents=True)
            (proc / "cgroup").write_text(
                "1:pids:/kubepods/p42/abc\n0::/docker/abc\n")
            self.assertEqual("/docker/abc",
                             profile.cgroup_path_of(42, proc_root=str(Path(tmp) / "proc")))

    def test_a_gone_process_is_none_not_a_guess(self):
        self.assertIsNone(profile.cgroup_path_of(999999, proc_root="/nonexistent-proc"))


class ReadTests(unittest.TestCase):

    def test_read_cgroup_reads_the_files_a_phase_needs(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_cgroup(tmp, "/docker/abc", current=1234, peak=9999,
                        limit=1 << 30,
                        stat="anon 100\nfile 200\nslab_unreclaimable 11\n",
                        events="low 0\noom 2\noom_kill 1\n")
            reading = profile.read_cgroup("/docker/abc", cgroup_root=tmp)
            self.assertEqual(1234, reading["current"])
            self.assertEqual(9999, reading["peak_file"])
            self.assertEqual(1 << 30, reading["limit"])
            self.assertEqual(100, reading["stat"]["anon"])
            self.assertEqual(2, reading["events"]["oom"])

    def test_an_absent_cgroup_is_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(profile.read_cgroup("/docker/gone", cgroup_root=tmp))


class SamplerTests(unittest.TestCase):
    """A full phase over two fake containers whose files do not move."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.cgroup_root = root / "cgroup"
        self.proc_root = root / "proc"
        make_cgroup(self.cgroup_root, "/docker/one", current=100, peak=180,
                    limit=1 << 30,
                    stat="anon 60\nfile 30\nslab_unreclaimable 10\n",
                    events="oom 1\noom_kill 0\n",
                    cpu="usage_usec 4000000\nnr_throttled 0\nthrottled_usec 0\n",
                    procs=[11])
        make_cgroup(self.cgroup_root, "/docker/two", current=50, peak=None,
                    stat="anon 20\nfile 25\n",
                    events="oom 0\noom_kill 0\n",
                    cpu="usage_usec 2000000\n",
                    procs=[22])
        make_proc(self.proc_root, 11, "gunicorn", vmrss=40000, anon=30000,
                  file_=9000, shmem=1000, pss=32000)
        make_proc(self.proc_root, 22, "redis-server", vmrss=10000, anon=9000,
                  file_=1000, shmem=0, pss=9500)
        for pid, path in (("11", "/docker/one"), ("22", "/docker/two")):
            (self.proc_root / pid).mkdir(parents=True, exist_ok=True)
            (self.proc_root / pid / "cgroup").write_text(f"0::{path}\n")
        make_cgroup(self.cgroup_root, "/init.scope", current=5000,
                    limit=1 << 34, stat="anon 4000\nfile 900\n",
                    events="oom 0\noom_kill 0\n")

        # docker ps / inspect stubbed: the same two containers every time
        ps = subprocess.CompletedProcess([], 0, "aaa\nbbb\n", "")
        inspect_one = subprocess.CompletedProcess([], 0, "/one\t11\n", "")
        inspect_two = subprocess.CompletedProcess([], 0, "/two\t22\n", "")

        def fake_docker(args, timeout=10):
            if args[0] == "ps":
                return ps
            if args[0] == "inspect":
                return inspect_one if args[0:] and "aaa" in args else inspect_two
            return subprocess.CompletedProcess([], 1, "", "unsupported")
        self.patches = {
            "run_docker": profile.run_docker,
            "self_cgroup_path": profile.self_cgroup_path,
        }
        profile.run_docker = fake_docker
        profile.self_cgroup_path = lambda proc_root=None: "/init.scope"
        self.addCleanup(lambda: [setattr(profile, k, v) for k, v in self.patches.items()])

    def sample_and_report(self):
        sampler = profile.Sampler("proj", "phase-x", interval=0.01,
                                  cgroup_root=str(self.cgroup_root),
                                  proc_root=str(self.proc_root))
        return sampler.run(duration=0.05)

    def test_every_container_of_the_project_is_measured(self):
        report = self.sample_and_report()
        self.assertEqual(["one", "two"],
                         sorted(report["containers"].keys()))
        one = report["containers"]["one"]
        self.assertEqual("/docker/one", one["cgroup"])
        self.assertEqual(100, one["current_p50"])
        self.assertEqual(100, one["current_peak"])
        self.assertEqual(180, one["peak_file"])
        self.assertEqual(70, one["committed_p50"])
        self.assertIsNone(report["containers"]["two"]["peak_file"])

    def test_the_totals_and_the_sampler_cgroup_come_with_the_phase(self):
        report = self.sample_and_report()
        self.assertEqual(150, report["stack_sum_current_p50"])
        self.assertEqual(150, report["stack_sum_current_peak"])
        self.assertEqual(5000, report["sampler_cgroup"]["current_p50"])
        self.assertEqual(1 << 34, report["sampler_cgroup"]["limit"])
        self.assertEqual(0, report["sampler_cgroup"]["oom_delta"])
        self.assertEqual("/init.scope", report["sampler_cgroup"]["cgroup"])

    def test_the_environment_names_the_tree_and_the_host(self):
        report = self.sample_and_report()
        self.assertEqual("proj", report["environment"]["project"])
        self.assertIsNotNone(report["environment"]["kernel"])

    def test_an_oom_counter_reports_the_delta_not_the_history(self):
        # the fake files never change, so a window over them is +0
        report = self.sample_and_report()
        self.assertEqual(0, report["containers"]["one"]["oom_delta"])

    def test_parent_oom_counters_report_a_window_delta(self):
        original_read_cgroup = profile.read_cgroup
        self_counter = 0

        def read_cgroup(path, cgroup_root=profile.CGROUP_ROOT):
            nonlocal self_counter
            reading = original_read_cgroup(path, cgroup_root=cgroup_root)
            if path == "/init.scope":
                self_counter += 1
                reading["events"]["oom"] = self_counter
                reading["events"]["oom_kill"] = self_counter // 2
            return reading

        with patch.object(profile, "read_cgroup", side_effect=read_cgroup):
            report = self.sample_and_report()
        self.assertGreater(report["sampler_cgroup"]["oom_delta"], 0)
        self.assertGreater(report["sampler_cgroup"]["oom_kill_delta"], 0)

    def test_missing_event_counters_are_not_reported_as_zero(self):
        self.assertIsNone(profile.counter_delta({}, {"oom": 0}, "oom"))

    def test_cpu_is_the_delta_of_the_cumulative_counter(self):
        report = self.sample_and_report()
        # the fake cpu.stat never moves, so a phase over it is +0, and the
        # lifetime value is never reported as if it were the phase's
        self.assertEqual(0, report["containers"]["one"]["cpu_usage_usec_delta"])
        self.assertEqual(0, report["containers"]["one"]["cpu_throttled_usec_delta"])

    def test_the_process_view_rides_with_the_phase(self):
        report = self.sample_and_report()
        procs = report["containers"]["one"]["procs"]
        self.assertEqual(["gunicorn"], list(procs))
        self.assertEqual(40000 * 1024, procs["gunicorn"]["vmrss_peak"])
        self.assertEqual(1000 * 1024, procs["gunicorn"]["shmem"])
        self.assertEqual(1, report["proc_samples"])

    def test_pss_can_be_enabled_for_a_full_sample(self):
        sampler = profile.Sampler(
            "proj", "phase-x", interval=0.01, cgroup_root=str(self.cgroup_root),
            proc_root=str(self.proc_root), include_pss=True)
        report = sampler.run(duration=0.05)
        procs = report["containers"]["one"]["procs"]
        self.assertTrue(report["pss_enabled"])
        self.assertEqual(32000 * 1024, procs["gunicorn"]["pss_peak"])
        self.assertGreater(procs["gunicorn"]["pss_complete_samples"], 0)


class ReportCommandTests(unittest.TestCase):

    def test_report_prints_the_phase_table_of_the_file(self):
        run = {
            "project": "p", "phase": "idle", "samples": 3, "elapsed_seconds": 3.0,
            "during": None, "during_rc": None,
            "stack_sum_current_p50": 1048576, "stack_sum_current_peak": 2 << 20,
            "stack_sum_committed_p50": 1 << 20, "stack_sum_committed_peak": 1 << 20,
            "sampler_cgroup": {"current_p50": 4 << 20, "current_peak": 5 << 20,
                               "limit": 16 << 30, "committed_peak": 3 << 20},
            "containers": {"/one": {"cgroup": "/docker/one", "samples": 3,
                                    "current_p50": 1 << 20, "current_peak": 2 << 20,
                                    "peak_file": None, "anon_p50": 1 << 20,
                                    "committed_p50": 1 << 20, "committed_peak": 1 << 20,
                                    "oom_delta": 0, "oom_kill_delta": 0,
                                    "cpu_usage_usec_delta": 1_000_000,
                                    "cpu_throttled_usec_delta": 0,
                                    "procs": {"python": {"processes": 2,
                                                        "vmrss_peak": 1 << 20,
                                                        "anon": 1 << 20,
                                                        "file": 0, "shmem": 0}}}},
            "environment": {"project": "p", "git_commit": "abc123",
                            "docker": "29", "kernel": "6.0"},
            "lost_containers": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runs.jsonl"
            path.write_text(json.dumps(run) + "\n")
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(0, profile.main(["report", "--in", str(path)]))
            text = out.getvalue()
            self.assertIn("idle", text)
            self.assertIn("abc123", text)
            self.assertIn("/one", text)
            self.assertIn("1M", text)
            # cpu cores and the process rows are part of the table too
            self.assertIn("0.33 cores", text)
            self.assertIn("python x2", text)


class WiringTests(unittest.TestCase):

    def test_the_tool_compiles_and_the_suite_is_registered(self):
        subprocess.run([sys.executable, "-m", "py_compile",
                        str(ROOT / "scripts" / "stack_memory_profile")],
                       check=True)
        self.assertIn("test_stack_memory_profile.py",
                      [p.name for p in (ROOT / "scripts").glob("test_*.py")])


class CommandTests(unittest.TestCase):
    def test_pss_is_read_in_bytes_and_unavailable_is_null(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "42"
            directory.mkdir()
            (directory / "smaps_rollup").write_text(
                "Rss: 123 kB\nPss: 87 kB\nPss_Anon: 80 kB\n")
            self.assertEqual(87 * 1024, profile.read_proc_pss(42, tmp))
            self.assertIsNone(profile.read_proc_pss(99, tmp))
        with patch("builtins.open", side_effect=PermissionError):
            self.assertIsNone(profile.read_proc_pss(42))

    def test_each_command_has_its_own_rss_peak(self):
        large = profile.measure_command(
            [sys.executable, "-c", "x = bytearray(64 * 1024 * 1024)"])
        small = profile.measure_command([sys.executable, "-c", "pass"])
        self.assertEqual(0, large["returncode"])
        self.assertEqual(0, small["returncode"])
        self.assertGreater(large["rss_peak"], small["rss_peak"] + 32 * 1024 * 1024)
        self.assertGreater(large["cpu_seconds"], 0)
        self.assertGreater(large["wall_seconds"], 0)

    def test_fast_failure_is_recorded_without_pss(self):
        with patch.object(profile, "read_proc_pss", return_value=None):
            measured = profile.measure_command([sys.executable, "-c", "raise SystemExit(7)"])
        self.assertEqual(7, measured["returncode"])
        self.assertFalse(measured["timed_out"])
        self.assertIsNone(measured["pss_sampled_peak"])
        self.assertEqual(0, measured["pss_samples"])
        self.assertGreater(measured["rss_peak"], 0)

    def test_hung_command_is_killed_and_reaped(self):
        measured = profile.measure_command(
            [sys.executable, "-c", "while True: pass"], timeout=0.1)
        self.assertTrue(measured["timed_out"])
        self.assertEqual(-9, measured["returncode"])
        self.assertLess(measured["wall_seconds"], 5)

    def test_command_cli_preserves_failure_and_report_handles_null_pss(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "commands.jsonl")
            with patch.object(profile, "environment", return_value={}), \
                    patch.object(profile, "read_proc_pss", return_value=None):
                rc = profile.main([
                    "command", "--phase", "broker-down", "--runs", "2",
                    "--revision", "abc123", "--out", path, "--",
                    sys.executable, "-c", "raise SystemExit(7)"])
            self.assertEqual(1, rc)
            run = json.loads(Path(path).read_text())
            self.assertEqual("abc123", run["environment"]["git_commit"])
            self.assertEqual([7, 7], [m["returncode"] for m in run["measurements"]])
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(0, profile.main(["report", "--in", path]))
            self.assertIn("broker-down", output.getvalue())
            self.assertIn("readable 0/2", output.getvalue())

    def test_invalid_limits_do_not_launch_commands(self):
        with patch.object(profile, "measure_command") as measure:
            for options in (["--runs", "0"], ["--timeout", "0"], ["--interval", "0"],
                            ["--timeout", "nan"], ["--interval", "inf"]):
                with self.subTest(options=options), redirect_stderr(io.StringIO()), \
                        self.assertRaises(SystemExit):
                    profile.main(["command", "--phase", "invalid", *options, "--", "unused"])
            measure.assert_not_called()

    def test_runner_termination_unwinds_the_measurement_and_restores_handler(self):
        previous = signal.getsignal(signal.SIGTERM)

        def terminate(*args):
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)

        with patch.object(profile, "measure_command", side_effect=terminate):
            with self.assertRaises(SystemExit) as raised:
                profile.main(["command", "--phase", "interrupted", "--", "unused"])
        self.assertEqual(143, raised.exception.code)
        self.assertEqual(previous, signal.getsignal(signal.SIGTERM))


if __name__ == "__main__":
    unittest.main()
