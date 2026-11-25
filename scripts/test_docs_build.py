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

Run from the repository root: ``python3 scripts/test_docs_build.py``.
Exit 0 when every check passes, 1 with the failed ones listed.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "source"
CONF = SOURCE / "conf.py"
EXTENSION = SOURCE / "_ext" / "mrmap_docs.py"
REQUIREMENTS = ROOT / "backend" / ".requirements" / "docs.txt"
DOCKERFILE = ROOT / "docker" / "docs" / "Dockerfile"
READTHEDOCS = ROOT / ".readthedocs.yaml"
GENERATOR = ROOT / "scripts" / "gen_docs_design.py"
GENERATED = ("design", "release_notes")
SKIP_DIRS = {"_ext", "_static", "_templates", "locale", "build", "_build"}

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
    check("diagram blocks degrade to their source rather than to nothing",
          "MermaidSourceDiagram" in extension
          and "GraphvizSourceDiagram" in extension)
    check("no diagram renderer is ever fetched over the network",
          "requests.get" not in extension and "urlopen" not in extension)
    check("every build writes its provenance beside its output",
          "provenance.json" in extension
          and all(key in extension for key in
                  ('"builder"', '"documented_commit"', '"autodoc"', '"diagrams"')))


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


def main() -> int:
    test_generated_pages_match_the_generator()
    test_every_authored_note_is_rendered_exactly_once()
    test_every_document_is_reachable_from_the_root()
    test_no_directive_is_written_in_the_wrong_dialect()
    test_markdown_toctree_entries_are_flush_left()
    test_title_adornments_are_long_enough()
    test_doc_references_resolve()
    test_ref_targets_have_a_label()
    test_local_links_of_the_authored_corpus_resolve()
    test_configuration_holds_the_contracts_the_pages_depend_on()
    test_requirements_are_pinned_and_isolated()
    print(f"\n{len(failures)} failed of the checks above" if failures
          else "\nall checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
