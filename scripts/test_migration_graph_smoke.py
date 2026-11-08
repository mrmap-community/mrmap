#!/usr/bin/env python3
"""Offline checks for scripts/migration_graph_smoke (issue #1157).

Runs without docker, without network and without `gh`: the graph rules are exercised
on synthetic migration files in memory, and the whole guard is run end to end against a
throw-away git repository in a temporary directory which holds the collision #1157 is
about - two branches, one migration number, one leaf each against master, two leaves
against each other. What is under test is therefore the boundary that matters: the
answer for (branch UNION master), which neither side's own CI run can see.

Run from the repository root: `python3 scripts/test_migration_graph_smoke.py`.
Exit 0 when every check passes, 1 with the failed ones listed.
"""

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
GUARD = SCRIPTS / "migration_graph_smoke.py"

loader = importlib.machinery.SourceFileLoader("migration_graph_smoke", str(GUARD))
spec = importlib.util.spec_from_loader("migration_graph_smoke", loader)
smoke = importlib.util.module_from_spec(spec)
loader.exec_module(smoke)

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))


def node(app, name, deps=(), sides=("HEAD", "origin/master")):
    """One node of a graph, in the shape `collect` hands out."""
    return {"app": app, "name": name, "deps": list(deps), "opaque": [],
            "sides": list(sides), "path": f"backend/{app}/migrations/{name}.py"}


def graph(*nodes):
    """{(app, name): node}, the key derived the way Django's graph keys it."""
    return {(n["app"], n["name"]): n for n in nodes}


def nodes_of(app, *specs):
    """A graph out of (name, dependencies) pairs, all of one app."""
    return graph(*[node(app, name, deps) for name, deps in specs])


def leaves_of(nodes):
    return smoke.leaf_nodes(nodes)


def leaf_names(nodes, app):
    return [name for app_, name in leaves_of(nodes) if app_ == app]


# ----------------------------------------------------------------- dependencies

def test_dependencies_are_read_without_importing():
    source = ("from django.db import migrations\n\n\nclass Migration(migrations.Migration):\n"
              "    initial = True\n\n"
              "    dependencies = [\n        ('notify', '0005_alter_x'),\n"
              "        ('registry', '0037_store_the_rows_of_the_alerts'),\n    ]\n")
    deps, opaque = smoke.dependencies_of(source, "0001.py")
    check("literal dependencies are read in the order they are written",
          deps == [("notify", "0005_alter_x"),
                   ("registry", "0037_store_the_rows_of_the_alerts")] and opaque == [],
          f"deps={deps} opaque={opaque}")

    # The one Django form this repository really carries besides the literal pair.
    swappable = ("from django.conf import settings\nfrom django.db import migrations\n\n\n"
                 "class Migration(migrations.Migration):\n"
                 "    dependencies = [\n        ('registry', '0030_x'),\n"
                 "        migrations.swappable_dependency(settings.AUTH_USER_MODEL),\n    ]\n")
    deps, opaque = smoke.dependencies_of(swappable, "0032.py")
    check("a swappable dependency is reported as unresolved instead of guessed",
          deps == [("registry", "0030_x")] and len(opaque) == 1
          and "swappable_dependency" in opaque[0], f"deps={deps} opaque={opaque}")

    # A module-level `dependencies` which is not the Migration class's is not a graph edge.
    other = ("dependencies = [('registry', 'nowhere')]\n\n\nclass Helper:\n"
             "    dependencies = [('registry', 'also_nowhere')]\n")
    check("only the dependencies of the Migration class are read",
          smoke.dependencies_of(other, "helper.py") == ([], []),
          smoke.dependencies_of(other, "helper.py"))

    check("a migration without dependencies is a root, not an error",
          smoke.dependencies_of("class Migration:\n    operations = []\n", "r.py") == ([], []))

    # The shapes whose edge this guard would silently lose: it must stop instead.
    for name, body in (("a name", "    dependencies = BASE_DEPS\n"),
                       ("a comprehension", "    dependencies = [d for d in BASE_DEPS]\n"),
                       ("a string", "    dependencies = '__first__'\n")):
        try:
            smoke.dependencies_of(f"class Migration:\n{body}", "x.py")
            ok, detail = False, "no HarnessError"
        except smoke.HarnessError as error:
            ok, detail = "x.py" in str(error), str(error)
        check(f"a dependencies written as {name} stops the run and names the file", ok, detail)

    try:
        smoke.dependencies_of("class Migration:\n  dependencies [[", "broken.py")
        check("a file which does not parse stops the run", False, "no HarnessError")
    except smoke.HarnessError as error:
        check("a file which does not parse stops the run", "broken.py" in str(error), str(error))


