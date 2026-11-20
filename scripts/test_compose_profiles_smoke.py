#!/usr/bin/env python3
"""Offline tests for `scripts/compose_profiles_smoke.py` (issue #1614).

Run from the repository root:  python3 scripts/test_compose_profiles_smoke.py
Needs no docker and no network for the checks of the rules themselves: every
rule is answered against a synthetic resolved configuration, so the drift the
check exists to catch is reproduced here rather than on somebody's stack. Where
docker is on PATH, the suite additionally runs the rules over the real compose
files of this checkout and prints the count it covered; without docker those
checks are skipped out loud, which is the honest smaller count rather than a
green that means nothing.

What these checks hold onto is the pair of answers the matrix must keep apart:
the full deployment waits for its log store and ships its container logs into
it, the lightweight mode starts without either and must say so in its own
configuration. Both directions of that seam fail in a way nothing notices at
runtime - a `required: false` leaking into the base file costs a deployment its
log handler on a cold start, a missing one costs a developer an `up` that
refuses to start at all.

Exit code 0 = all ran checks passed.
"""

import importlib.util
import shutil
import subprocess  # nosec B404 - probing for docker is a check of the environment
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

_spec = importlib.util.spec_from_file_location(
    "compose_profiles_smoke", SCRIPTS / "compose_profiles_smoke.py")
smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoke)

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))


def config(services=None, **named):
    """A resolved-configuration document out of service definitions. Names
    carrying a dash - most of them - arrive through the dict, not as keywords."""
    merged = dict(services or {})
    merged.update(named)
    return {"services": {name: dict(body) for name, body in merged.items()}}


COREISH = {"postgis": {"image": "postgis/postgis", "restart": "unless-stopped"},
           "redis": {"image": "library/redis", "restart": "unless-stopped"},
           "docker-api": {"image": "haproxy", "restart": "unless-stopped"},
           "backend": {"image": "example/backend", "restart": "unless-stopped",
                       "depends_on": {"victoria-logs": {
                           "condition": "service_started", "required": True}}},
           "celery-worker": {"image": "example/backend", "restart": "unless-stopped"},
           "celery-beat": {"image": "example/backend", "restart": "unless-stopped"},
           "frontend": {"image": "example/frontend", "restart": "unless-stopped",
                        "logging": {"driver": "syslog", "options": {
                            "syslog-address": "udp://127.0.0.1:5514"}}},
           "victoria-logs": {"image": "example/vl", "restart": "unless-stopped"},
           "grafana": {"image": "example/grafana"},
           "pgadmin": {"image": "example/pgadmin"},
           "flower": {"image": "example/flower"}}

# What the full deployment of docker-compose.yml alone runs: the one-off check
# containers belong to the development file, so they are not in this set.
FULL_EXPECT = smoke.CORE | (smoke.TIER_SERVICES
                            - frozenset(smoke.TIERS["testing"]))


def full_like():
    """The shape of docker-compose.yml alone: no profile anywhere, the log
    store both depended on and shipped to."""
    return config(**COREISH)


def lightweight_like():
    """The shape of docker-compose.yml + docker-compose.lightweight.yml: the
    tiers profiled, the edge optional, the container logs local."""
    services = {name: dict(body) for name, body in COREISH.items()}
    services["victoria-logs"]["profiles"] = ["observability"]
    services["grafana"]["profiles"] = ["observability"]
    services["pgadmin"]["profiles"] = ["admin"]
    services["flower"]["profiles"] = ["admin"]
    services["behave"] = {"image": "example/backend", "profiles": ["testing"]}
    services["backend"]["depends_on"] = {"victoria-logs": {
        "condition": "service_started", "required": False}}
    for name in ("postgis", "frontend"):
        services[name]["logging"] = {"driver": "json-file",
                                     "options": {"max-size": "10m"}}
    return config(**services)


def combination(name, files, profiles, expect):
    return {"name": name, "files": tuple(files), "profiles": tuple(profiles),
            "expect": expect}


def lite_combination(**overrides):
    """A lightweight combination over the synthetic model, with the defaults of
    a passing answer: the core tier only, the testing tier inert."""
    combo = combination("synthetic lightweight",
                        ("docker-compose.yml", "docker-compose.lightweight.yml"),
                        (), smoke.CORE)
    combo.update(overrides)
    return combo


