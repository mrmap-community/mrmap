(decision-records)=

# Architecture decisions

The records of decisions that shaped the system, rendered from
``docs/architecture/decisions/``. A record is a historical document: once
accepted it is not edited in place, only succeeded by a record that supersedes
it, so reading one tells you what was known and chosen at the time - not
necessarily what is true today. The numbering, status and supersession
conventions are in ``docs/architecture/decisions/README.md``.

| Record | What it decided |
| --- | --- |
| ADR-0001-autonomous-documentation-architecture-and-coverage-contract | The architecture this portal is built under: deterministic extraction over generated prose, evidence as the unit of trust, the audience taxonomy the sections above follow, the artifact schema, and the validation gates #1597 through #1610 are measured against. |
| ADR-README | The conventions the records are written under: numbering, what each status commits the project to, and how a record is superseded rather than edited. Read this before reading any record. |

```{toctree}
:hidden:
:maxdepth: 1

ADR-0001-autonomous-documentation-architecture-and-coverage-contract
ADR-README
```
