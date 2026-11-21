#!/usr/bin/env python3
"""Offline tests for scripts/xml_parse_guard.py and its hook wiring (#1468).

Run from the repository root:  python3 scripts/test_xml_parse_guard.py

The guard is exercised through its real entry point against a synthetic
mini-repository in a temporary directory: the shapes the backend actually
carries (``from lxml import etree``, ``import lxml.etree``,
``from lxml.etree import fromstring``), the hardened calls the policy asks for,
the waiver marker and the test-code exemption. The wiring inside
``scripts/git_checks.py`` is tested the same way, against real Git trees,
because the guard reads the *committed* tree and not the working directory. The
real repository is checked too: the migration #1468 performed must stay
complete at HEAD.

Nothing here needs docker, Django, GDAL, a database or the network; the fixture
code is parsed, never imported.

Exit code 0 = all ran checks passed.
"""

import importlib.util
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

_spec = importlib.util.spec_from_file_location("xml_parse_guard", SCRIPTS / "xml_parse_guard.py")
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

_spec2 = importlib.util.spec_from_file_location("git_checks", SCRIPTS / "git_checks.py")
hooks = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(hooks)

RESULTS = []

#: what the XXE canary reads if a parser resolves entities
CANARY_MARKER = "XXE-CANARY-CONTENT"
#: what an expanded self-declaration repeats
EXPANSION_MARKER = "expanded"
#: an external document which reads a local file through a SYSTEM entity;
#: ``%s`` is filled with the file:// URI of a marker file the test creates
XXE_DOCUMENT = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE root [ <!ENTITY xxe SYSTEM "%s"> ]>
<root>&xxe;</root>
"""

#: a declaration which expands itself several times, which grows quadratically
BOMB_DOCUMENT = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE root [
<!ENTITY a "&b;&b;&b;">
<!ENTITY b "&c;&c;&c;">
<!ENTITY c "&d;&d;&d;">
<!ENTITY d "&e;&e;&e;">
<!ENTITY e "&f;&f;&f;">
<!ENTITY f "&g;&g;&g;">
<!ENTITY g "%s">
]>
<root>&a;</root>
""" % EXPANSION_MARKER

#: filled by main(), so the module imports on a runner without lxml
etree = None


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))


def run_guard(root, *args):
    """The guard's own exit code and output for a checkout."""
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "xml_parse_guard.py"), "--root", str(root), *args],
        capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def write(root, relative, content):
    path = Path(root) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True,
                          text=True, check=True).stdout.strip()


def make_repo(tmp):
    """A checkout holding the guard and the helper, so both stages can run."""
    root = Path(tmp) / "repo"
    root.mkdir()
    git(root, "init", "-q", "--initial-branch=master")
    git(root, "config", "user.email", "guard@example.com")
    git(root, "config", "user.name", "Guard tests")
    git(root, "config", "commit.gpgsign", "false")
    (root / "scripts").mkdir()
    shutil.copy2(SCRIPTS / "xml_parse_guard.py", root / "scripts/xml_parse_guard.py")
    write(root, guard.POLICY_MODULE, "def parse_untrusted(content):\n    pass\n")
    return root


def commit_all(root):
    git(root, "add", "-A")
    git(root, "commit", "-qm", "fixture")
    return git(root, "rev-parse", "HEAD")


BARE = "from lxml import etree\n\n\ndef read(content):\n    return etree.fromstring(content)\n"
HARDENED = ("from lxml import etree\n"
            "from registry.helper.xml import parse_untrusted\n\n\n"
            "def read(content):\n    return parse_untrusted(content)\n")


def test_guard_fails_a_bare_default_parse():
    with tempfile.TemporaryDirectory(prefix="mrmap-xml-guard-") as tmp:
        root = make_repo(tmp)
        write(root, "backend/registry/views/bad.py", BARE)
        code, out = run_guard(root)
        check("guard fails a bare etree.fromstring", code == 1, out)
        check("guard names the violating file and line",
              "backend/registry/views/bad.py:5" in out, out)
        check("guard names the function it refuses",
              "etree.fromstring() uses the default parser" in out, out)


