#!/usr/bin/env python3
"""migration_graph_smoke: do this branch and master end up with two leaf migrations?

Host-side check carried by this repository; run it as `python3
scripts/migration_graph_smoke.py` from the repository root. Standard library only,
plus the local `git` CLI: two commits are read, nothing is built, no container is
started, no network is contacted and no `gh` is needed. Exit 0 when every app's
migration graph still has a single leaf, 1 when one has more than one, 2 when the
harness itself could not run.

Why the leaf of a migration graph is checked here, and nowhere else
-------------------------------------------------------------------
Two branches which each add a migration to the same app are both green on their own:
each has one leaf against the master it was cut from, so each passes the
`makemigrations --check --dry-run` of `backend/.bash_scripts/pre_commit_check.sh`.
Merged they are not: the tree of the merge queue carries both files, the app ends up
with two leaf nodes, and `makemigrations` answers `CommandError: Conflicting
migrations detected; multiple leaf nodes in the migration graph`. That is #1157:
after a `0036` triple-claim came a `0037` and a `0038` pair, with PR #1114 bringing
`0038_the_keyword_maintenance_is_managed_by_pgtrigger` while PR #1145 brought
`0038_a_harvesting_run_knows_when_it_was_made` - both hanging off the same leaf
`0037_store_the_rows_of_the_alerts`. Neither branch could see it, and every discovery
cost one merge-queue cycle.

The property is one of (branch UNION master), not of either side alone, which is the
same reason this repository keeps `scripts/nginx_routing_smoke.py` and
`scripts/static_mounts_smoke.py`. Django decides a conflict by counting leaf nodes
per app - `MigrationLoader.detect_conflicts` - so that is exactly what is counted
here, in the two seconds a push has.

What it checks
--------------
Per app of `backend/`: the migration files of `--head` (default `HEAD`), of `--base`
(default `origin/master`) and the names of their merge base, listed with `git
ls-tree`; the `dependencies` of each file, read with `ast` out of its `Migration`
class - no import, so no GDAL, no settings, no database and no compose stack. A file
belongs to the tree the queue builds when HEAD carries it, or when only the base
carries it and HEAD did not delete it since the merge base; a file HEAD deleted is
gone, and a file both sides carry is read as HEAD has it.

Edges are the literal `("app", "name")` dependencies. A node nothing depends on is a
leaf, and leaves are counted over the whole graph and grouped by app, because that is
how Django counts them: a migration of `registry` which a migration of `notify`
depends on is not a leaf, and an app whose last migration became somebody else's
parent is not a conflict either. Two leaves of one app is the conflict, and the report
names both with the file declaring each and the side it comes from. `--app` narrows
what is reported, never what is read: the graph has to stay whole for the leaves to be
right.

When it cannot answer, it says so instead of guessing
----------------------------------------------------
A dependency which is not a literal pair of strings - `migrations
.swappable_dependency(settings.AUTH_USER_MODEL)`, which Django resolves to the first
migration of the app owning the user model - cannot be resolved statically. Those are
counted, reported and left out of the graph: they point at the root of another app,
and a root with no other child would be a leaf on its own anyway. A `dependencies`
this parser cannot read at all stops the run with exit 2, because a silently missing
edge is a leaf nobody was asked about.

When to touch this file
-----------------------
A new app with a `migrations` package needs nothing here - the listing finds it. A
`dependencies` written any other way than literal pairs, a squashed history with
`replaces`, or a `run_before` are the shapes whose edges this does not model yet; each
needs the parser extended, not the assertion weakened. Renumbering a leaf is the fix a
reported conflict asks for, and it belongs to the branch whose migration is not in
master yet. The offline checks are `scripts/test_migration_graph_smoke.py` (no docker,
no network, synthetic graphs plus one throw-away git repository).
"""

import argparse
import ast
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

# The apps are <checkout>/backend/<app>/migrations/*.py; nothing else is read.
APPS_ROOT = "backend"
DEFAULT_HEAD = "HEAD"
DEFAULT_BASE = "origin/master"

# Django's loader rule (MigrationLoader.load_disk): a .py of a migrations package
# whose name starts with neither "_" nor "~" is a migration.
IGNORED_PREFIXES = ("_", "~")

# The dependency names which point at a position rather than at a file.
PLACEHOLDERS = ("__first__", "__latest__")

HEAD, BASE = "head", "base"


class HarnessError(Exception):
    """The check could not be run at all - no git, a ref that names no commit, a
    migration file whose dependencies cannot be read. Kept apart from a found second
    leaf, which is a real answer to the question this check asks."""


def repo():
    """The checkout to read. `MIGRATION_GRAPH_SMOKE_REPO` points at another repository
    the way `AGENT_CGROUP_ROOT` points `scripts/agent_capacity` at a fabricated cgroup:
    the offline checks build a throw-away repository holding a two-leaf collision."""
    override = os.environ.get("MIGRATION_GRAPH_SMOKE_REPO")
    return Path(override) if override else Path(__file__).resolve().parent.parent


