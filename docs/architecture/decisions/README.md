# Architecture decision records

This directory holds the architecture decision records (ADRs) of MrMap. An ADR
records a decision that shapes the system, the context that forced it, the
alternatives that were weighed, and the consequences the project accepts. It is
a historical document: once accepted it is never edited in place, only
succeeded by a new record that supersedes it.

The records live beside `docs/architecture.md` and the other design notes under
`docs/`, and are plain Markdown rather than part of the Sphinx tree in
`docs/source`. They describe decisions for maintainers and for the automation
that builds the portal; the portal consumes them as sources, it does not own
them.

## Numbering and naming

Files are named `ADR-<four-digit-number>-<kebab-topic>.md`, numbered in the
order the records are opened. The number is assigned when the record is opened,
not when it is merged, and is never reused.

## Status values

| Status | Meaning |
| --- | --- |
| `Proposed` | Open for review. Not yet binding. |
| `Accepted` | Binding. Implementation must follow it. |
| `Superseded by ADR-NNNN` | Replaced. Kept for the history. |

## Structure of a record

Every record answers the same headings, in this order: Context, Decision,
Validation, Consequences, Implementation. The Validation section names the
evidence a later change must produce to show it still honours the record, with
the measured baseline of the day the record was written. A record without
validation is prose, not a contract.

## Index

| Record | Status | Topic |
| --- | --- | --- |
| [ADR-0001](ADR-0001-autonomous-documentation-architecture-and-coverage-contract.md) | Proposed | Autonomous documentation architecture and coverage contract (epic #1589) |