def test_guard_accepts_the_policy_calls():
    with tempfile.TemporaryDirectory(prefix="mrmap-xml-guard-") as tmp:
        root = make_repo(tmp)
        write(root, "backend/registry/views/good.py", HARDENED)
        code, out = run_guard(root)
        check("parse_untrusted passes the guard", code == 0, out)


def test_guard_accepts_an_explicit_parser():
    with tempfile.TemporaryDirectory(prefix="mrmap-xml-guard-") as tmp:
        root = make_repo(tmp)
        write(root, "backend/a.py",
              "from lxml import etree\nfrom registry.helper.xml import hardened_parser\n"
              "\n\ndef read(content):\n"
              "    return etree.fromstring(content, parser=hardened_parser())\n")
        code, out = run_guard(root)
        check("a passed parser passes the guard", code == 0, out)
        write(root, "backend/a.py",
              "from lxml import etree\nfrom registry.helper.xml import hardened_parser\n"
              "\n\ndef read(content):\n"
              "    return etree.parse(content, hardened_parser())\n")
        code, out = run_guard(root)
        check("a positional parser passes the guard for etree.parse", code == 0, out)


def test_guard_reads_aliases():
    cases = {
        "import lxml.etree": ("import lxml.etree\n\n\ndef read(c):\n"
                              "    return lxml.etree.parse(c)\n", "etree.parse()"),
        "from lxml.etree import fromstring": (
            "from lxml.etree import fromstring\n\n\ndef read(c):\n"
            "    return fromstring(c)\n", "etree.fromstring()"),
        "aliased import": ("from lxml import etree as xml\n\n\ndef read(c):\n"
                           "    return xml.fromstring(c)\n", "etree.fromstring()"),
    }
    with tempfile.TemporaryDirectory(prefix="mrmap-xml-guard-") as tmp:
        root = make_repo(tmp)
        for name, (source, _) in cases.items():
            write(root, "backend/alias.py", source)
            code, out = run_guard(root)
            check(f"guard reads the import shape: {name}", code == 1, out)


def test_guard_ignores_unrelated_calls():
    source = ("from lxml import etree\n\n\n"
              "def read(c):\n"
              "    # not a reader: a builder, a serializer and a string helper\n"
              "    etree.SubElement(c, 'x')\n"
              "    etree.tostring(c)\n"
              "    etree.indent(c)\n"
              "    return etree.QName(c)\n")
    with tempfile.TemporaryDirectory(prefix="mrmap-xml-guard-") as tmp:
        root = make_repo(tmp)
        write(root, "backend/builder.py", source)
        code, out = run_guard(root)
        check("lxml's other functions are no parse sites",
              code == 0 and "0 parse site(s)" in out, out)


def test_guard_waives_a_line_with_a_reason():
    with tempfile.TemporaryDirectory(prefix="mrmap-xml-guard-") as tmp:
        root = make_repo(tmp)
        write(root, "backend/waived.py",
              "from lxml import etree\n\n\ndef read(c):\n"
              "    return etree.fromstring(c)  # NOSONAR shipped schema\n")
        code, out = run_guard(root)
        check("a NOSONAR waiver passes", code == 0, out)


def test_guard_reports_test_code_but_never_fails_it():
    with tempfile.TemporaryDirectory(prefix="mrmap-xml-guard-") as tmp:
        root = make_repo(tmp)
        write(root, "backend/tests/django/registry/tests_x.py", BARE)
        code, out = run_guard(root)
        check("test code is never a violation", code == 0, out)
        check("test code is still reported in the audit",
              "test code" in run_guard(root, "--audit")[1], out)


def test_policy_module_may_hold_the_bare_call():
    with tempfile.TemporaryDirectory(prefix="mrmap-xml-guard-") as tmp:
        root = make_repo(tmp)
        write(root, guard.POLICY_MODULE,
              '"""policy"""\nfrom lxml import etree\n\n\n'
              "def parse_untrusted(content):\n    return etree.fromstring(content)\n")
        code, out = run_guard(root)
        check("the policy module is exempt", code == 0, out)


def test_guard_only_sweeps_tracked_files():
    with tempfile.TemporaryDirectory(prefix="mrmap-xml-guard-") as tmp:
        root = make_repo(tmp)
        write(root, "backend/tracked.py", BARE)
        commit_all(root)
        write(root, "backend/scratch.py", BARE)
        code, out = run_guard(root)
        check("an untracked scratch file is not judged", "1 parse site(s)" in out, out)
        check("a tracked violation still fails", code == 1, out)