# --------------------------------------------------------------- queue membership

HEAD_LISTING = {"registry": {
    "0001_initial": "backend/registry/migrations/0001_initial.py",
    "0003_mine": "backend/registry/migrations/0003_mine.py"}}
MASTER_LISTING = {"registry": {
    "0001_initial": "backend/registry/migrations/0001_initial.py",
    "0003_theirs": "backend/registry/migrations/0003_theirs.py"}}


def test_the_tree_the_queue_builds():
    chosen = smoke.queue_files(HEAD_LISTING, MASTER_LISTING, HEAD_LISTING)
    check("the file this branch adds is read from the branch",
          chosen[("registry", "0003_mine")]["side"] == smoke.HEAD
          and chosen[("registry", "0003_mine")]["sides"] == [smoke.HEAD],
          chosen.get(("registry", "0003_mine")))
    check("the file master added after the branch split off is read from master",
          chosen[("registry", "0003_theirs")]["side"] == smoke.BASE
          and chosen[("registry", "0003_theirs")]["sides"] == [smoke.BASE],
          chosen.get(("registry", "0003_theirs")))
    check("a file both sides carry is read as the branch has it, and named as both's",
          chosen[("registry", "0001_initial")]["side"] == smoke.HEAD
          and chosen[("registry", "0001_initial")]["sides"] == [smoke.HEAD, smoke.BASE],
          chosen.get(("registry", "0001_initial")))

    # Both files above are in the queue's tree, and both hang off 0001: that is #1157.
    both_sides = nodes_of("registry", ("0001_initial", []),
                          ("0003_mine", [("registry", "0001_initial")]),
                          ("0003_theirs", [("registry", "0001_initial")]))
    check("the two sides' migrations of one number are two leaves of one tree",
          leaf_names(both_sides, "registry") == ["0003_mine", "0003_theirs"],
          leaves_of(both_sides))

    # The merge base exists for exactly one decision: what HEAD deleted is gone.
    before = {"registry": {"0001_initial": "p1", "0002_gone": "p2"}}
    kept = smoke.queue_files(HEAD_LISTING, before, before)
    check("a migration this branch deleted does not come back as a leaf of master's",
          ("registry", "0002_gone") not in kept
          and leaf_names(nodes_of("registry", ("0001_initial", []),
                                  ("0003_mine", [("registry", "0001_initial")])),
                         "registry") == ["0003_mine"], kept)


# ----------------------------------------------------------------------- leaves