def git(*args, stdin=b""):
    """git in this checkout and its stdout, or a HarnessError carrying its stderr."""
    try:
        process = subprocess.run(["git", *args], capture_output=True,
                                 cwd=repo(), input=stdin)  # nosec B603 - fixed argv
    except FileNotFoundError:
        raise HarnessError("the git CLI is not on PATH")
    if process.returncode != 0:
        raise HarnessError(
            f"git {' '.join(args)} exited {process.returncode}: "
            f"{process.stderr.decode('utf-8', 'replace').strip()}")
    return process.stdout


def commit_of(ref):
    """The commit a ref names. An unresolvable ref is the harness failing, not the
    graph being fine, so it names the fetch that usually fixes it."""
    try:
        return git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").decode().strip()
    except HarnessError:
        raise HarnessError(
            f"{ref} names no commit in {repo()}"
            + (" - run `git fetch origin` first" if "/" in ref else ""))


def migrations_of(commit):
    """{app: {name: path}} for every migration file a commit carries."""
    listing = git("ls-tree", "-r", "--name-only", "-z", commit,
                  "--", APPS_ROOT).decode("utf-8", "replace")
    found = {}
    for path in listing.split("\0"):
        parts = path.split("/")
        # exactly backend/<app>/migrations/<name>.py, so a nested package or a helper
        # module of a migrations directory is not taken for a migration
        if len(parts) != 4 or parts[2] != "migrations" or not path.endswith(".py"):
            continue
        name = parts[3][:-len(".py")]
        if name.startswith(IGNORED_PREFIXES):
            continue
        found.setdefault(parts[1], {})[name] = path
    return found


def read_blobs(commit, paths):
    """The text of `commit:<path>` for each path, in one `git cat-file --batch`: the
    ~90 files of the two sides are one process, which is what keeps this a push-time
    check instead of a build."""
    if not paths:
        return {}
    out = git("cat-file", "--batch",
              stdin=("\n".join(f"{commit}:{p}" for p in paths) + "\n").encode())
    texts, at = {}, 0
    for path in paths:
        end = out.index(b"\n", at)
        header = out[at:end].decode("utf-8", "replace")
        at = end + 1
        fields = header.split(" ")
        if len(fields) != 3:  # "<spec> missing" for a path the commit does not carry
            raise HarnessError(f"{commit}:{path} could not be read ({header})")
        size = int(fields[2])
        texts[path] = out[at:at + size].decode("utf-8", "replace")
        at += size + 1  # the object, then the newline git puts behind it
    return texts


def literal_dependency(element):
    """`('registry', '0037_...')` as a pair, or None for anything else."""
    if (isinstance(element, ast.Tuple) and len(element.elts) == 2
            and all(isinstance(e, ast.Constant) and isinstance(e.value, str)
                    for e in element.elts)):
        return tuple(e.value for e in element.elts)
    return None


def dependencies_of(text, where):
    """The `Migration.dependencies` of one file as ((app, name), ...), plus the entries
    which are not a literal pair of strings and so cannot be resolved here."""
    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        raise HarnessError(f"{where} does not parse: {error}")
    deps, opaque = [], []
    for class_ in [node for node in tree.body
                   if isinstance(node, ast.ClassDef) and node.name == "Migration"]:
        for statement in class_.body:
            if not (isinstance(statement, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "dependencies"
                            for t in statement.targets)):
                continue
            if not isinstance(statement.value, (ast.List, ast.Tuple)):
                raise HarnessError(
                    f"{where}: `dependencies` is a {type(statement.value).__name__}, "
                    f"not a list of literal pairs this guard can read")
            for element in statement.value.elts:
                dependency = literal_dependency(element)
                if dependency is None:
                    opaque.append(ast.unparse(element))
                else:
                    deps.append(dependency)
    return deps, opaque


def queue_files(head, base, merge):
    """{(app, name): {"side", "path", "sides"}} of the tree the merge queue builds.

    The three arguments are the `{app: {name: path}}` listings of the head commit, of
    the base commit and of their merge base; `side` says which commit's copy of the
    file to read ("head" wins where both carry it, because that is what a merge keeps
    from the branch), and `sides` says which of the two refs a reader will find the
    file in. The merge base is here for one decision only: a file HEAD deleted is gone
    from the queue's tree, while a file only the base carries is one master added after
    this branch split off and is really there. Reading the base for both cases would
    turn a deleted migration into a leaf that exists nowhere.
    """
    chosen = {}
    for app in sorted(set(head) | set(base)):
        in_head, in_base = head.get(app, {}), base.get(app, {})
        in_merge = merge.get(app, {})
        for name in sorted(set(in_head) | set(in_base)):
            if name in in_head:
                side, path = HEAD, in_head[name]
            elif name in in_merge:
                continue
            else:
                side, path = BASE, in_base[name]
            chosen[(app, name)] = {
                "side": side, "path": path,
                "sides": [label for label, listing in ((HEAD, in_head), (BASE, in_base))
                          if name in listing],
            }
    return chosen


