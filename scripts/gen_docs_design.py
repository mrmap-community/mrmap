#!/usr/bin/env python3
"""Generate the portal's design and release-notes pages (#1597, epic #1589).

Deterministic and offline: reads the authored notes under ``docs/`` and writes the
wrapper pages under ``docs/source/``. Run from the repository root with no
arguments, and run it again after adding a note - ``scripts/test_docs_build.py``
fails when the committed pages are not what this script produces, so the
generated tree cannot drift from the notes it renders.

Nothing here rewrites a note. Each page is one ``{include}`` of one Markdown file
with ``:relative-docs:`` and ``:relative-images:``: the note keeps its own
headings and words, its links to sibling notes resolve to sibling portal pages,
and its pictures still show the picture. The notes stay Markdown at their
repository paths because ``AGENTS.md``, the README and the project skills quote
those paths - the build reads them where they are instead of moving them.

The pages are MyST rather than reStructuredText because that is what the
``.md`` suffix means here: a directive written ``.. toctree::`` inside a Markdown
file is *not* parsed, it renders as a paragraph. MyST spells the same directives
as fenced blocks and its tables as pipe tables, which is also the difference
between the notes' tables rendering and the portal silently publishing them as
text.
"""

from __future__ import annotations

import pathlib
import sys

SOURCE = pathlib.Path("docs/source")

# (page name, note under docs/, one-line reason a reader opens it)
NOTES = [
    ("architecture", "architecture.md",
     "The domain in one read: the service and metadata aggregates, update jobs,"
     " monitoring, the attention list and the security proxy. This is the note"
     " the project's own ``AGENTS.md`` files and skills point an implementer at."),
    ("metadata-identity", "metadata-identity.md",
     "How a record keeps its identity across harvests and updates: the decision"
     " record of #982 on identity, relationships, precedence and enum"
     " conventions, including the correction the later review rounds forced."),
    ("metadata-collection-design", "metadata-collection-design.md",
     "The audit and design behind registering an OGC service and collecting the"
     " metadata it links. Research and design only - the implementation is where"
     " the usage and development pages say it is."),
    ("metadata-editing", "metadata-editing.md",
     "How a record is authored today: the write path and what it guarantees, the"
     " authoring profiles, when validation runs, what a save does to the served"
     " document, and what the first version deliberately does not do."),
    ("metadata-editor-design", "metadata-editor-design.md",
     "The research and gap analysis that shaped the editor, with the comparison"
     " mockups. The mockups are proposals and the evidence grades say what was"
     " verified - read the page above for the implemented design."),
    ("ows-context", "ows-context.md",
     "The OGC OWS Context GeoJSON profile the instance exports at"
     " ``/mrmap-proxy/ows/<id>`` and the viewer consumes."),
    ("ows-context-interoperability", "ows-context-interoperability.md",
     "The acceptance contract for the exported OWS Context against the clients"
     " that consume it. A proposed clarification, not an assertion that every"
     " row of it is implemented."),
    ("live-service-previews", "live-service-previews.md",
     "The live preview card on a service overview: what it fetches, what it"
     " cancels, and which state belongs to the preview rather than to the"
     " viewer."),
]

PAGE_HEADER = """<!-- Rendered by the portal from ``docs/{note}`` (#1597); this page
holds no prose of its own. The note stays Markdown at its repository path,
because that is the path ``AGENTS.md``, the README and the project skills quote,
and the build includes it here. ``:relative-docs:`` and ``:relative-images:`` are
what make a link from one note to another resolve to two portal pages and a
picture still show the picture, instead of pointing at a repository path no
reader of the portal has.
-->

"""

# Architecture decision records are rendered too: a design note links into them,
# and `docs/architecture/decisions/README.md` states that the portal consumes
# them as sources. `name` is the file stem, which keeps the citation a reader
# would write.
DECISIONS = [
    ("ADR-0001-autonomous-documentation-architecture-and-coverage-contract",
     "architecture/decisions/"
     "ADR-0001-autonomous-documentation-architecture-and-coverage-contract.md",
     "The architecture this portal is built under: deterministic extraction"
     " over generated prose, evidence as the unit of trust, the audience"
     " taxonomy the sections above follow, the artifact schema, and the"
     " validation gates #1597 through #1610 are measured against."),
    ("ADR-README", "architecture/decisions/README.md",
     "The conventions the records are written under: numbering, what each status"
     " commits the project to, and how a record is superseded rather than edited."
     " Read this before reading any record."),
]

DECISIONS_INTRO = """The records of decisions that shaped the system, rendered from
``docs/architecture/decisions/``. A record is a historical document: once
accepted it is not edited in place, only succeeded by a record that supersedes
it, so reading one tells you what was known and chosen at the time - not
necessarily what is true today. The numbering, status and supersession
conventions are in ``docs/architecture/decisions/README.md``.

"""

INDEX_INTRO = """The reasoning behind the features, written while they were being decided. These
pages are **not** generated and not summarised: each is one hand-authored
Markdown note under ``docs/`` in the repository, included into the portal
verbatim by the page that names it.

The notes were always part of the corpus and never part of the portal. Before
#1597 the build loaded no Markdown parser, so eight notes totalling more than
1 600 lines - beside two image manifests - were invisible to a reader while
``AGENTS.md``, the README and the project's own skills quoted them as authority.
Rendering them is the whole of this section; editing them is not, which is why
no page here carries prose of its own.

Two conventions to read them with:

- **Provenance is stated, not assumed.** Several notes carry images marked
  ``CURRENT`` or ``PROPOSED``. Those are renderings of the implemented
  components or of a proposal, produced from the source at a named commit, and
  the manifest beside them under ``docs/images/`` says which is which and when
  it was made. They are not screenshots of a running deployment, and the notes
  say so themselves.
- **A note is the historical record.** Several are explicitly research, an audit
  or a proposed contract, and one describes a decision a later review round
  superseded. Where a note and the running software disagree, the implementation
  page in the relevant section is the authority for the present and the note is
  the record of how it got there.

"""

