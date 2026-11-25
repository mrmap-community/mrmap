(release-notes)=

# Release notes

Two things meet on this page and they have different authors. The version this
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

## The notes

Below is ``CHANGELOG.md`` of the commit this build was made from, in place. Its Keep a Changelog headings are the headings the release tooling writes, so this page and the release artifact cannot say different things about one version.

```{include} ../../../CHANGELOG.md
:relative-docs: ../../../
```
