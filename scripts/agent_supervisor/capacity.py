"""Admission: may the host take one more job right now?

The measurement is not redone here. ``scripts/agent_capacity`` (#1053) is the
repository's own gate - it knows the cgroup this process lives in, the
unreclaimable charge inside it, the load, the disk, the running
``mrmap-agent-*`` stacks and the pressure state - and a supervisor carrying its
own copy of that arithmetic is a supervisor that will disagree with itself. So
this module runs the gate and reads its answer.

What it adds of its own is one rule: **the answer has to be read, not assumed.**
A missing script, a timeout, an exit code that is neither of the two meaningful
ones, an unparsable line - all of them mean *do not start another stack*. An
unmeasurable host is a full host.

Three job classes, named the way the gate names them:

``stack``     a Compose test stack with a worker in it - the heavy one
``process``   one more OpenCode worker without a stack (a resume, a review run)
``none``      a tick that only reads

The gate counts stacks from ``docker ps`` itself, so the supervisor deliberately
does not pass ``--stacks``: its own bookkeeping sees only its own jobs, while the
host's running stacks - including one an agent started by hand in VS Code - are
what the admission decision has to be about.
"""

import json
import os
import subprocess

NEED_STACK = "stack"
NEED_PROCESS = "process"
NEED_NONE = "none"
NEEDS = (NEED_STACK, NEED_PROCESS, NEED_NONE)

TIMEOUT_S = 30

_HERE = os.path.dirname(os.path.abspath(__file__))
CAPACITY_PATH = os.environ.get("MRMAP_CAPACITY_SCRIPT") or os.path.join(
    os.path.dirname(_HERE), "agent_capacity")


class Capacity:
    """One call per decision, nothing cached between decisions.

    Capacity is exactly the thing that changes while a supervisor sleeps, so a
    remembered verdict is a wrong verdict. The cost is one host-only Python run
    that opens no socket, which is cheap beside the GitHub reads.
    """

    def __init__(self, cfg, path=None):
        self.cfg = cfg
        self.path = path or CAPACITY_PATH

    def evaluate(self, need=NEED_STACK):
        """{fits, verdict, explanation, reasons, metrics, source}. Never raises.

        The shape the gate answers in (#1053) is
        ``{"need", "fits", "reasons", "metrics": {…}}``; the supervisor's shape
        adds a `verdict` word and a one-line `explanation` because that is what
        the tick report and the event log print.
        """
        if need not in NEEDS:
            raise ValueError(f"not a job class: {need}")
        if not os.path.exists(self.path):
            return self._refuse("unknown", f"no capacity gate at {self.path}; admission is "
                                           "refused until one exists")
        raw, error, code = self._run(["--need", need, "--json"])
        if error:
            # A gate from before #1053 knows neither --need nor --json. Ask it
            # the old way and measure everything as one stack, saying so.
            line, error2, code2 = self._run([])
            if error2:
                return self._refuse("error", f"the capacity gate did not answer: "
                                             f"{error}; {error2}")
            return self._from_line(line, code2)
        try:
            data = json.loads(raw)
        except ValueError:
            # The other way an old gate shows itself: it does not reject the new
            # flags, it ignores them and prints its one line anyway. Reading that
            # line is the difference between running on an updated host and
            # refusing work on one that is merely a release behind.
            return self._from_line(raw, code)
        if not isinstance(data, dict):
            return self._refuse("error", "the capacity gate answered a JSON non-object")
        fits = bool(data.get("fits"))
        reasons = [str(reason) for reason in (data.get("reasons") or [])]
        metrics = data.get("metrics") or {}
        return {
            "fits": fits,
            "verdict": "fits" if fits else "busy",
            "explanation": "; ".join(reasons) if reasons else self._summary(need, metrics),
            "reasons": reasons,
            "need": data.get("need") or need,
            "metrics": metrics,
            "source": "json",
        }

    def fits(self, need=NEED_STACK):
        return self.evaluate(need)["fits"]

    def _summary(self, need, metrics):
        """The short human line the tick report prints when nothing is wrong.

        The class is the one that was asked for: the gate's metrics describe the
        host, not the request, so the name has to come from this side.
        """
        if not metrics:
            return "the gate reported no metrics"
        return (f"{need}: mem {metrics.get('mem_effective_gb', 0):.1f}G "
                f"of {metrics.get('mem_cgroup_limit_gb') or metrics.get('mem_host_available_gb')}G "
                f"({metrics.get('mem_source', '?')}), stacks {metrics.get('stacks')}"
                f"/{metrics.get('stacks_max')}, load {metrics.get('load_per_core', 0):.1f}/core")

    def _run(self, extra):
        cmd = [self.path] + extra
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired:
            return None, f"{os.path.basename(self.path)} timed out after {TIMEOUT_S}s", None
        except OSError as exc:
            return None, f"{os.path.basename(self.path)} cannot run: {exc}", None
        out = (proc.stdout or "").strip()
        if proc.returncode not in (0, 1):
            # 0 fits and 1 busy are the only meaningful answers. Anything else is
            # a broken gate, and a broken gate is not permission.
            return None, (f"{os.path.basename(self.path)} exited {proc.returncode}: "
                          f"{(proc.stderr or out)[:200]}"), proc.returncode
        return out, None, proc.returncode

    def _from_line(self, text, code=None):
        """The pre-#1053 gate: one line, ending in `-> fits` or `-> busy`.

        The exit code and the word at the end have to agree. A gate that writes
        `fits` and exits busy is a gate with a bug, and the bug is on the side
        that lets work start - so the disagreement is refused.
        """
        line = (text or "").strip().splitlines()
        line = line[-1] if line else ""
        if line.endswith("-> fits"):
            if code == 1:
                return self._refuse("error", "the capacity gate says fits but exits busy: "
                                             f"{line}")
            return {"fits": True, "verdict": "fits", "explanation": line, "reasons": [],
                    "need": NEED_STACK, "metrics": {}, "source": "legacy-line"}
        if line.endswith("-> busy"):
            return {"fits": False, "verdict": "busy", "explanation": line, "reasons": ["busy"],
                    "need": NEED_STACK, "metrics": {}, "source": "legacy-line"}
        return self._refuse("unknown", f"the capacity gate's answer is not understood: {line}")

    def _refuse(self, verdict, explanation):
        return {"fits": False, "verdict": verdict, "explanation": explanation, "reasons": [],
                "need": None, "metrics": {}, "source": "refused"}