def collect(head_ref, base_ref):
    """({(app, name): node}, {head, base, merge_base}) of the queue's tree. A node is
    {"app", "name", "path", "sides", "deps", "opaque"}."""
    head, base = commit_of(head_ref), commit_of(base_ref)
    merge = git("merge-base", head, base).decode().strip()
    trees = {head: migrations_of(head), base: migrations_of(base),
             merge: migrations_of(merge)}
    labels = {HEAD: head_ref, BASE: base_ref}
    chosen = queue_files(trees[head], trees[base], trees[merge])

    nodes, needed, source = {}, defaultdict(list), {}
    for key, info in chosen.items():
        commit = head if info["side"] == HEAD else base
        nodes[key] = {"app": key[0], "name": key[1], "path": info["path"],
                      "sides": [labels[s] for s in info["sides"]],
                      "deps": [], "opaque": []}
        needed[commit].append(info["path"])
        source[(commit, info["path"])] = key

    for commit, paths in needed.items():
        for path, text in read_blobs(commit, paths).items():
            deps, opaque = dependencies_of(text, f"{labels[HEAD if commit == head else BASE]}:"
                                                 f"{path}")
            nodes[source[(commit, path)]]["deps"] = deps
            nodes[source[(commit, path)]]["opaque"] = opaque
    return nodes, {"head": head, "base": base, "merge_base": merge}


def leaf_nodes(nodes):
    """Every node nothing depends on, as Django's `MigrationGraph.leaf_nodes` hands
    them out - cross-app edges included, because Django groups these by app."""
    depended_on = {dep for node in nodes.values()
                   for dep in node["deps"] if dep in nodes}
    return sorted(key for key in nodes if key not in depended_on)


def dangling(nodes):
    """Literal dependencies on a migration of an app this guard reads which neither
    side carries. Django refuses those as well (`NodeNotFoundError` while building the
    graph), and a graph with a hole in it has no trustworthy leaf. The placeholder names
    are excluded: `__first__` names no file, and Django itself ignores it when it points
    at the same app (#22325)."""
    apps = {app for app, _ in nodes}
    return sorted((key, dep) for key, node in nodes.items() for dep in node["deps"]
                  if dep not in nodes and dep[0] in apps and dep[1] not in PLACEHOLDERS)


def cyclic(nodes):
    """True when nothing is a leaf, which for a finite graph means a cycle. Django's
    own answer to that is `CircularDependencyError`."""
    return bool(nodes) and not leaf_nodes(nodes)


def next_number(numbers):
    """The number a renumbered leaf would carry, or None when the names do not follow
    the four-digit convention this suggests a name from."""
    if numbers and all(n.isdigit() for n in numbers):
        return f"{max(int(n) for n in numbers) + 1:04d}"
    return None


def how_many(count, word):
    """`3 migrations` / `1 migration` - the count is never reworded away."""
    return f"{count} {word}" + ("" if count == 1 else "s")