def test_a_leaf_is_a_leaf_the_way_django_counts_them():
    chain = graph(node("registry", "0001_initial", []),
                  node("registry", "0002_next", [("registry", "0001_initial")]))
    check("a linear history has one leaf", leaf_names(chain, "registry") == ["0002_next"],
          leaves_of(chain))

    pair = graph(node("registry", "0037_alerts", []),
                 node("registry", "0038_keyword", [("registry", "0037_alerts")]),
                 node("registry", "0038_run_moment", [("registry", "0037_alerts")]))
    check("two migrations off one leaf are two leaves",
          leaf_names(pair, "registry") == ["0038_keyword", "0038_run_moment"], leaves_of(pair))

    fixed = graph(*pair.values(),
                  node("registry", "0039_merge",
                       [("registry", "0038_keyword"), ("registry", "0038_run_moment")]))
    check("the renumbered migration on top of both ends it",
          leaf_names(fixed, "registry") == ["0039_merge"], leaves_of(fixed))

    # Django counts leaves of the whole graph and groups them by app, so a migration
    # another app depends on is not a leaf of its own app any more.
    cross = graph(node("notify", "0005_type", []),
                  node("registry", "0036_watchdog", []),
                  node("registry", "0037_alerts",
                       [("notify", "0005_type"), ("registry", "0036_watchdog")]))
    check("an app whose last migration is another app's parent has no leaf of its own",
          leaf_names(cross, "notify") == [] and leaf_names(cross, "registry") == ["0037_alerts"],
          leaves_of(cross))
    check("and that is not a conflict",
          len(leaf_names(cross, "notify")) <= 1)

    foreign = graph(node("registry", "0001_initial", [("auth", "0012_alter_user")]))
    check("a dependency on another repository's app is neither an edge nor a hole",
          smoke.dangling(foreign) == [] and leaf_names(foreign, "registry") == ["0001_initial"],
          smoke.dangling(foreign))

    hole = graph(node("registry", "0005_x", [("registry", "0004_missing")]))
    check("a dependency on a migration neither side carries is a hole",
          smoke.dangling(hole) == [(("registry", "0005_x"), ("registry", "0004_missing"))],
          smoke.dangling(hole))

    first = graph(node("registry", "0001_initial", []),
                  node("registry", "0002_first", [("registry", "__first__")]))
    check("a __first__ dependency on the same app is not a hole",
          smoke.dangling(first) == [], smoke.dangling(first))

    loop = graph(node("registry", "0001_a", [("registry", "0002_b")]),
                 node("registry", "0002_b", [("registry", "0001_a")]))
    check("a cycle has no leaf and is reported as one",
          leaves_of(loop) == [] and smoke.cyclic(loop), leaves_of(loop))
    check("the number a renumbered leaf would carry is the next one",
          smoke.next_number(["0038", "0038"]) == "0039"
          and smoke.next_number(["0038", "0039"]) == "0040"
          and smoke.next_number(["auto_2026"]) is None)


def test_what_a_conflict_is_told():
    pair = graph(node("registry", "0037_alerts", []),
                 node("registry", "0038_keyword", [("registry", "0037_alerts")],
                      sides=("HEAD",)),
                 node("registry", "0038_run_moment", [("registry", "0037_alerts")],
                      sides=("origin/master",)))
    lines, conflicts = smoke.verdict(pair, leaves_of(pair), ["registry"])
    text = "\n".join(lines)
    check("a conflict names both leaves, their files and the side each comes from",
          conflicts == ["registry"] and all(part in text for part in (
              "0038_keyword", "0038_run_moment",
              "backend/registry/migrations/0038_keyword.py",
              "backend/registry/migrations/0038_run_moment.py", "(HEAD)", "(origin/master)")),
          text)
    check("a conflict says which number both leaves carry",
          "both carry the number 0038" in text, text)
    check("a conflict says what makemigrations will answer for the queue",
          "Conflicting migrations detected; multiple leaf nodes in the migration graph" in text,
          text)
    check("a conflict names the number to renumber to", "registry/0039_" in text, text)

    ok_lines, conflicts = smoke.verdict(pair, [("registry", "0037_alerts")], ["registry"])
    check("one leaf is one line and no conflict", conflicts == []
          and len(ok_lines) == 1 and "one leaf: 0037_alerts" in ok_lines[0], ok_lines)

    hidden, conflicts = smoke.verdict(pair, leaves_of(pair), [])
    check("--app cannot hide a second leaf of an app nobody asked about",
          conflicts == ["registry"] and "0038_keyword" in "\n".join(hidden), (conflicts, hidden))


# ------------------------------------------------------------------ end to end

def git(cwd, *args):
    process = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if process.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {process.stderr.strip()}")
    return process.stdout


def make_repo(root):
    """A repository of two apps whose master and branch each add one migration."""
    repo = Path(root) / "repo"
    for app in ("registry", "accounts"):
        (repo / "backend" / app / "migrations").mkdir(parents=True)
        (repo / "backend" / app / "migrations" / "__init__.py").write_text("")
    git(repo, "init", "-q", "-b", "master")
    write(repo, "registry", "0001_initial", deps=[])
    write(repo, "accounts", "0001_initial", deps=[])
    commit(repo, "two initial migrations")

    git(repo, "checkout", "-q", "-b", "branch")
    write(repo, "registry", "0002_mine", deps=[("registry", "0001_initial")])
    commit(repo, "the branch adds 0002_mine")
    git(repo, "checkout", "-q", "master")
    write(repo, "registry", "0002_theirs", deps=[("registry", "0001_initial")])
    commit(repo, "master adds 0002_theirs")
    return repo


