#!/usr/bin/env python3
"""Fail the tree for a bare lxml parse call in the backend (#1468).

lxml resolves entities and follows network references by default, so an XML
document which an external side wrote can read a local file of the deployment
and echo its content back, and a declaration which expands itself grows until
the worker is gone. The policy lives in ``backend/registry/helper/xml.py``: an
externally written document parses with ``parse_untrusted()``, a document this
deployment wrote itself with ``parse_trusted()``. A bare ``etree.fromstring``
or ``etree.parse`` is what the policy forbids, because it is the default parser
in disguise and is invisible in a review next to a hardened call.

Why a host-side script and not a flake8 plugin: the repo runs flake8 with no
plugins installed and adds no dependency for one check, which is why
``scripts/orm_lint.py`` and ``scripts/pr_classify`` exist for their own rules.
``scripts/git_checks.py`` runs this guard in the pre-commit and pre-push hooks
and ``scripts/check_repo_tooling.sh`` runs its suite in CI's Script tests job,
both on a plain checkout.

Reading, not importing: the backend is not importable on a host without GDAL
(``MrMap/settings.py`` calls ``gdal_info()``), so the guard parses sources with
``ast`` and never imports them.

Usage::

    python3 scripts/xml_parse_guard.py              # check the tree, quiet on success
    python3 scripts/xml_parse_guard.py --audit      # every site and its decision
    python3 scripts/xml_parse_guard.py --root DIR   # check another checkout

Exit code 0 means no violation, 1 names every violation.
"""
import argparse
import ast
import os
from pathlib import Path
import subprocess
import sys

#: where the swept code lives, relative to the repository root
SWEEP_ROOT = "backend"
#: the one module allowed to hold a bare parse call
POLICY_MODULE = os.path.join("backend", "registry", "helper", "xml.py")
#: the calls which need the policy; lxml's other readers build trees itself
PARSE_FUNCTIONS = ("fromstring", "parse")
#: a deliberate exception carries this marker plus a reason on the line
WAIVER = "NOSONAR"
#: test code builds its own documents and asserts on the parser, so it states
#: nothing; it is reported but never a violation
TEST_MARKER = os.sep + "tests" + os.sep


def tracked_python(root):
    """Paths of the swept python files, relative to ``root``.

    ``git ls-files`` is the file list, so an untracked scratch file is not
    checked and a deleted one is not reported. Without git (an exported
    snapshot is always a git checkout here, but the suite passes a plain
    directory) the sweep walks the tree instead.
    """
    try:
        listing = subprocess.run(
            ["git", "ls-files", "-z", "--", SWEEP_ROOT],
            cwd=root, capture_output=True, check=True).stdout.decode()
    except (OSError, subprocess.CalledProcessError):
        listing = ""
    if listing:
        return sorted(name for name in listing.split("\0")
                      if name.endswith(".py") and (root / name).is_file())
    base = Path(root) / SWEEP_ROOT
    return sorted(str(path.relative_to(root)) for path in base.rglob("*.py"))


def resolve_lxml(tree):
    """The local names this module reaches lxml through.

    ``from lxml import etree``, ``import lxml.etree`` and ``from lxml.etree
    import fromstring`` all appear in the backend, so the guard resolves the
    bound names instead of matching the text ``etree.`` and missing an alias.

    Answers ``(etree_names, lxml_names, imported)``: the names bound to the
    ``etree`` module itself, the names bound to ``lxml`` (reached as
    ``lxml.etree``), and the parse functions imported by name.
    """
    etree_names = set()
    lxml_names = set()
    imported = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "lxml":
            if node.module in ("lxml.etree", "lxml"):
                for item in node.names:
                    if item.name == "etree" and node.module == "lxml":
                        etree_names.add(item.asname or "etree")
                    elif item.name in PARSE_FUNCTIONS:
                        imported[item.asname or item.name] = item.name
            continue
        if isinstance(node, ast.Import):
            for item in node.names:
                if item.name == "lxml.etree" or item.name.endswith(".etree"):
                    # binds the top package, reached as `lxml.etree.parse`
                    lxml_names.add(item.asname or item.name.split(".")[0])
                elif item.name == "lxml":
                    lxml_names.add(item.asname or "lxml")
    return etree_names, lxml_names, imported