def verdict(nodes, leaves, reported):
    """(lines, conflicts): the leaf of every app, and the answer a conflict owes - both
    leaves, their files, the side each comes from, and the fix Django itself names.
    `--app` filters the green lines only: an app which is not reported but does have a
    second leaf is still printed and still named in `conflicts`, because the queue does
    not care which app somebody meant to look at."""
    lines, conflicts = [], []
    by_app = defaultdict(list)
    for app, name in leaves:
        by_app[app].append(name)
    for app in sorted({key[0] for key in nodes}):
        migrations = [key for key in nodes if key[0] == app]
        app_leaves = by_app.get(app, [])
        if len(app_leaves) <= 1:
            if app not in reported:
                continue
            # No leaf of its own is not a conflict: the last migration of this app is
            # a parent of a migration of another one, and Django counts those as the
            # other app's leaf.
            leaf = (f"one leaf: {app_leaves[0]}" if app_leaves
                    else "no leaf of its own: its last one is another app's parent")
            lines.append(f"  ok    {app:<10} {how_many(len(migrations), 'migration'):>15}, "
                         f"{leaf}")
            continue
        conflicts.append(app)
        numbers = [name.split("_", 1)[0] for name in app_leaves]
        lines.append(f"  FAIL  {app:<10} {how_many(len(migrations), 'migration'):>15}, "
                     f"{len(app_leaves)} leaves:")
        for name in app_leaves:
            node = nodes[(app, name)]
            lines.append(f"        {app}/{name}\n"
                         f"          declared by {node['path']} "
                         f"({' + '.join(node['sides'])})")
        shared = sorted({n for n in numbers if numbers.count(n) > 1})
        if shared:
            lines.append(f"        both carry the number {' and '.join(shared)}: the "
                         f"same slot claimed by two branches")
        lines.append(f"        makemigrations answers for the merge queue: \"Conflicting "
                     f"migrations detected; multiple leaf nodes in the migration graph: "
                     f"({', '.join(app_leaves)} in {app}).\"")
        renamed = next_number(numbers)
        lines.append(f"        fix: the branch whose migration master does not carry yet "
                     f"renumbers it to {app}/{renamed or 'N'}_<topic> and depends on the "
                     f"leaf the other side brings")
    return lines, conflicts


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="migration_graph_smoke", description=__doc__.splitlines()[0],
        epilog="exit 0 one leaf per app, 1 an app with more than one, 2 the harness "
               "could not run")
    parser.add_argument("--head", default=DEFAULT_HEAD,
                        help="the branch to check (default HEAD)")
    parser.add_argument("--base", default=DEFAULT_BASE,
                        help=f"the ref it is merged into (default {DEFAULT_BASE})")
    parser.add_argument("--app", action="append", dest="apps", metavar="APP",
                        help="report only this app, repeatable; every app of "
                             f"{APPS_ROOT}/ is reported by default. Only the report is "
                             "narrowed, never the graph")
    parser.add_argument("--json", action="store_true",
                        help="the verdict as one JSON object")
    args = parser.parse_args(argv)

    try:
        nodes, commits = collect(args.head, args.base)
        if not nodes:
            raise HarnessError(f"no migration found under {APPS_ROOT}/ of "
                               f"{args.head} or {args.base} - run this from a "
                               f"mrmap checkout")
        leaves, holes = leaf_nodes(nodes), dangling(nodes)
        by_app = defaultdict(list)
        for app, name in leaves:
            by_app[app].append(name)
        reported = args.apps or sorted({app for app, _ in nodes})
        unknown = [app for app in reported if not any(k[0] == app for k in nodes)]
        lines, conflicts = verdict(nodes, leaves, reported)
        cycle = cyclic(nodes)
        unresolved = sum(len(node["opaque"]) for node in nodes.values())
        ok = not conflicts and not holes and not cycle and not unknown
    except HarnessError as error:
        print(f"migration_graph_smoke: cannot run: {error}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({
            "head": commits["head"], "base": commits["base"],
            "merge_base": commits["merge_base"], "migrations": len(nodes),
            "unresolved_dependencies": unresolved,
            "cyclic": cycle,
            "apps": [{"app": app,
                      "migrations": sum(1 for key in nodes if key[0] == app),
                      "leaves": [{"name": name, "path": nodes[app, name]["path"],
                                  "sides": nodes[app, name]["sides"]}
                                 for name in by_app.get(app, [])],
                      "ok": len(by_app.get(app, [])) <= 1} for app in reported],
            "dangling": [[f"{a}/{n}", f"{da}/{dn}"]
                         for (a, n), (da, dn) in holes],
            "ok": ok,
        }))
        return 0 if ok else 1

    print(f"migration_graph_smoke: {args.head} ({commits['head'][:8]}) + "
          f"{args.base} ({commits['base'][:8]}), merge base "
          f"{commits['merge_base'][:8]}, {len(nodes)} migrations read")
    for line in lines:
        print(line)
    for app in unknown:
        print(f"  FAIL  {app}: no migrations of that app under {APPS_ROOT}/")
    for (app, name), (dep_app, dep_name) in holes:
        print(f"  FAIL  {app}/{name} depends on {dep_app}/{dep_name}, which neither "
              f"{args.head} nor {args.base} carries")
    if cycle:
        print("  FAIL  nothing is a leaf: the graph of these files has a cycle")
    if unresolved:
        print(f"  note  {unresolved} dependency(ies) which are not literal pairs "
              f"(migrations.swappable_dependency and friends) could not be resolved "
              f"here and are not edges")

    problems = []
    if conflicts:
        problems.extend(f"{app} has {len(by_app[app])} leaves" for app in conflicts)
    if holes:
        problems.append(f"{how_many(len(holes), 'hole')} in the graph")
    if cycle:
        problems.append("a cycle")
    if unknown:
        problems.append("no app named " + " and ".join(unknown)
                        + f" under {APPS_ROOT}/")
    if problems:
        print("migration_graph_smoke: the merge queue would not accept this graph - "
              + ", ".join(problems))
        return 1
    print("migration_graph_smoke: one leaf per app - the queue's makemigrations "
          "will not see a conflict")
    return 0


if __name__ == "__main__":
    sys.exit(main())