# The manifests beside the design images are part of the evidence of the notes
# that quote them - they say which picture is a rendering of the current UI and
# which is a proposal - and the notes link to them by relative path, so they are
# rendered at the path those links resolve to.
MANIFESTS = [
    ("images/metadata-collection/README.md",
     "design/images/metadata-collection/README.md"),
    ("images/metadata-editor/README.md",
     "design/images/metadata-editor/README.md"),
]

RELEASE_NOTES_INTRO = """Two things meet on this page and they have different authors. The version this
portal documents comes from the canonical ``VERSION`` file of the release the
build was made from, and ``sphinx_multiversion`` builds the documentation of
every released tag - ``scripts/release_lifecycle.json`` names that selection and
``scripts/test_release_lifecycle.py`` fails if the description and the tooling
drift apart - so the version selector in the sidebar lists the versions that have
their own documentation. The notes below are written by the change itself, from
the class of its pull request title: ``CONTRIBUTING.md`` tells contributors the
pull request title is the change class, and ``scripts/release_gates.py`` refuses
a release whose notes do not match the history it was built from (#1578, #1580,
#1581, epic #1577). Neither the notes nor this page is hand-edited, which is the
only reason they can be trusted to stay in step with the software.

| You want | Read | Because |
| --- | --- | --- |
| the notes of the version you run | the section of your version below | it is generated from the same commit as this build |
| the exact, immutable notes of a released version | ``CHANGELOG.md`` **on the release tag**, or the GitHub release | ``develop`` moves; a tag never does |
| what is planned but not released | the *Unreleased* section below | curated entries sit above the generated releases until a release is prepared (#1581) |
| how a version number is decided | {doc}`../development/release-versioning-baseline` and {doc}`../development/release-planning` | the SemVer policy and the measured implementation of it |
| how to get from one version to the next | {doc}`../administration/release-operator-runbook` | the image pin, the migrate step, and the backup and rollback duties that belong to the operator and to no tool |

Publication is not part of this portal yet (#1608, #1609). What exists here is
the build: the artifact, its identity and its gates. Publishing a built portal to
a public host stays a separate, privileged step that consumes the artifact and
runs no generator - see {ref}`decision-records`.

"""


def includedirective(target: str, up: str, images: bool = True) -> str:
    """One MyST ``{include}`` of ``target``, resolved ``up`` levels from the page."""
    options = f":relative-docs: {up}\n"
    if images:
        options += ":relative-images:\n"
    return f"```{{include}} {target}\n{options}```\n"


def page(note: str, up: str, images: bool = True) -> str:
    return (PAGE_HEADER.format(note=note)
            + includedirective(f"{up}{note}", up, images))


def write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"wrote {path}")


def main() -> int:
    for name, note, _reason in NOTES:
        write(SOURCE / "design" / f"{name}.md", page(note, "../../"))

    for name, note, _reason in DECISIONS:
        write(SOURCE / "design" / "decisions" / f"{name}.md",
              page(note, "../../../"))

    for note, target in MANIFESTS:
        page_path = SOURCE / target
        # One level deeper than the page's own depth under ``source``: the note is
        # under ``docs/``, not under ``docs/source/``.
        up = "../" * (len(page_path.parent.relative_to(SOURCE).parts) + 1)
        write(page_path, page(note, up, images=False))

    rows = "\n".join(f"| {name} | {reason} |" for name, _n, reason in NOTES)
    entries = [name for name, _n, _r in NOTES]
    # The image manifests are reachable from the notes that quote them, and a
    # page no toctree leads to is a page no reader of the portal finds.
    entries += [target.removesuffix(".md").removeprefix("design/")
                for _note, target in MANIFESTS]
    manifest_rows = "\n".join(
        f"| {target[: -len('.md')]} | The manifest beside those pictures: which "
        f"file renders the implemented interface and which a proposal, and from "
        f"which commit it was made. |"
        for _note, target in MANIFESTS)
    entries.append("decisions/index")
    write(SOURCE / "design" / "index.md",
          "(design-notes)=\n\n# Design notes\n\n" + INDEX_INTRO
          + "| Page | What it settles |\n| --- | --- |\n" + rows + "\n" + manifest_rows + "\n\n"
          + "```{toctree}\n:hidden:\n:maxdepth: 1\n\n" + "\n".join(entries) + "\n```\n")

    decision_rows = "\n".join(f"| {name} | {reason} |"
                              for name, _n, reason in DECISIONS)
    decision_entries = "\n".join(name for name, _n, _r in DECISIONS)
    write(SOURCE / "design" / "decisions" / "index.md",
          "(decision-records)=\n\n# Architecture decisions\n\n" + DECISIONS_INTRO
          + "| Record | What it decided |\n| --- | --- |\n" + decision_rows + "\n\n"
          + "```{toctree}\n:hidden:\n:maxdepth: 1\n\n" + decision_entries + "\n```\n")

    write(SOURCE / "release_notes" / "index.md",
          "(release-notes)=\n\n# Release notes\n\n" + RELEASE_NOTES_INTRO
          + "## The notes\n\nBelow is ``CHANGELOG.md`` of the commit this build was"
          " made from, in place. Its Keep a Changelog headings are the headings the"
          " release tooling writes, so this page and the release artifact cannot say"
          " different things about one version.\n\n"
          + includedirective("../../../CHANGELOG.md", "../../../", images=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