def active_set_checks():
    lite = lightweight_like()
    running = smoke.active_services(lite)
    check("a service with no profile runs in the default mode",
          "backend" in running and "postgis" in running)
    check("a profiled service does not run without its profile",
          not any(name in running
                  for name in ("grafana", "pgadmin", "flower", "victoria-logs",
                               "behave")),
          f"got {sorted(running)}")
    check("one active profile brings exactly its own tier",
          smoke.active_services(lite, ("admin",))
          == smoke.active_services(lite) | {"pgadmin", "flower"})
    check("several profiles bring the union of their tiers",
          {"grafana", "flower", "pgadmin", "victoria-logs"}.issubset(
              smoke.active_services(lite, ("admin", "observability"))))
    check("an unrelated profile activates nothing",
          smoke.active_services(lite, ("nosuch",)) == smoke.active_services(lite))


def classification_checks():
    check("every tier of the matrix is a set of distinct services",
          len(smoke.TIER_SERVICES) == sum(len(members) for members in smoke.TIERS.values()),
          f"{smoke.TIERS}")
    check("the core tier is exactly the services which must come back after a reboot",
          smoke.CORE == frozenset(smoke.ALWAYS_ON), f"{smoke.CORE}")
    check("the testing tier holds the one-off check containers of the dev file",
          set(smoke.TIERS["testing"]) == {"pre-commit-check", "behave",
                                          "django-tests", "frontend-tests"})
    check("the full deployment documents no testing tier",
          not frozenset(smoke.TIERS["testing"])
          & next(c["expect"] for c in smoke.COMBINATIONS
                 if c["files"] == (smoke.BASE,)),
          "docker-compose.yml does not define the one-off containers")
    check("a service nobody classified is reported",
          smoke.unclassified(config(backend={}, jaeger={"image": "x"})) == ["jaeger"],
          f"got {smoke.unclassified(config(backend={}, jaeger={'image': 'x'}))}")
    check("the mapserver of the dev file counts as core, not as a tier",
          smoke.unclassified(config(mapserver={}, postgis={})) == [])


def dependency_checks():
    lite = lightweight_like()
    check("an optional edge into an inactive tier is not a dangling dependency",
          smoke.dangling_dependencies(lite) == [],
          f"got {smoke.dangling_dependencies(lite)}")
    broken = lightweight_like()
    broken["services"]["backend"]["depends_on"]["victoria-logs"]["required"] = True
    check("a required edge into an inactive tier is reported",
          smoke.dangling_dependencies(broken) == [("backend", "victoria-logs")],
          f"got {smoke.dangling_dependencies(broken)}")
    check("the same edge is fine once the profile runs the tier",
          smoke.dangling_dependencies(broken, ("observability",)) == [])
    short = config({"backend": {"depends_on": ["victoria-logs"]},
                    "victoria-logs": {"profiles": ["observability"]}})
    check("the short depends_on syntax is treated as required",
          smoke.dangling_dependencies(short) == [("backend", "victoria-logs")])
    check("an edge to a service which runs is never reported",
          smoke.dangling_dependencies(full_like()) == [])


def logging_checks():
    lite = lightweight_like()
    check("the lightweight mode ships no container log to an absent store",
          smoke.blind_syslog(lite) == [], f"got {smoke.blind_syslog(lite)}")
    check("the full deployment keeps shipping container logs into its store",
          smoke.blind_syslog(full_like()) == [], "the store runs there")
    regressed = lightweight_like()
    regressed["services"]["postgis"]["logging"] = {
        "driver": "syslog", "options": {"syslog-address": "udp://127.0.0.1:5514"}}
    check("a syslog driver inherited into a mode without the store is reported",
          smoke.blind_syslog(regressed) == [("postgis", "udp://127.0.0.1:5514")],
          f"got {smoke.blind_syslog(regressed)}")
    check("... and is fine again with the observability profile on",
          smoke.blind_syslog(regressed, ("observability",)) == [])
    quiet = config(postgis={"logging": {"driver": "journald"}})
    check("another driver than syslog is nobody's business",
          smoke.blind_syslog(quiet) == [])