def test_guard_survives_a_broken_file_with_a_named_fault():
    with tempfile.TemporaryDirectory(prefix="mrmap-xml-guard-") as tmp:
        root = make_repo(tmp)
        write(root, "backend/broken.py", "def read(:\n")
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "xml_parse_guard.py"), "--root", str(root)],
            capture_output=True, text=True)
        check("an unreadable module names itself instead of a traceback guess",
              "backend/broken.py" in (result.stdout + result.stderr)
              and result.returncode != 0,
              (result.stdout + result.stderr)[-300:])


def test_real_repository_is_clean():
    code, out = run_guard(ROOT)
    check("the repository's own tree stays clean at HEAD", code == 0, out.strip())
    reported = re.search(r"(\d+) parse site", out)
    check("the sweep actually sees the migrated parse sites",
          reported is not None and int(reported.group(1)) > 50, out.strip())


def test_guard_paths_is_the_backend_code_list_for_both_stages():
    paths = ["backend/registry/views.py", "backend/AGENTS.md", "backend/README.rst",
             "frontend/src/App.tsx", "scripts/wip", "docs/x.rst"]
    # one list for both stages: the push stage used to get a bool here and the
    # caller iterated it, which killed every backend push with a TypeError
    selected = hooks.xml_guard_paths(paths)
    check("xml_guard_paths returns the backend code list",
          isinstance(selected, list) and selected == ["backend/registry/views.py"],
          repr(selected))
    check("xml_guard_paths is iterable for a push",
          list(hooks.xml_guard_paths(paths)) == ["backend/registry/views.py"],
          repr(selected))
    check("xml_guard_paths keeps a deletion",
          hooks.xml_guard_paths(["backend/deleted.py"]) == ["backend/deleted.py"])
    check("xml_guard_paths is empty for a docs-only change",
          hooks.xml_guard_paths(["docs/x.rst"]) == [])


def test_push_stage_runs_the_guard_and_survives_a_backend_push():
    """The pre-push path must run the guard rather than crash on the path list.

    A first version handed the push stage a bool and iterated it, which killed
    every backend push with a TypeError before any check could report.
    """
    with tempfile.TemporaryDirectory(prefix="mrmap-xml-guard-") as tmp:
        root = make_repo(tmp)
        write(root, "backend/good.py", HARDENED)
        base = commit_all(root)
        write(root, "backend/good.py", HARDENED + "\n# touched\n")
        head = commit_all(root)
        try:
            hooks.check_xml_parse_policy(root, "push", head, ["backend/good.py"])
            check("a clean backend push runs the guard without error", True)
        except TypeError as error:
            check("a clean backend push runs the guard without error", False, repr(error))
        assert base != head
        # now a violating push: the guard must stop it
        write(root, "backend/bad.py", BARE)
        head = commit_all(root)
        try:
            hooks.check_xml_parse_policy(root, "push", head, ["backend/good.py", "backend/bad.py"])
            check("a violating backend push is refused", False, "no error raised")
        except subprocess.CalledProcessError as error:
            check("a violating backend push is refused",
                  "xml_parse_guard.py" in " ".join(str(a) for a in error.cmd),
                  str(error.cmd))


def test_commit_stage_judges_the_index_not_the_worktree():
    with tempfile.TemporaryDirectory(prefix="mrmap-xml-guard-") as tmp:
        root = make_repo(tmp)
        write(root, "backend/one.py", HARDENED)
        commit_all(root)
        # staged: hardened. working tree: bare. The commit must pass.
        write(root, "backend/one.py", HARDENED)
        git(root, "add", "backend/one.py")
        write(root, "backend/one.py", BARE)
        try:
            hooks.check_xml_parse_policy(root, "commit", None, ["backend/one.py"])
            check("the staged content is what gets judged", True)
        except subprocess.CalledProcessError as error:
            check("the staged content is what gets judged", False, str(error.cmd))
        # the other way round: a staged violation is refused although the
        # working tree looks clean
        write(root, "backend/one.py", BARE)
        git(root, "add", "backend/one.py")
        write(root, "backend/one.py", HARDENED)
        try:
            hooks.check_xml_parse_policy(root, "commit", None, ["backend/one.py"])
            check("a staged violation is refused even with a clean worktree", False,
                  "no error raised")
        except subprocess.CalledProcessError:
            check("a staged violation is refused even with a clean worktree", True)


