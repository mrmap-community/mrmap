.. _queryset-manager-conventions:

========================================
QuerySet and Manager conventions for tasks
========================================

This page is the convention of #1397: where the read queries of a Celery task
(or any other background consumer) are built, how such a method is named and
exposed, and what a reviewer checks. It exists because a task that carries its
own ``.select_related(...).prefetch_related(...).annotate(...)`` chain hides
what it reads: the plan cannot be reviewed, reused or counted where it is
written, and a second consumer of the same aggregate writes a second, subtly
different chain. The audit of #1388
(:ref:`celery-task-orm-audit`) is the matrix of which paths need such a method
and which are fine as they are.

What belongs into a QuerySet method — and what does not
########################################################

**Centralize nontrivial, reused or task-specific read-access policy** on the
QuerySet of the owning model: ``select_related`` plans, bounded or filtered
``Prefetch``/``prefetch_related``, projections, annotations, aggregations and
comparable scoped aggregation methods. Distinct tasks get distinct narrow
plans — the broad, view-oriented ``prefetch_whole_service()`` stays what it
always was, the plan of the API, and never becomes the plan of a task.

**Leave in the task** everything that is business-process orchestration:
Celery chain/chord/retry wiring, network calls (``OgcClient``), XML
transforms, status progression and user notifications. A QuerySet method
selects rows; it does not run a process.

**Do not wrap the trivial.** A one-off ``objects.get(pk=...)`` or a beat's
``get(name=...)`` is a bounded indexed lookup, not a plan; giving it a wrapper
adds a name to remember without removing a chain to review (#1397 rule 6; the
audit lists the explicit *no-method* decisions).

Naming and ownership
####################

Name the method for the **intent of the consumer**, not for the ORM mechanics:

- ``for_monitoring_task()`` — the plan of the ``run_*_monitoring`` tasks;
- ``for_harvest_import()`` — the plan of one stored file's import;
- ``for_probe_execution()``, ``for_update_diff()``, ``for_cleanup_batch()`` —
  the proposals of #1398's follow-ups, named after who asks.

A reader of the call site should know which task the plan serves and be able
to look up *why* each relation is in it; the name ``with_three_joins()`` says
neither. Names live per model. A shared mixin is only for genuinely identical
semantics across models, never as a speculative framework — there is no task
repository and no generic ORM layer here, and #1398 keeps CI and Sonar
enforcement syntactic.

**Reuse before naming.** If an existing method's contract already matches what
the consumer needs, call it — an inline chain is only a candidate for a new
method once the contract it should have is actually expressible by one.

**Expose the method the way the model is set up today**: ``Manager.from_queryset``
(``registry/managers/update.py``), ``as_manager()``
(``registry/models/harvest.py``) or explicit delegation from the manager
(``registry/managers/monitoring.py``). Do not switch a model's exposure style
as a side effect of adding one method, and preserve inherited manager
composition — ``HarvestingJobManager`` stays ``DefaultHistoryManager`` +
``CTEManager`` returning ``HarvestingJobQuerySet``, tree managers keep their
managers.

The API contract
################

A query-plan method returns a **lazy, chainable queryset**. After it:

- ``.filter()``, ``.get()``, ``.using()`` and any authorized scoping still
  work — the method narrows *which columns and relations an answer carries*,
  it never decides *which rows are visible*;
- the default manager's filters are retained unless the method says otherwise
  in its docstring;
- nothing is materialized. Where materialization, a page bound or a lock is
  genuinely wanted, it is a **separately named operation at the call site**
  — ``.select_for_update(of=("self",))``, ``[:batch]``, ``.iterator()`` — so
  the transaction and locking scope stay visible where the work runs. The
  harvest import is the standing example: ``for_harvest_import()`` answers the
  join plan, ``select_for_update`` stays in the task
  (``registry/tasks/harvest.py``).

The docstring of every such method names: the included relations and *which
read of the consumer needs each* (a relation without demonstrated use does
not enter the plan), the anticipated cardinality (1 row, a bounded page, one
service and its elements), and the intended consumer task(s).

The do-not-prefetch-the-backlog rule
####################################

A narrow plan reads the row and the chain it needs — never the collection the
consumer is working through. ``TemporaryMdMetadataFile.for_harvest_import()``
joins ``job``, ``job__service`` and ``job__service__auth`` and *nothing* that
touches the job's other files: the import drains that table one locked row at
a time, and a plan which prefetched the backlog would read all 411k remaining
rows per imported file (the shape #870 and #886 removed from the API reads).
The same rule reads back through the aggregates: the statistics methods of
``HarvestingJobManager`` answer counters from correlated subqueries bounded by
the outer page (#885, #1037) instead of aggregating the relation table per
run. When reviewing a plan, ask what it costs when the collection around the
row is large — the answer must not be "everything".

Worked examples
###############

- ``MonitoringRunQuerySet.for_monitoring_task()``
  (``registry/managers/monitoring.py``): the plan of the
  ``run_{wms,wfs,csw}_monitoring`` tasks. It joins exactly ``setting`` — the
  one relation those tasks read (the probes to dispatch come from the
  setting); the probe lists stay lazy reads of the setting's two probe
  relations, because their relation names differ per concrete run model and
  the base model has no ``setting`` field at all. The three task call sites
  read ``...objects.for_monitoring_task().get(pk=run_pk)``; the SQL is the
  SQL of the inline chain it replaced, one row, one join.
- ``TemporaryMdMetadataFileQuerySet.for_harvest_import()``
  (``registry/managers/harvesting.py``): as described above — the plan of
  ``import_md_metadata_file``, both the chunk importer and the single-row
  seam, 1 row and three one-to-one joins per import.

The per-domain migrations of the remaining audit candidates
(``for_probe_execution()``, ``for_update_diff()``, ``for_cleanup_batch()``)
are owned by #1392/#1393/#1394 — one independently scoped change per PR,
never a centralized rewrite. #1395 owns the repeatable query-count and
memory-bound tests built on the shared helper in ``tests/django/utils.py``
(``QueryPlanMixin``); static enforcement is #1398's.

The reviewer checklist
######################

For a PR that adds or changes a query-plan method or adopts one:

1. Is there a *real* consumer with a nontrivial plan — not a trivial
   by-pk/by-name lookup dressed up as a method (#1397 rule 6)?
2. Does every relation in the plan name the read that needs it? Anything
   without a named read comes out.
3. Is the plan bounded against the collection around the row — no prefetch of
   the backlog the consumer drains?
4. Does the method return a lazy queryset that still takes ``.filter()``,
   ``.get()``, ``.using()`` and authorized scoping, keeping the default
   manager's filters?
5. Are locking, paging and materialization separate, named call-site
   operations with the transaction scope intact?
6. Is the model's existing manager exposure kept (``from_queryset`` /
   ``as_manager`` / delegation), and is inherited manager composition
   (history, CTE, tree) untouched and still functional?
7. Do the docstring's relations, cardinality and consumer match the code?
8. Is the inline query plan it replaces deleted, not left as a second copy?
9. Before/after: does the change answer the same rows with the same (or
   fewer) statements? The audit's proposed-method table carries the expected
   shape; a new plan comes with a query-count test using the shared helper,
   and large-volume cases prove their bound with a 0/1/10 fixture.
10. Does the method keep signals, history, retries and return types of the
    path it serves?