def policy_checks():
    check("the core tier of the lightweight mode is still reboot-persistent",
          smoke.nonpersistent(lightweight_like()) == [])
    softened = lightweight_like()
    del softened["services"]["celery-worker"]["restart"]
    check("a core service which lost its restart policy is reported",
          smoke.nonpersistent(softened) == ["celery-worker"])
    check("a one-off check container is not expected to carry a restart policy",
          smoke.nonpersistent(config(behave={"image": "x"}), ()) == [])
    homeless = config({"behave": {"profiles": ["testing"]},
                       "backend": {"image": "x"}, "postgis": {"image": "x"},
                       "redis": {"image": "x"}, "docker-api": {"image": "x"},
                       "celery-worker": {"image": "x"},
                       "celery-beat": {"image": "x"},
                       "frontend": {"image": "x"}})
    check("an active service without image and build is reported",
          smoke.homeless(homeless, ("testing",)) == ["behave"])
    check("while the same service inert is not reported",
          smoke.homeless(homeless) == [])


def seam_checks():
    """check_combination's two directions of the depends_on seam, and the
    active-set assertion it makes with them."""
    ok = smoke.check_combination(
        combination("full", ("docker-compose.yml",), (), FULL_EXPECT),
        full_like())
    check("the full deployment as designed passes", ok == [], f"{ok}")
    leak = full_like()
    leak["services"]["backend"]["depends_on"]["victoria-logs"]["required"] = False
    problems = smoke.check_combination(
        combination("full", ("docker-compose.yml",), (), FULL_EXPECT),
        leak)
    check("a required: false leaking into the full mode fails the check",
          any("required" in problem for problem in problems), f"{problems}")
    forgotten = lightweight_like()
    forgotten["services"]["backend"]["depends_on"]["victoria-logs"]["required"] = True
    lite = lite_combination(expect=smoke.CORE)
    problems = smoke.check_combination(lite, forgotten)
    check("a lightweight mode which forgot required: false fails the check",
          any("required: false" in problem for problem in problems), f"{problems}")
    wrong_set = smoke.check_combination(
        lite_combination(expect=smoke.CORE | {"behave"}), lightweight_like())
    check("a combination whose documented set does not match the model fails",
          any("service(s), not the" in problem for problem in wrong_set),
          f"{wrong_set}")
    ok = smoke.check_combination(lite, lightweight_like())
    check("the lightweight default as designed passes", ok == [], f"{ok}")


def real_files_checks():
    """The rules over this checkout's real compose files, where a docker CLI
    can resolve them."""
    covered = 0
    for combo in smoke.COMBINATIONS:
        if not all((ROOT / file).is_file() for file in combo["files"]):
            print(f"SKIP  the real {combo['name']}: "
                  f"{' or '.join(f for f in combo['files'] if not (ROOT / f).is_file())} "
                  f"is not in this checkout")
            continue
        try:
            resolved = smoke.compose_config(combo["files"], combo["profiles"])
        except smoke.HarnessError as error:
            check(f"the real {combo['name']} resolves", False, str(error))
            continue
        covered += 1
        problems = smoke.check_combination(combo, resolved)
        check(f"the real {combo['name']} agrees with the matrix",
              not problems, "; ".join(problems))
    check("the docker-backed part covered every combination of the table",
          covered == len(smoke.COMBINATIONS), f"{covered} of {len(smoke.COMBINATIONS)}")


def main():
    print(f"compose_profiles_smoke tests, on {ROOT}")
    active_set_checks()
    classification_checks()
    dependency_checks()
    logging_checks()
    policy_checks()
    seam_checks()
    if shutil.which("docker") and subprocess.run(  # nosec B603 - a fixed argv
            ["docker", "compose", "version"], capture_output=True,
            text=True).returncode == 0:
        real_files_checks()
    else:
        print("SKIP  the real compose files (no docker compose CLI on PATH)")

    width = max(len(name) for name, _, _ in RESULTS)
    failed = [(name, detail) for name, ok, detail in RESULTS if not ok]
    for name, ok, detail in RESULTS:
        line = f"{'PASS' if ok else 'FAIL'}  {name:<{width}}"
        if not ok and detail:
            line += f"   <- {detail}"
        print(line)
    if failed:
        print(f"FAILED ({len(failed)} of {len(RESULTS)} checks)", file=sys.stderr)
        return 1
    print(f"OK ({len(RESULTS)} checks; skips marked above)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