def test_commit_stage_keeps_a_staged_deletion():
    """Removing the last hardened call of a module is what the guard must see."""
    with tempfile.TemporaryDirectory(prefix="mrmap-xml-guard-") as tmp:
        root = make_repo(tmp)
        write(root, "backend/gone.py", BARE)
        commit_all(root)
        (root / "backend/gone.py").unlink()
        git(root, "add", "-A")
        try:
            hooks.check_xml_parse_policy(root, "commit", None, ["backend/gone.py"])
            check("a staged deletion is judged and cannot smuggle a violation", True)
        except subprocess.CalledProcessError as error:
            check("a staged deletion is judged and cannot smuggle a violation", False,
                  str(error.cmd))


def test_guard_without_the_script_is_skipped_not_fatal():
    with tempfile.TemporaryDirectory(prefix="mrmap-xml-guard-") as tmp:
        root = Path(tmp) / "old"
        root.mkdir()
        git(root, "init", "-q")
        try:
            hooks.check_xml_parse_policy(root, "commit", None, ["backend/a.py"])
            check("a branch without the guard skips the check", True)
        except Exception as error:
            check("a branch without the guard skips the check", False, repr(error))


def test_hardened_parser_refuses_a_live_xxe_canary():
    """The hardened options must refuse a document that really can read a file.

    The canary names a marker file which exists. The negative control parses
    the same document with ``load_dtd=True, resolve_entities=True``, the option
    pair which actually reads the file on the libxml2 shipping with the pinned
    lxml: measured here, plain ``etree.XMLParser()`` refuses the declaration
    with "Entity 'xxe' not defined" because its own ``load_dtd`` default never
    reads the internal subset. Asserting against the defaults instead would
    compare two refusals and stay green even if the hardened options were
    dropped, so the control names the settings that genuinely leak.
    """
    if etree is None:
        return  # skipped by main() without lxml
    parser = hardened_options_parser()
    with tempfile.TemporaryDirectory(prefix="mrmap-xml-canary-") as tmp:
        secret = Path(tmp) / "canary-secret.txt"
        secret.write_text(CANARY_MARKER, encoding="utf-8")
        document = (XXE_DOCUMENT % secret.as_uri()).encode()
        leaking = etree.tostring(
            etree.fromstring(document, parser=etree.XMLParser(
                load_dtd=True, resolve_entities=True)),
            encoding="unicode")
        check("the XXE canary is live for an entity-expanding parser",
              CANARY_MARKER in leaking,
              "the canary document did not read the file, so the hardened "
              "assertion below proves nothing")
        hardened = etree.fromstring(document, parser=parser)
        surfaces = [_xml(hardened), repr([element.text for element in hardened]),
                    "".join(hardened.itertext())]
        check("the hardened parser keeps the file out of the tree and its text",
              all(CANARY_MARKER not in surface for surface in surfaces),
              surfaces[0][:200])
        check("the hardened parser answers the declared element",
              hardened.tag == "root", surfaces[0][:200])


def test_hardened_parser_refuses_an_expansion_bomb():
    """A self-expanding declaration must not be expanded into the tree.

    Observed through the tree and its XML serialization, which is what the
    backend reads. ``tostring(method="text")`` is deliberately not the surface:
    libxml2 re-expands entity references while serializing text even from a
    tree it refused to expand, and no backend site uses that method (checked by
    ``test_no_backend_site_serializes_with_method_text``).
    """
    if etree is None:
        return  # skipped by main() without lxml
    parser = hardened_options_parser()
    expanded = _xml(etree.fromstring(BOMB_DOCUMENT.encode(), parser=etree.XMLParser()))
    check("the expansion canary is live under lxml's defaults",
          expanded.count(EXPANSION_MARKER) > 100, "count=%d" % expanded.count(EXPANSION_MARKER))
    hardened = etree.fromstring(BOMB_DOCUMENT.encode(), parser=parser)
    check("the hardened parser does not expand the self-declared entity",
          EXPANSION_MARKER not in _xml(hardened)
          and EXPANSION_MARKER not in "".join(hardened.itertext()),
          _xml(hardened)[:200])