def write(repo, app, name, deps=(), opaque=False):
    entry = ("        migrations.swappable_dependency(settings.AUTH_USER_MODEL),\n"
             if opaque else "".join(f"        ('{a}', '{n}'),\n" for a, n in deps))
    (repo / "backend" / app / "migrations" / f"{name}.py").write_text(
        "from django.conf import settings\nfrom django.db import migrations\n\n\n"
        "class Migration(migrations.Migration):\n\n"
        f"    dependencies = [\n{entry}    ]\n\n    operations = []\n")


def commit(repo, message):
    git(repo, "-c", "user.name=t", "-c", "user.email=t@example", "add", "-A")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@example",
        "commit", "-q", "-m", message, "--no-gpg-sign")


def guard(repo, *args):
    env = dict(os.environ, MIGRATION_GRAPH_SMOKE_REPO=str(repo))
    return subprocess.run([sys.executable, str(GUARD), *args], capture_output=True,
                          text=True, env=env)


def test_the_guard_on_a_repository_that_clashes(repo):
    out = guard(repo, "--head", "branch", "--base", "master")
    check("the collision of two branches is a failure the branch could not see",
          out.returncode == 1, f"code={out.returncode} out={out.stdout}{out.stderr}")
    check("it names both leaves with the file and the side declaring them",
          "backend/registry/migrations/0002_mine.py (branch)" in out.stdout
          and "backend/registry/migrations/0002_mine.py (branch)" in out.stdout
          and "backend/registry/migrations/0002_theirs.py (master)" in out.stdout, out.stdout)
    check("it says the number both leaves carry", "number 0002" in out.stdout, out.stdout)
    check("and what the merge queue would answer", "Conflicting migrations detected" in out.stdout,
          out.stdout)

    # The other side alone, which is what a branch's own CI run sees, is green: this is
    # the whole point of checking (branch UNION master).
    alone = guard(repo, "--head", "branch", "--base", "branch~1")
    check("the same branch against its own parent is green",
          alone.returncode == 0, alone.stdout + alone.stderr)

    data = json.loads(guard(repo, "--head", "branch", "--base", "master", "--json").stdout)
    registry = [a for a in data["apps"] if a["app"] == "registry"][0]
    check("--json is one object naming the leaves of the clashing app",
          data["ok"] is False and len(registry["leaves"]) == 2
          and registry["ok"] is False, data)
    check("--json carries the three commits the verdict was read from",
          data["head"] and data["base"] and data["merge_base"], data)

    narrowing = guard(repo, "--head", "branch", "--base", "master", "--app", "accounts")
    check("narrowing the report to another app still fails on the leaf it hides",
          narrowing.returncode == 1 and "0002_mine" in narrowing.stdout, narrowing.stdout)

    # The fix the report asks for.
    git(repo, "checkout", "-q", "branch")
    (repo / "backend" / "registry" / "migrations" / "0002_mine.py").unlink()
    write(repo, "registry", "0003_mine", deps=[("registry", "0001_initial"),
                                               ("registry", "0002_theirs")])
    commit(repo, "renumbered behind master's leaf")
    fixed = guard(repo, "--head", "branch", "--base", "master")
    check("after the renumber the same two branches are one leaf",
          fixed.returncode == 0 and "one leaf: 0003_mine" in fixed.stdout,
          fixed.stdout + fixed.stderr)

    check("the apps of the checkout are all found, and __init__ is not a migration",
          "accounts" in fixed.stdout and "0 migrations" not in fixed.stdout
          and "1 migration," in fixed.stdout, fixed.stdout)


