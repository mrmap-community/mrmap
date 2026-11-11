# Metadata editor design images

Images for the metadata editing epic. Two kinds, deliberately distinguishable:

## `current-*.png` — MrMap as it is today

Rendered from the source of `master` at `d2a9dc0` (react-admin v5 + MUI tokens, the components under
`frontend/src/components/Resource/Generic/RecordShow/`). They are **faithful HTML renderings of the
implemented UI, not screenshots of a running deployment** — no public MrMap demo was reachable when
these were made. Marked `CURRENT` in the image itself.

* `current-record-show.png` — the record detail screen (`RecordShow.tsx`, its six tabs, the header
  actions of `RecordHeader.tsx`)
* `current-edit-dialog.png` — the edit dialog: an `EditGuesser` `SimpleForm` in a
  `ContextBasedDialog`, one flat field list, save button after the last field

## `proposed-*.png` — design proposals

Same rendering technique, same design language. These are **proposals, not implemented screens** —
marked `PROPOSED` in the image. Each one is attached to the issue that specifies it.

| image | proposal |
| --- | --- |
| `proposed-01-editor-simple.png` | editor shell: profile and state chips, Simple mode, section rail, sticky toolbar, validation rail |
| `proposed-02-editor-advanced.png` | Advanced mode: ISO element groups with cardinality, keyword sets per thesaurus, add optional element |
| `proposed-03-publish-gate.png` | publishing blocked by validation errors, jump-to-field, save-as-draft escape |
| `proposed-04-xml-source.png` | XML source document view, changed lines marked, write-back rule stated in the UI |
| `proposed-05-keyword-picker.png` | thesaurus search grouped per registry, free text flagged, `gmx:Anchor` preview |
| `proposed-06-contact-chooser.png` | choose an existing Contact with a `CI_RoleCode`, reuse count, create new |
| `proposed-07-extent-editor.png` | bounding box / polygon / GeoJSON on a map, extent fields, temporal extent error inline |
| `proposed-08-relations-editor.png` | relation table: type, related record, ISO element written, origin, add/remove |
| `proposed-09-create-record.png` | create wizard: profile and origin, template **or blank**, what-you-get panel |
| `proposed-10-list.png` | metadata list with editorial state, selection, batch edit, create |
| `proposed-11-batch-edit.png` | batch edit of one element over a selection with per-record validity preview |
| `proposed-12-harvest-conflict.png` | record harvested while a draft is open, resolved per section |

## `gn-*.png` — GeoNetwork 4.4.12 reference screenshots

Screenshots of a locally installed **GeoNetwork 4.4.12.0** (own docker install, admin account, two
ISO 19139 records imported from MrMap's own test fixtures). GeoNetwork is GPL-2.0-or-later, © the
GeoNetwork team; the screenshots are included as reference material for the comparison, not as
design templates.

* `gn-edit-01-form-top.png` — the record editor in `Simple` mode
* `gn-edit-04-full.png` — the same record in `Full` mode: ISO tree as nested element cards
* `gn-edit-06-xml-source.png` — the `XML` mode source editor
* `gn-edit-07-validation.png` — validation results as rule families with per-rule messages
* `gn-edit-09-keyword-picker.png` — keyword fields as plain text inputs with reorder and delete
* `gn-edit-10-create.png` — create-from-template screen without any template present
* `gn-edit-12-batchedit.png` — the 3-step batch editing wizard
* `gn-edit-14-import.png` — import with record type and UUID handling
