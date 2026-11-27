#!/usr/bin/env python3
"""Offline checks for the documentation portal (#1597, epic #1589).

Part of the portal is generated, and a generated page is only trustworthy while
it still matches what generated it. This suite holds that equality plus the
structural facts a build depends on - reachability, include targets,
cross-references, the pin the build installs from - without running Sphinx, so it
costs milliseconds and needs neither the docs environment nor network access.
Building is the docs job's business; this is the part that fails a pull request
instead of a documentation deployment.

Three of these checks earned their place while #1597 was implemented: an
``{include}`` one directory level off, which MyST reports as *file not found*
while still writing an empty page; an RST ``.. toctree::`` inside a ``.md`` file,
which MyST renders as a paragraph and so publishes a section with no navigation;
and a toctree entry carrying the indent the RST form requires inside a fenced
MyST directive, where that indent becomes part of the document name. All three
"built successfully".

The last group of checks asks the one question a build cannot ask about itself:
whether the exit status of the pinned strict build really decides. It builds a
clean tree and a deliberately broken one against the same Sphinx and the same
flags the docs job uses, and pins the contrast - the broken tree exits non-zero
with ``-W`` and exits 0 without it, having written its HTML either way. Those
checks skip out loud when Sphinx is not installed and fail when
``MRMAP_DOCS_PYTHON`` names an interpreter that cannot import it.

Run from the repository root: ``python3 scripts/test_docs_build.py``.
Exit 0 when every check passes, 1 with the failed ones listed.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "source"
CONF = SOURCE / "conf.py"
EXTENSION = SOURCE / "_ext" / "mrmap_docs.py"
REQUIREMENTS = ROOT / "backend" / ".requirements" / "docs.txt"
DOCKERFILE = ROOT / "docker" / "docs" / "Dockerfile"
READTHEDOCS = ROOT / ".readthedocs.yaml"
WORKFLOW = ROOT / ".github" / "workflows" / "docs.yml"
GENERATOR = ROOT / "scripts" / "gen_docs_design.py"
GENERATED = ("design", "release_notes")
SKIP_DIRS = {"_ext", "_static", "_templates", "locale", "build", "_build"}

#: The flags the strict build of ``.github/workflows/docs.yml`` runs with, and
#: the ones the exit-status contract below is demonstrated with. Asserted
#: against the workflow rather than assumed, because a gate whose flags drifted
#: from the ones being tested is a gate that stopped meaning something.
STRICT_FLAGS = ["-b", "html", "-E", "-W", "--keep-going"]

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        failures.append(f"{name}: {detail}")
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}"
          + (f"  - {detail}" if detail and not ok else ""))


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def documents(base: Path = SOURCE) -> list[Path]:
    """Every portal document, the way Sphinx collects them."""
    return sorted(
        path for path in base.rglob("*")
        if path.is_file() and path.suffix in {".rst", ".md"}
        and not (set(path.relative_to(base).parts) & SKIP_DIRS))


def blocks(text: str, directive: str) -> list[str]:
    """The bodies of every ``directive`` block, in either dialect.

    RST spells a directive ``.. name::`` with an indented body; MyST spells the
    same one as a fenced block whose option lines are flush left. Both are
    matched here because a document may legitimately use either - which of them
    it *should* use for its file type is checked separately.
    """
    fenced = re.compile(
        r"^```\s*\{\s*" + directive + r"\s*\}\s*(.*)\n(.*?)^```\s*$",
        re.MULTILINE | re.DOTALL)
    simple = re.compile(
        r"^\.\.\s+" + directive + r"::\s*\n((?:[ \t]*\n|[ \t]+\S.*(?:\n|$))*)",
        re.MULTILINE)
    return ([head + body for head, body in fenced.findall(text)]
            + simple.findall(text))


def entries_in(block: str) -> list[str]:
    """Toctree entries of one body; option lines and comments are not entries."""
    entries = []
    for line in block.splitlines():
        stripped = line.strip()
        # An option line starts with a colon and a comment with ``..`` plus a
        # space - not with ``../``, which is how a relative entry starts.
        if not stripped or stripped.startswith(":") \
                or re.match(r"\.\.(\s|$)", stripped):
            continue
        entries.append(stripped.split(" #")[0].split("<<")[0].strip())
    return entries


def resolve(from_page: Path, entry: str) -> Path | None:
    """The document a toctree entry or ``:doc:`` target names, from ``from_page``."""
    base = (from_page.parent / entry).resolve()
    if base.suffix in {".rst", ".md"}:
        return base if base.is_file() else None
    for candidate in (Path(str(base) + ".md"), Path(str(base) + ".rst"),
                      base / "index.md", base / "index.rst", base):
        if candidate.is_file():
            return candidate
    return None


# ---------------------------------------------------------------- generator ---
def test_generated_pages_match_the_generator() -> None:
    """The committed generated pages are what the generator writes today.

    Run against a throw-away tree, so the working copy is never touched.
    """
    committed = {page.relative_to(SOURCE): read(page)
                 for name in GENERATED
                 for page in (SOURCE / name).rglob("*") if page.is_file()}
    spec = importlib.util.spec_from_file_location("gen_docs_design", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as tmp:
        module.SOURCE = Path(tmp)
        module.main()
        produced = {page.relative_to(Path(tmp)): read(page)
                    for page in Path(tmp).rglob("*") if page.is_file()}
    difference = sorted(
        {str(key) for key in produced.keys() ^ committed.keys()}
        | {str(key) for key in produced if produced[key] != committed.get(key)})
    check("the generated pages are what scripts/gen_docs_design.py writes",
          produced == committed, ", ".join(difference))


# ----------------------------------------------------------------- coverage ---
def included_targets() -> dict[str, list[Path]]:
    """Every ``{include}`` target of the portal, resolved to a repository path."""
    includes: dict[str, list[Path]] = {}
    for page in documents():
        for body in blocks(read(page), "include"):
            target = body.splitlines()[0].split()[0]
            includes.setdefault(str((page.parent / target).resolve()), []).append(page)
    return includes


def test_every_authored_note_is_rendered_exactly_once() -> None:
    """Each note the repository quotes as authority reaches the portal once.

    The notes under ``docs/`` are the one part of the portal not authored in the
    portal tree: ``AGENTS.md``, the README and the project skills quote those
    paths. Both a note nobody includes and a note included twice are faults - the
    first hides content, the second gives a reader two URLs for one document.
    """
    authored = (sorted((ROOT / "docs").glob("*.md"))
                + sorted((ROOT / "docs" / "architecture" / "decisions").glob("*.md"))
                + sorted((ROOT / "docs" / "images").glob("*/README.md")))
    includes = included_targets()
    for note in authored:
        found = includes.get(str(note.resolve()), [])
        check(f"rendered exactly once: {note.relative_to(ROOT)}",
              len(found) == 1, f"{len(found)} including page(s)")
    for key, pages in sorted(includes.items()):
        check(f"the included file exists: {Path(key).relative_to(ROOT)}",
              Path(key).is_file(),
              "included by "
              + ", ".join(str(p.relative_to(ROOT)) for p in pages))


def test_every_document_is_reachable_from_the_root() -> None:
    """No page is orphaned.

    ``orphan_warnings`` is off, so an unreachable page is silent: it builds, it
    gets published, and no navigation leads to it. That is how the eight design
    notes stayed invisible for the whole life of the corpus while the README
    quoted them.
    """
    entries = {page: [entry for block in blocks(read(page), "toctree")
                      for entry in entries_in(block)]
               for page in documents()}
    root = SOURCE / "index.rst"
    reachable, queue = {root}, [root]
    while queue:
        page = queue.pop()
        for entry in entries.get(page, []):
            target = resolve(page, entry)
            if target and target not in reachable:
                reachable.add(target)
                queue.append(target)
    orphans = [page for page in documents()
               if page not in reachable
               and page.stem not in {"genindex", "search"}
               and "_generated" not in read(page)]
    check("every portal document is reachable from index.rst", not orphans,
          ", ".join(str(p.relative_to(ROOT)) for p in orphans))


def test_no_directive_is_written_in_the_wrong_dialect() -> None:
    """A directive inside a ``.md`` file is MyST syntax and nothing else.

    ``.. toctree::`` in Markdown is a paragraph, and MyST spells the same
    directive as a fenced block. The two read alike in a diff and only one of
    them produces navigation or a table.
    """
    bad = [page for page in documents()
           if page.suffix == ".md"
           and re.search(r"^\.\.\s+(toctree|list-table|include|note|warning"
                         r"|figure|code-block|mermaid|graphviz|image)\s*::",
                         read(page), re.MULTILINE)]
    check("no RST directive syntax inside a Markdown page", not bad,
          ", ".join(str(p.relative_to(ROOT)) for p in bad))


def test_markdown_toctree_entries_are_flush_left() -> None:
    """An entry inside a fenced MyST toctree carries no indent of its own.

    The indentation the RST form needs becomes part of the document name inside a
    fenced block, so the entry resolves to nothing and the section publishes with
    an empty navigation.
    """
    indented = []
    for page in documents():
        if page.suffix != ".md":
            continue
        for block in blocks(read(page), "toctree"):
            indented += [f"{page.relative_to(ROOT)}: {line!r}"
                         for line in block.splitlines()
                         if line.startswith(" ") and line.strip()
                         and not line.strip().startswith(":")]
    check("toctree entries of a Markdown page are flush left", not indented,
          "; ".join(indented))


def test_title_adornments_are_long_enough() -> None:
    """A title is adorned by a rule at least as long as the title itself.

    docutils reports the shorter form as a title that "is not underlined" and
    renders the heading as body text, so the section vanishes from the table of
    contents while still being readable on the page. This was the most frequent
    single fault found while #1597 repaired the corpus.
    """
    short = []
    for page in documents():
        lines = read(page).splitlines()
        # A fenced block is not a heading, and its delimiter is a rule as far as
        # a character test is concerned: only look outside the fences.
        inside = False
        for index in range(len(lines) - 1):
            rule, title = lines[index], lines[index - 1] if index else ""
            if rule.startswith("```"):
                inside = not inside
                continue
            if inside or not rule or set(rule) - set("=-~^\"'`#+*"):
                continue
            if not title.strip() or set(title) & set("=-~^\"'`#+*"):
                continue
            if len(rule) < len(title):
                short.append(f"{page.relative_to(ROOT)}: {title!r}")
    check("every title adornment is at least as long as its title", not short,
          "; ".join(short))


def test_theme_assets_exist() -> None:
    """Every static asset the config names is a file git carries.

    Two faults hide here, and CI found the first one after a local tree that
    already had both had passed. A ``html_css_files`` entry naming a sheet that
    was never written is not checked by Sphinx at all, so the portal publishes
    without its styling and nothing is reported. And a ``html_static_path``
    entry that names an empty directory is a warning - which -W turns into a
    failure - while git itself never commits an empty directory, so the checkout
    has no such path at all.
    """
    conf = read(CONF)
    source = SOURCE
    for name in re.findall(r'"([^"]+\.css)"', conf):
        check(f"the stylesheet {name} the config names exists",
              (source / "_static" / name).is_file())
    paths = re.search(r"html_static_path\s*=\s*\[([^\]]*)\]", conf)
    for entry in re.findall(r'"([^"]+)"', paths.group(1)) if paths else []:
        directory = source / entry
        check(f"the static path {entry} exists and is committed",
              directory.is_dir() and any(p.is_file() for p in directory.rglob("*")))


# ------------------------------------------------------------ cross-references ---
def test_doc_references_resolve() -> None:
    """Every ``:doc:`` and ``{doc}`` target names a document that exists."""
    broken = []
    for page in documents():
        text = read(page)
        targets = (re.findall(r":doc:`[^`<]*<([^>]+)>`", text)
                   + re.findall(r":doc:`([^`<>]+)`", text)
                   + re.findall(r"\{doc\}`[^`<]*<([^>]+)>`", text)
                   + re.findall(r"\{doc\}`([^`<>]+)`", text))
        for target in targets:
            if resolve(page, target.strip()) is None:
                broken.append(f"{page.relative_to(ROOT)} -> {target}")
    check("every :doc: target resolves", not broken,
          "; ".join(sorted(set(broken))))


def test_ref_targets_have_a_label() -> None:
    """Every ``:ref:`` names a label some document defines.

    Labels are written explicitly rather than generated from section titles, so a
    renamed heading cannot break a cross-reference - and a reference to a label
    that was never written is caught here rather than by a reader.
    """
    labels: set[str] = set()
    for page in documents():
        text = read(page)
        labels |= set(re.findall(r"^\.\.\s+_([^:\s]+):", text, re.MULTILINE))
        labels |= set(re.findall(r"^\(([^)\s]+)\)=$", text, re.MULTILINE))
    broken = []
    for page in documents():
        for explicit, shorthand in re.findall(
                r":ref:`([^`<]*)(?:<([^>]*)>)?`", read(page)):
            target = (shorthand or explicit).strip()
            if target and target not in labels:
                broken.append(f"{page.relative_to(ROOT)} -> {target}")
    check("every :ref: names a label that is defined", not broken,
          "; ".join(sorted(set(broken))))


def test_rst_explicit_links_resolve() -> None:
    """RST inline links name a real target, document, or absolute URL."""
    labels: set[str] = set()
    pages = [page for page in documents() if page.suffix == ".rst"]
    for page in pages:
        labels |= set(re.findall(r"^\.\.\s+_([^:\s]+):", read(page), re.MULTILINE))
        labels |= set(re.findall(r"^\(([^)\s]+)\)=$", read(page), re.MULTILINE))

    broken = []
    pattern = re.compile(r"(?<!`)`[^`<>]+<([^<>]+)>`_(?!`)")
    for page in pages:
        for target in pattern.findall(read(page)):
            target = target.strip()
            if urlsplit(target).scheme or target.startswith("//"):
                continue
            if target.endswith("_") and target[:-1] in labels:
                continue
            local_target = target[:-1] if target.endswith("_") else target
            local_target = local_target.split("#", 1)[0]
            if local_target and resolve(page, local_target) is None:
                broken.append(f"{page.relative_to(ROOT)} -> {target}")
    check("every RST inline target resolves", not broken,
          "; ".join(sorted(set(broken))))


def test_local_links_of_the_authored_corpus_resolve() -> None:
    """Every relative Markdown link under ``docs/`` points at a real file.

    A note written for the repository tree and rendered into the portal tree is
    where this breaks: the target exists on GitHub and not in the build, or the
    other way round. A directory is not a page either - the portal publishes
    documents, so a link at a directory is a 404 in the built site.
    """
    broken = []
    for note in sorted((ROOT / "docs").rglob("*.md")):
        for target in re.findall(r"\]\((?!https?://|mailto:|#)([^)\s]+)",
                                 read(note)):
            if not (note.parent / target.split("#")[0]).resolve().is_file():
                broken.append(f"{note.relative_to(ROOT)} -> {target}")
    check("every relative link of the authored corpus is a file", not broken,
          "; ".join(broken))


# ------------------------------------------------------------------- config ---
def test_configuration_holds_the_contracts_the_pages_depend_on() -> None:
    conf = read(CONF)
    check("the MyST parser is loaded", '"myst_parser"' in conf)
    check("the project extension is loaded", '"mrmap_docs"' in conf)
    check("Markdown is a recognised source suffix", '".md"' in conf)
    check("include fences are directives",
          "myst_fence_as_directive" in conf and '"include"' in conf)
    check("headings get anchors so notes can link into each other",
          "myst_heading_anchors" in conf)
    check("the theme is declared", "sphinx_rtd_theme" in conf)
    check("the documented language is declared, for the root element and search",
          'language = "en"' in conf)
    check("private hosts are never link-checked",
          "linkcheck_ignore" in conf and "127.0.0.1" in conf)
    check("a generated artifact inside the tree can never be a source",
          '"build"' in conf and '"_build"' in conf)
    check("the release string comes from the canonical VERSION file",
          "VERSION" in conf and "release" in conf)
    check("autodoc failure is a decision and not a surprise",
          "MRMAP_DOCS_AUTODOC" in conf)
    extension = read(EXTENSION)
    check("real autodoc directives are registered before being reported effective",
          'app.setup_extension("sphinx.ext.autodoc")' in extension)
    check("diagram blocks degrade to their source rather than to nothing",
          "MermaidSourceDiagram" in extension
          and "GraphvizSourceDiagram" in extension)
    check("rendered Mermaid uses and includes the vendored local renderer",
          "mermaid_use_local = MERMAID_RENDERER_FILENAME" in extension
          and "_copy_vendored_mermaid" in extension)
    check("no diagram renderer is ever fetched over the network",
          "requests.get" not in extension and "urlopen" not in extension)
    check("every build writes its provenance beside its output",
          "provenance.json" in extension
          and all(key in extension for key in
                  ('"builder"', '"documented_commit"', '"autodoc"', '"diagrams"')))


def test_hosting_is_managed_and_the_force_push_publisher_stays_gone() -> None:
    """Hosting is Read the Docs configuration, not a publisher of our own (#1608).

    The retired 2021 script force-pushed a build onto ``gh-pages``, so it could
    not say which version or commit a published page came from, and a failed run
    replaced good documentation with nothing. The revised epic #1589 does not
    want a repository-owned replacement at all: the managed service provides the
    versions, the retention and the build queue. These checks hold that decision,
    because a deleted file and a page of prose are both easy to undo quietly.
    """
    check("the force-push publisher is gone",
          not (ROOT / "docs" / "publish_docs.sh").exists())

    workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    force_pushers = [w.name for w in workflows
                     if "gh-pages" in read(w)
                     and re.search(r"git push[^\n]*(--force|-f)\b", read(w))]
    check("no workflow force-pushes a Pages branch", not force_pushers,
          ", ".join(force_pushers))
    # A Pages deployment job beside the service would be the dual publisher the
    # revised epic refuses, so name one rather than trust the prose about it.
    deployers = [f"{w.name}:{job}" for w in workflows
                 for job in workflow_jobs(read(w))
                 if re.search(r"pages|deploy", job, re.IGNORECASE)]
    check("no Pages deployment job exists beside the managed service",
          not deployers, ", ".join(deployers))

    config = read(READTHEDOCS)
    check("Read the Docs builds from the single docs pin file",
          re.search(r"requirements:\s*\n?\s*-?\s*backend/\.requirements/docs\.txt",
                    config) is not None)
    check("the hosted build treats a warning as a failure, as CI does",
          "fail_on_warning: true" in config)
    # Comments only, this time the other way round: the header of the file
    # explains why it declares no apt packages, and prose about a setting is not
    # the setting. Same distinction the docs-image check above makes.
    declared = "\n".join(line for line in config.splitlines()
                         if not line.lstrip().startswith("#"))
    check("no second package source is declared for the hosted build",
          "apt_packages" not in declared and "pip install" not in declared)
    check("the hosted interpreter is the one the docs pins were frozen with",
          'python: "3.13"' in config and "ubuntu-24.04" in config)

    hosting = SOURCE / "development" / "documentation-hosting.rst"
    text = read(hosting) if hosting.is_file() else ""
    # Named after the actions the service actually offers, so that a rewrite of
    # this page into a plausible-sounding but wrong rule set fails here.
    check("the hosting rules an administrator has to set are written down",
          all(phrase in text for phrase in
              ("Automation Rules", "Activate version", "Trigger build for version",
               "Changed files", "Hide version")),
          "; ".join(phrase for phrase in
                    ("Automation Rules", "Activate version", "Trigger build for version",
                     "Changed files", "Hide version") if phrase not in text))
    published = hosted_site_url()
    check("the hosted site is the URL the image metadata publishes",
          bool(published) and published in text,
          f"image_release.py publishes {published!r}")


def hosted_site_url() -> str:
    """The documentation URL the image metadata publishes, read from its owner."""
    match = re.search(r'"documentation":\s*"(https://[^"]+)"',
                      read(ROOT / "scripts" / "image_release.py"))
    return match.group(1) if match else ""


def workflow_jobs(text: str) -> list[str]:
    """Job ids of a workflow file, from the two-space indent under ``jobs:``."""
    body = text.split("\njobs:", 1)
    if len(body) < 2:
        return []
    return re.findall(r"^  ([A-Za-z0-9_-]+):\s*$", body[1], re.MULTILINE)


def test_requirements_are_pinned_and_isolated() -> None:
    requirements = read(REQUIREMENTS)
    lines = [line.strip() for line in requirements.splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    unpinned = [line for line in lines if "==" not in line]
    check("every docs requirement is pinned to an exact version", not unpinned,
          ", ".join(unpinned))
    pins = {re.split("==", line)[0].strip().lower().replace("_", "-")
            for line in lines if "==" in line}
    for name in ("sphinx", "myst-parser", "sphinx-multiversion",
                 "sphinx-rtd-theme"):
        check(f"{name} is pinned", name in pins, str(sorted(pins)))
    sphinx = next((line for line in lines
                   if line.lower().startswith("sphinx==")), "sphinx=missing")
    check("Sphinx is on a major version the configuration supports",
          int(sphinx.split("==")[1].split(".")[0]) >= 7, sphinx)
    application = [name for name in ("django", "djangorestframework", "gdal",
                                     "psycopg", "celery")
                   if re.search("^" + name + r"\b", requirements.lower(),
                                re.MULTILINE)]
    check("the docs build needs nothing of the application", not application,
          ", ".join(application))
    if DOCKERFILE.is_file():
        # Only the instructions count: the header comment of this image explains
        # the unpinned image it replaced, and prose about that is not an install.
        instructions = "\n".join(line for line in read(DOCKERFILE).splitlines()
                                 if not line.lstrip().startswith("#"))
        check("the docs image installs the pinned docs requirements",
              "backend/.requirements/docs.txt" in instructions
              and "-r /tmp/docs.txt" in instructions)
        check("the docs image installs no second source of Sphinx",
              "python3-sphinx" not in instructions
              and "requirements.txt" not in instructions)
    if READTHEDOCS.is_file():
        declared = re.findall(r"requirements:\s*\n\s*-\s*(\S+)", read(READTHEDOCS))
        check(".readthedocs.yaml names requirements files that exist",
              all((ROOT / name).is_file() for name in declared), str(declared))


# ------------------------------------------------------- the strict build is the gate ---
def _sphinx_interpreter() -> tuple[str | None, str, bool]:
    """The interpreter that can run Sphinx, or why this check cannot run.

    Returns ``(interpreter, reason, is_defect)``. The distinction is the point:

    - ``(path, "", False)`` - Sphinx is there, run the checks.
    - ``(None, reason, False)`` - this host never had Sphinx, so the affected
      checks skip out loud rather than reporting a broken portal.
    - ``(None, reason, True)`` - ``MRMAP_DOCS_PYTHON`` named an interpreter and
      it cannot import Sphinx. That is a defect, not an absent optional tool:
      the docs job names the venv it installed from the one pin file, and a gate
      that skipped whenever that venv broke would stop being checked exactly when
      it started mattering.
    """
    named = os.environ.get("MRMAP_DOCS_PYTHON", "").strip()
    if named:
        if not Path(named).exists():
            return None, f"MRMAP_DOCS_PYTHON={named} does not exist", True
        probe = subprocess.run([named, "-c", "import sphinx"],
                               capture_output=True, text=True)
        if probe.returncode != 0:
            tail = probe.stderr.strip().splitlines()
            return None, (f"MRMAP_DOCS_PYTHON={named} cannot import sphinx: "
                          f"{tail[-1] if tail else 'no output'}"), True
        return named, "", False

    probe = subprocess.run([sys.executable, "-c", "import sphinx"],
                           capture_output=True, text=True)
    if probe.returncode == 0:
        return sys.executable, "", False
    return None, ("no Sphinx on this interpreter (install "
                  "backend/.requirements/docs.txt, or name one with "
                  "MRMAP_DOCS_PYTHON)"), False


def _write_fixtures(base: Path) -> tuple[Path, Path]:
    """A clean tree and a tree with two independent faults, both minimal.

    The faults are the two the portal actually produces: a toctree entry that
    names no document, and a ``:doc:`` target that resolves to nothing. Two of
    them, on two pages, so a build that stopped at the first warning would be
    visible as doing so.
    """
    conf = 'project = "gate"\nextensions = []\nexclude_patterns = ["_build"]\n'
    good = base / "good"
    bad = base / "bad"
    for tree in (good, bad):
        tree.mkdir(parents=True)
        (tree / "conf.py").write_text(conf, encoding="utf-8")
        (tree / "page.rst").write_text(
            "Page\n====\n\nText that references :doc:`page` correctly.\n",
            encoding="utf-8")
    (good / "index.rst").write_text(
        "Gate\n====\n\n.. toctree::\n   :maxdepth: 2\n\n   page\n",
        encoding="utf-8")
    (bad / "index.rst").write_text(
        "Gate\n====\n\n.. toctree::\n   :maxdepth: 2\n\n   page\n   missing\n",
        encoding="utf-8")
    (bad / "page.rst").write_text(
        "Page\n====\n\nSee :doc:`nowhere`.\n", encoding="utf-8")
    return good, bad


def _build(interpreter: str, source: Path, out: Path,
           flags: list[str]) -> tuple[int, str]:
    process = subprocess.run([interpreter, "-m", "sphinx", *flags, "-q",
                              str(source), str(out)],
                             capture_output=True, text=True, cwd=str(ROOT))
    return process.returncode, (process.stdout or "") + (process.stderr or "")


def test_the_strict_build_is_the_gate() -> None:
    """The exit status of the pinned strict build decides, and nothing else does.

    Three facts, each one the failure mode the issue's "native exit status is the
    gate" sentence exists to close, all three demonstrated against the same
    interpreter and the same flags ``docs.yml`` runs with:

    1. A clean tree exits 0 - the gate is satisfiable, so a red is a real red.
    2. A broken tree exits non-zero *and* lists both faults, which is ``-W`` and
       ``--keep-going`` respectively doing their jobs.
    3. The same broken tree **without** ``-W`` exits 0 and still writes its HTML.
       That contrast is the whole reason the flag is in the workflow: without it
       a documentation build publishes quietly broken pages and reports success.
    """
    interpreter, why_unavailable, is_defect = _sphinx_interpreter()
    if interpreter is None:
        # A named interpreter that cannot import Sphinx is a broken environment,
        # reported as a failure; an absent optional tool is a reported skip.
        check("the strict build can run where it was asked to run", not is_defect,
              why_unavailable)
        if not is_defect:
            print(f"SKIP  the strict build exits as the gate ({why_unavailable})")
        return

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        good, bad = _write_fixtures(base)
        clean_code, clean_out = _build(interpreter, good, base / "out-good",
                                       STRICT_FLAGS)
        broken_code, broken_out = _build(interpreter, bad, base / "out-bad",
                                         STRICT_FLAGS)
        lenient_code, _lenient_out = _build(
            interpreter, bad, base / "out-lenient",
            [flag for flag in STRICT_FLAGS if flag != "-W"])
        lenient_pages = list((base / "out-lenient").glob("*.html"))

    check("a clean tree builds with exit status 0", clean_code == 0,
          f"exit {clean_code}: {clean_out[-200:]}")
    check("a broken tree is refused by the native exit status",
          broken_code != 0, f"exit {broken_code}: {broken_out[-200:]}")
    check("the failing build names both faults, not just the first",
          "missing" in broken_out and "nowhere" in broken_out
          and broken_out.count("WARNING") >= 2,
          broken_out[-300:])
    check("-W is load-bearing: the same broken tree passes without it",
          lenient_code == 0 and len(lenient_pages) > 0,
          f"exit {lenient_code}, {len(lenient_pages)} page(s) written")


def test_ordinary_checks_stay_targeted_and_publish_nothing() -> None:
    """An ordinary pull request checks the documentation; it does not ship it.

    #1589 is explicit that publication is not here and that no heavy docs job
    belongs in ordinary development: the portal is built and uploaded as a
    reviewable artifact, linkcheck is reported rather than gated (an upstream 500
    must not refuse a pull request that never touched the page quoting it), and
    nothing deploys. Those boundaries are one deleted line each, so they are held
    rather than trusted.
    """
    workflow = read(WORKFLOW)
    strict_step = [line for line in workflow.splitlines() if "-m sphinx" in line]
    check("the workflow builds the portal strictly, with -W --keep-going",
          any("-W" in line and "--keep-going" in line for line in strict_step),
          "; ".join(strict_step) or "no sphinx invocation found")
    check("linkcheck cannot refuse a pull request (informational only)",
          "continue-on-error: true" in workflow
          and "-b linkcheck" in workflow,
          "linkcheck must stay reported, not gated")
    publishable = [needle for needle in
                   ("actions/deploy-pages", "upload-pages-artifact",
                    "sphinx-multiversion", "docker build", "rsync",
                    "gh-pages")
                   if needle in workflow]
    check("no ordinary pull request publishes a site", not publishable,
          ", ".join(publishable))
    check("the docs job needs no credentials, database or container",
          "secrets." not in workflow and "docker compose" not in workflow
          and "POSTGRES" not in workflow,
          "the docs environment is the one pin file")
    # The demonstration of the exit-status contract needs the pinned interpreter,
    # and the suite runs under the runner's plain python. Without this line in the
    # workflow those checks skip in CI while every local run says green, which is
    # how a gate goes unsurveyed without anyone deciding to remove it.
    check("the docs job hands the suite the pinned interpreter",
          re.search(r"^\s*MRMAP_DOCS_PYTHON:\s*\S", workflow, re.MULTILINE)
          is not None,
          "the exit-status demonstration would skip in CI")


def main() -> int:
    test_generated_pages_match_the_generator()
    test_every_authored_note_is_rendered_exactly_once()
    test_every_document_is_reachable_from_the_root()
    test_no_directive_is_written_in_the_wrong_dialect()
    test_markdown_toctree_entries_are_flush_left()
    test_title_adornments_are_long_enough()
    test_theme_assets_exist()
    test_doc_references_resolve()
    test_ref_targets_have_a_label()
    test_rst_explicit_links_resolve()
    test_local_links_of_the_authored_corpus_resolve()
    test_configuration_holds_the_contracts_the_pages_depend_on()
    test_hosting_is_managed_and_the_force_push_publisher_stays_gone()
    test_requirements_are_pinned_and_isolated()
    test_the_strict_build_is_the_gate()
    test_ordinary_checks_stay_targeted_and_publish_nothing()
    print(f"\n{len(failures)} failed of the checks above" if failures
          else "\nall checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