def test_a_migration_the_branch_deleted(root):
    """A squash or a dropped migration is the case where reading the base blindly would
    invent a leaf: the queue's tree does not carry what the branch deleted."""
    repo = Path(root) / "deleted"
    (repo / "backend" / "registry" / "migrations").mkdir(parents=True)
    (repo / "backend" / "registry" / "migrations" / "__init__.py").write_text("")
    git(repo, "init", "-q", "-b", "master")
    write(repo, "registry", "0001_initial", deps=[])
    write(repo, "registry", "0002_dropped", deps=[("registry", "0001_initial")])
    commit(repo, "initial and one migration master still has")
    git(repo, "checkout", "-q", "-b", "branch")
    (repo / "backend" / "registry" / "migrations" / "0002_dropped.py").unlink()
    write(repo, "registry", "0003_replacing", deps=[("registry", "0001_initial")])
    commit(repo, "the migration is replaced by another one")

    out = guard(repo, "--head", "branch", "--base", "master")
    check("a migration the branch deleted is not counted as a leaf of master's",
          out.returncode == 0 and "0002_dropped" not in out.stdout
          and "one leaf: 0003_replacing" in out.stdout, out.stdout + out.stderr)


def test_the_guard_when_it_cannot_answer(repo):
    missing = guard(repo, "--base", "origin/nothing-here")
    check("a ref which names no commit is the harness, exit 2, not a green graph",
          missing.returncode == 2 and "git fetch origin" in missing.stderr,
          f"code={missing.returncode} err={missing.stderr}")

    unreadable = Path(str(repo) + "-unreadable")
    unreadable.mkdir(parents=True, exist_ok=True)
    git(unreadable, "init", "-q", "-b", "master")
    (unreadable / "backend" / "registry" / "migrations").mkdir(parents=True)
    (unreadable / "backend" / "registry" / "migrations" / "0001_initial.py").write_text(
        "from django.db import migrations\n\n\nBASE = [('registry', 'nowhere')]\n\n\n"
        "class Migration(migrations.Migration):\n    dependencies = BASE\n"
        "    operations = []\n")
    commit(unreadable, "a migration whose dependencies cannot be read")
    out = guard(unreadable, "--head", "master", "--base", "master")
    check("a dependencies this cannot read stops the run and names the file",
          out.returncode == 2 and "0001_initial.py" in out.stderr,
          f"code={out.returncode} err={out.stderr}")

    elsewhere = guard(repo, "--head", "master", "--base", "master")
    check("a repository with migrations answers for its own apps only",
          elsewhere.returncode == 0 and "notify" not in elsewhere.stdout,
          elsewhere.stdout)


def test_nothing_but_git_is_executed():
    """The guard is host-only by construction: no docker, no gh, no network. It is a
    fact about the file, so it is read out of the file rather than trusted."""
    tree = __import__("ast").parse(GUARD.read_text())
    executed = []
    for n in __import__("ast").walk(tree):
        if (isinstance(n, __import__("ast").Call)
                and __import__("ast").unparse(n.func).endswith("subprocess.run")):
            argv = n.args[0]
            first = argv.elts[0] if isinstance(argv, __import__("ast").List) and argv.elts else None
            executed.append(first.value if isinstance(first, __import__("ast").Constant) else None)
    check("every program the guard runs is git", executed and all(e == "git" for e in executed),
          executed)


def main():
    for fn in (test_dependencies_are_read_without_importing,
               test_the_tree_the_queue_builds,
               test_a_leaf_is_a_leaf_the_way_django_counts_them,
               test_what_a_conflict_is_told,
               test_nothing_but_git_is_executed):
        fn()
    with tempfile.TemporaryDirectory(prefix="migration-graph-smoke-") as tmp:
        repo = make_repo(tmp)
        test_the_guard_on_a_repository_that_clashes(repo)
        test_the_guard_when_it_cannot_answer(repo)
        test_a_migration_the_branch_deleted(tmp)

    failed = 0
    for name, ok, detail in RESULTS:
        if not ok:
            failed += 1
        print(f"{'PASS' if ok else 'FAIL'}  {name}"
              + (f"  [{detail}]" if detail and not ok else ""))
    print(f"{len(RESULTS) - failed}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