def test_no_backend_site_serializes_with_method_text():
    """``method="text"`` re-expands entity nodes, so no site may read XML that way.

    A measured parser behaviour rather than a style rule: the hardened tree
    holds ``&a;`` unexpanded, but serializing it as text makes libxml2 expand
    the declaration at serialization time, which would undo the policy for the
    one call shape that does it.
    """
    hits = [str(path.relative_to(ROOT)) + ":"
            + str(number) for path in (ROOT / "backend").rglob("*.py")
            for number, line in enumerate(path.read_text(encoding="utf-8",
                                                         errors="replace").splitlines(), 1)
            if "method=" in line and "text" in line.split("method=")[-1]]
    check("no backend module serializes with method=text", not hits, ", ".join(hits[:5]))


def test_text_serialization_is_why_no_site_may_use_it():
    """Keeps the reason of the check above true.

    Text serialization re-expands an internal declaration which the hardened
    option pair refused, while a SYSTEM literal stays unfetched there too. Both
    halves are measured, because the refusal of the tree is only justified while
    the behaviour is real - and it is the *text* method, not the hardened parse,
    which decides whether an internal entity is expanded.
    """
    if etree is None:
        return  # skipped by main() without lxml
    internal = ('<?xml version="1.0"?>\n'
                '<!DOCTYPE root [ <!ENTITY a "&b;&b;"> <!ENTITY b "B"> ]>\n'
                '<root>&a;</root>\n')
    hardened = etree.fromstring(internal.encode(),
                                parser=hardened_options_parser())
    check("a hardened tree keeps an internal declaration unexpanded",
          "BB" not in _xml(hardened) and "BB" not in "".join(hardened.itertext()),
          _xml(hardened))
    check("serializing that tree as text expands the declaration anyway",
          etree.tostring(hardened, encoding="unicode", method="text") == "BB",
          "the text method no longer expands, so its refusal needs a new reason")

    with tempfile.TemporaryDirectory(prefix="mrmap-xml-canary-") as tmp:
        secret = Path(tmp) / "canary-secret.txt"
        secret.write_text(CANARY_MARKER, encoding="utf-8")
        external = etree.fromstring((XXE_DOCUMENT % secret.as_uri()).encode(),
                                    parser=hardened_options_parser())
        check("text serialization does not fetch a SYSTEM literal either",
              CANARY_MARKER not in etree.tostring(
                  external, encoding="unicode", method="text"),
              "a SYSTEM literal reached the text of a hardened document")


def _xml(element):
    return etree.tostring(element, encoding="unicode")


def hardened_options_parser():
    """The option set of the policy module, applied to a real lxml parser.

    The backend can not be imported on a host without GDAL, so the options are
    read out of the policy module's source as a literal and handed to lxml here;
    the Django spec ``tests/django/registry/tests_xml_parse_policy.py`` asserts
    the same behaviour through the imported factory.
    """
    import ast
    source = (ROOT / guard.POLICY_MODULE).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Assign) and any(
                getattr(target, "id", "") == "HARDENED_OPTIONS" for target in node.targets):
            return etree.XMLParser(**ast.literal_eval(node.value))
    raise AssertionError("HARDENED_OPTIONS is not a literal in the policy module")


def main():
    global etree
    try:
        from lxml import etree as _lxml_etree
    except ImportError:
        check("lxml canary checks skipped (no lxml on this runner)", True,
              "the Django spec covers the behaviour in the backend image")
    else:
        etree = _lxml_etree
    for name, function in sorted(globals().items()):
        if name.startswith("test_") and callable(function):
            function()
    failed = [r for r in RESULTS if not r[1]]
    for name, ok, detail in RESULTS:
        print("%s %s%s" % ("PASS" if ok else "FAIL", name,
                           (" - " + detail) if detail and not ok else ""))
    print("xml_parse_guard suite: %d checks, %d failed" % (len(RESULTS), len(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
