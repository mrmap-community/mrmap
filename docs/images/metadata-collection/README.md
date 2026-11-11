# Metadata collection — design images

Images for the audit of the service registration and its metadata collection. Two kinds, deliberately
distinguishable:

## `current-*.png` — MrMap as it is today

Rendered from the source of `master` at `d2a9dc0` (react-admin v5 + MUI tokens; the components under
`frontend/src/components/Resource/`). They are **faithful HTML renderings of the implemented UI, not
screenshots of a running deployment** — no public MrMap demo was reachable while these were made, and
starting a full stack would not change what the components render. Marked `CURRENT` in the image.

Inside those images a grey dashed box marks something which is **missing today**, and names the file and
line which is responsible for it. That is the only annotation; nothing outside such a box is invented.

| image | screen |
| --- | --- |
| `current-registration-jobcenter.png` | service overview of a registered WMS with the Background Job Center open: nothing on the page reports the collection, the job row is the only trace |
| `current-featuretype-inspection.png` | WFS feature types tab, element inspection: the metadata section a layer gets is not rendered for a feature type |

## `proposed-*.png` — design proposals

Same rendering technique, same design language. Every proposed part is drawn with a **dashed outline and an
orange "proposed" tag**; a legend strip at the bottom of each image separates the two. These are
**proposals, not implemented screens** — marked `PROPOSED` in the image. Each one is attached to the issue
that specifies it.

| image | proposal |
| --- | --- |
| `proposed-create-dialog-collect-metadata.png` | the create option: wording which states what is collected, that failures are per reference, and where to look afterwards |
| `proposed-registration-collection-card.png` | one card per registration on the service overview: phases, progress, counters per outcome |
| `proposed-collection-outcome.png` | the background process screen with one row per metadata reference and its outcome, next to the log as it looks today |
| `proposed-featuretype-metadata-relations.png` | element inspection with the metadata section for a feature type, showing which record describes what |
| `proposed-dataset-relationship-graph.png` | the relations graph grouped by what a relation means — with the existing relation kinds only, per RFC #992 and the review of PR #1255 |

## How they were made

The pages are written as HTML against a stylesheet which reproduces MrMap's own tokens and the markup of the
components in question (`SimpleCard`, the service show tabs, `HarvestingActivityCard`,
`HarvestingPhaseStepper`, `HarvestingRunSummary`, `RecordRelations`, `JobCenterDrawer`, `ElementInspection`),
then screenshotted with headless Chromium at 1440 px and 1.5 device scale.

* **Every label is taken from the source**, not invented: `frontend/src/i18n/en.ts` (`serviceShow.*`,
  `recordShow.*`, `layerInspection.*`, `backgroundActivity.*`, `harvestRun.collectingStates.*`), the resource
  names the OpenAPI schema provides, and `backend/registry/enums/metadata.py` for the `MetadataOriginEnum`
  labels. The English locale is used, as in the metadata-editor images.
* Data is **plausible, not real**: no public deployment was queried, and no real service's capabilities were
  read. The identifiers, titles and URLs are invented in the style of the fixtures; the counts match what the
  cited code does with them.
* Proposed wording is labelled as proposed *inside* the image, so a reader cannot mistake a suggestion for an
  implemented string.