def parse_function(func, etree_names, lxml_names, imported):
    """The parse function of a call's ``func`` node, or ``None``.

    ``func`` is what ``ast.Call.func`` holds, so a dotted chain is looked at as
    written rather than as the call around it.
    """
    node = func
    if isinstance(node, ast.Attribute) and node.attr in PARSE_FUNCTIONS:
        base = node.value
        if isinstance(base, ast.Name) and base.id in etree_names:
            return node.attr
        # lxml.etree.fromstring(...) after "import lxml.etree"
        if isinstance(base, ast.Attribute) and base.attr == "etree" \
                and isinstance(base.value, ast.Name) \
                and base.value.id in lxml_names:
            return node.attr
        return None
    if isinstance(node, ast.Name) and node.id in imported:
        return imported[node.id]
    return None


def passes_a_parser(call):
    """True when the call hands lxml a parser instead of using the default.

    The guard asks for an argument and not for the value of its options:
    reading ``resolve_entities=False`` out of a call needs a constant fold
    which breaks on any parser built somewhere else, and the point of the rule
    is that the policy is not spelled out per site. A parser the sites may
    pass comes from ``hardened_parser()`` in the policy module.
    """
    return len(call.args) > 1 or any(
        keyword.arg == "parser" for keyword in call.keywords)


def scan_file(relative, source):
    """Every parse site of one module, each with how it passes the policy."""
    tree = ast.parse(source, filename=relative)
    etree_names, lxml_names, imported = resolve_lxml(tree)
    if not (etree_names or lxml_names or imported):
        return []
    lines = source.splitlines()
    sites = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = parse_function(node.func, etree_names, lxml_names, imported)
        if function is None:
            continue
        text = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""
        if TEST_MARKER in relative:
            verdict = "test code"
        elif os.path.normpath(relative) == os.path.normpath(POLICY_MODULE):
            verdict = "the policy module"
        elif WAIVER in text:
            verdict = "waived on the line"
        elif passes_a_parser(node):
            verdict = "parser argument"
        else:
            verdict = ""
        sites.append({
            "path": relative,
            "line": node.lineno,
            "call": function,
            "verdict": verdict,
            "text": text,
        })
    return sites


def scan(root):
    """Every parse site below ``root``/``backend``, sorted by path and line."""
    sites = []
    for relative in tracked_python(root):
        source = (root / relative).read_text(encoding="utf-8")
        try:
            sites.extend(scan_file(relative, source))
        except SyntaxError as error:
            raise RuntimeError(
                f"xml parse guard can not read {relative}: {error}") from error
    return sites


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=None,
                        help="checkout to check (default: the git root of cwd)")
    parser.add_argument("--audit", action="store_true",
                        help="print every parse site with its decision")
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else Path(subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=Path.cwd(),
        capture_output=True, check=True).stdout.decode().strip())

    sites = scan(root)
    bad = [site for site in sites if not site["verdict"]]

    if args.audit:
        for site in sites:
            flag = site["verdict"] or "VIOLATION"
            print(f"{flag:18s} {site['path']}:{site['line']}"
                  f"  etree.{site['call']}()  | {site['text']}")
    print(f"xml parse guard: {len(sites)} parse site(s), {len(bad)} violation(s)")
    if bad:
        for site in bad:
            print(f"  {site['path']}:{site['line']}: etree.{site['call']}() "
                  "uses the default parser", file=sys.stderr)
        print("Read a document an external side wrote with "
              "registry.helper.xml.parse_untrusted() and one this deployment "
              "wrote itself with parse_trusted(); a deliberate exception needs "
              "a NOSONAR comment with the reason on the line. Policy: "
              "backend/registry/helper/xml.py (#1468).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
