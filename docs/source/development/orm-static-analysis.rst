.. _orm-static-analysis:

======================================
Static ORM analysis of the task code
======================================

This page is the tooling layer of #1398, the third pillar of the task-sql
epic (#1387) after the audit of #1388 (:ref:`celery-task-orm-audit`) and the
naming/ownership contract of #1397
(:ref:`queryset-manager-conventions`), with the measurements of #1395
(:ref:`celery-task-sql-regression`) as its verification partner. It documents
``scripts/orm_lint.py``: what it checks, why each rule exists in this
repository and not in an off-the-shelf tool, what a finding is allowed to
claim, and how the results reach a pull request and SonarCloud.

A static checker can prove syntactic and architectural facts. It cannot prove
that a queryset will cause an N+1, that a production index is missing or that
a plan is optimal. Every suspicion-level finding therefore says *candidate*
and names the place where a suspicion becomes evidence: the test-time SQL
capture of #1395 (``CaptureQueriesContext`` over 0/1/10/100+ cardinality
fixtures, then PostgreSQL ``EXPLAIN``). No finding of this tool may be
presented as a measured speedup, and V2 runtime telemetry (epic #1387, out of
scope here) is not implied by any of it.

What is checked, and where the scope is drawn
#############################################

The analyzer is a standard-library AST walk (``ast`` only, no Django import,
no database, no network — the same offline discipline as the other suites in
``scripts/``). It reads the first-party code of ``backend/`` with the same
exclusions ``sonar-project.properties`` applies to main sources
(``migrations/``, ``tests/``, ``fixtures/`` and friends), so every reported
path is also a path the Sonar scan analyses.

Task scope (rule 1 of #1398: "match actual Celery-decorated tasks/known call
sites; don't flag all Python helpers by file name alone"): every function
decorated by a Celery task decorator (``@shared_task``, ``@celery.task``,
``@app.task`` and their dotted/aliased forms) is an entry point, and the
scope of the task rules is that function plus its **transitive closure over
same-module calls** — statically resolvable without pretending to resolve
cross-module helpers. A module without any decorated task carries no task
scope at all. ``QuerySet``/``Manager`` classes are read everywhere: their
``select_related``/``prefetch_related``/``Prefetch`` plans are collected into
a plan index, so a call site such as
``MonitoringRun.objects.for_monitoring_task()`` knows the plan its
:ref:`queryset-manager-conventions` method applies. That index is why the
cross-module seam of #1397 does not produce false positives, and it is also
why an unresolvable method makes the answer *unknown* — unknown is never a
finding.

The rule catalog
################

Rule IDs are stable; renaming one is a breaking change for existing
suppressions and for Sonar's issue history. Severity escalates only with
evidence (see `Escalation` below).

.. list-table::
   :header-rows: 1
   :widths: 18 12 12 58

   * - Rule ID
     - Gate class
     - Sonar
     - Checks (and what it does not)
   * - ``MRMAP-ORM-001``
     - blocking
     - MAJOR
     - An inline ``select_related(...)``/``prefetch_related(...)``/
       ``Prefetch(...)`` plan inside task scope. Per #1397 the plan belongs on
       the QuerySet of the owning model as a ``for_<consumer>()`` method so it
       is reviewable and countable where it is written. A plain
       ``objects.get(pk=...)`` is a bounded lookup, not a plan, and is never
       flagged; plans inside ``QuerySet``/``Manager`` classes are the
       convention itself and are never flagged.
   * - ``MRMAP-ORM-004``
     - advisory
     - MINOR
     - A manager/queryset call inside a loop or comprehension in task scope:
       one statement per iteration. Receiver qualification keeps non-ORM
       ``.get()`` (dicts, settings, configs) out; chained statements are
       reported once at the evaluating method; the queryset that is the loop's
       own iterable is not an access *per iteration*. A flag is a candidate
       for N+1 — bounded paging loops (the #1237 cleanup, the #1330 paging of
       ``bound_task_attempt_samples``) are legitimately flagged as "one query
       per page" and live in the baseline until someone wants to discuss them.
   * - ``MRMAP-ORM-005``
     - advisory
     - INFO
     - Iteration over a queryset whose model and plan resolve, then access of
       a forward FK/O2O/M2M attribute the expression does not eager-load
       (neither inline ``select_related``/``prefetch_related``/``Prefetch``
       nor the plan index). ``_id`` access, ``pk``, plain columns, reverse
       names (unknown from the model files alone) and unresolvable manager
       methods are not flagged. The suggestion text is deliberately
       conditional: the do-not-prefetch-the-backlog rule may well answer
       "leave it lazy".
   * - ``MRMAP-ORM-SUP``
     - blocking
     - MINOR
     - A ``# orm-lint: ignore`` comment that names no rule ID, names ``all``,
       names an unknown rule or carries no justification. #1398 rule 5:
       suppressions are per rule ID and must say why — the baseline is the
       documented home of accepted findings, blanket silences are not.

Rule IDs ``MRMAP-ORM-002`` (duplicated plans), ``MRMAP-ORM-003`` (query
builder contract inside ``for_*()`` methods) and ``MRMAP-ORM-006`` (query
shape risks) from the issue are **reserved, not implemented**: 002's
"proven equivalent expressions" and 006's severity calibration need the
evidence #1395 produces before they can be low-noise, and 003 largely
coincides with what the plan index and the #1397 review already enforce.
Adding them later does not change the existing IDs.

Rule/tool coverage matrix (#1398 implementation step 1)
########################################################

Measured on 2026-11-17 against this checkout (ruff 0.17.5,
``--isolated``, rules ``DJ001,DJ003,DJ006,DJ007,DJ008,DJ012,DJ013,S608,S610,
S611``; task scope = ``registry/tasks``, ``notify``, ``system``, ``extras``,
``accounts``, ``csw``):

.. list-table::
   :header-rows: 1
   :widths: 22 18 60

   * - Capability
     - Covered by
     - Decision for this repository
   * - Raw SQL / injection (``RawSQL``, ``.raw()``, ``.extra()``, cursors,
       f-string SQL)
     - SonarCloud S2077, S3649 (taint); S5131 (reflected XSS); Ruff S608/
       S610/S611 (syntactic)
     - Keep Sonar's native rules — they are taint-aware and Ruff's syntactic
       duplicates add nothing here. The 26 Ruff S608 sites of the backend are
       in migrations, ``registry/triggers.py`` and test SQL fixtures —
       first-party DDL the sonar sources already exclude or accept; none in
       task code except one accepted hotspot.
   * - Django conventions (``null=True`` on string fields, unordered
       ``Meta.ordering``, ``__str__``, receiver decorator order S6552/DJ rules)
     - Sonar S6552; Ruff DJ001/DJ003/DJ006/DJ007/DJ008/DJ012/DJ013
     - Conventions, not query plans — no overlap with the MRMAP rules. The
       measured Ruff findings (66 backend-wide, 7 in task scope) are pre-existing
       style debt in models and would add noise, so Ruff is not wired into CI
       here; enabling selected DJ rules remains a free follow-up.
   * - Manager-first query plans, task-scoped
     - **nobody** — Semgrep/Sonar/Ruff cannot combine Celery-decorator
       matching with the cross-file ownership knowledge (#1397's plan index)
       the question needs
     - ``MRMAP-ORM-001`` (custom, this tool).
   * - Query-in-loop / lazy relation access
     - django-fox-query, django-check (both experimental); Sonar/Ruff/Semgrep
       do not model iteration of querysets
     - ``MRMAP-ORM-004``/``MRMAP-ORM-005`` (custom, suspicion-level).
   * - Version-upgrade mechanics
     - django-upgrade
     - Useful for Django upgrades; not query analysis. Not adopted here.

The two experimental candidates were evaluated read-only, not installed:

- **django-fox-query 0.1.0** (PyPI wheel inspected): it is a *management
  command* (``find_query``) that must live in ``INSTALLED_APPS`` and runs
  inside a running Django process — reproducible-on-a-bare-checkout is
  already violated. Its N+1 analyzer asks whether the literal text
  ``select_related`` appears in the query's code and otherwise suggests
  eager-loading **every** relation field of the model. That is precisely the
  false-positive profile #1398 warned about, and a plan that eagerly loads
  every relation is the opposite of the do-not-prefetch-the-backlog rule.
  Rejected; its ``values``/``unused`` ideas are noted for ``MRMAP-ORM-006``.
- **django-check** (richardhapb, GitHub-only — not on PyPI, verified via
  ``pip download``): AST model/relationship analysis is the right shape, but
  its own docs limit it to simple managers and shallow call graphs. MrMap's
  managers are ``DefaultHistoryManager`` + ``CTEManager`` compositions and
  cross-module QuerySet chains — the documented limitation is the material
  part of MrMap. Rejected as a dependency; kept as a reference for how far
  AST tracing can reach.

Suppression and the grandfather baseline
########################################

Three mechanisms, in this order of preference:

1. **Fix it the #1397 way**: move the plan into a ``for_<consumer>()`` method
   on the owning model's QuerySet — the audit page lists which paths are
   already scheduled for exactly that (#1392/#1394).
2. **Suppress inline**, for a genuine one-off that stays at the call site:
   a comment on the finding's line or the line above, naming the rule and the
   reason: ``# orm-lint: ignore MRMAP-ORM-001 -- one-off probe lookup, see #1388``.
   Malformed suppressions are blocking findings of ``MRMAP-ORM-SUP``.
3. **Grandfather it**: an accepted pre-existing finding is recorded in
   ``scripts/orm_lint_baseline.json`` keyed by rule + file + a fingerprint of
   the *expression text* (not the line), so moving code around neither hides
   a finding nor resurrects a fixed one. Regenerate deliberately with
   ``python3 scripts/orm_lint.py --update-baseline`` and review the diff of
   the file — an entry disappearing because the code was fixed should be the
   common change.

The initial baseline (7 findings at the time of writing) is the audit's own
leftovers: the inline download plan of ``call_fetch_records`` (owned by #1392)
and the bounded paging/recovery loops of ``cleanup_harvesting_job_temp_files``,
``recover_registration_reference_work`` and ``bound_task_attempt_samples``.

Running it locally
##################

From the repository root::

    python3 scripts/orm_lint.py                 # text report + gate (new blocking findings exit 1)
    python3 scripts/orm_lint.py --fail-on nothing   # just look
    python3 scripts/orm_lint.py --format sonar -o reports/orm-lint/orm-issues.json
    python3 scripts/orm_lint.py --format sarif -o reports/orm-lint/orm-issues.sarif
    python3 scripts/orm_lint.py --format github     # ::notice/::warning workflow commands
    python3 scripts/test_orm_lint.py            # the fixture suite (also scripts/check_repo_tooling.sh)

The full text report lists grandfathered findings too (marked
``[grandfathered]``); every machine format carries only the new ones, so what
CI publishes and what a reviewer annotates is what changed. The suite runs
the analyzer over the real repository as one of its checks — the committed
baseline must stay green at HEAD.

Evaluating a finding against #1395
##################################

A suspicion finding (004/005) is the *beginning* of an investigation:

1. Read the loop: is the access per row of a collection that grows in
   production (the audit page names the cardinalities), or per page of a
   bounded sweep? Bounded is fine and stays — in the baseline, not in silence.
2. Reproduce the question with the harness of :ref:`celery-task-sql-regression`
   (``CaptureQueriesContext`` over the fixture cardinalities): does the query
   count grow with the rows, or with the pages?
3. If it grows with the rows: move the plan to the owning model per
   :ref:`queryset-manager-conventions`, pin the query count with a guard and
   retire the baseline entry / let the finding go green.
4. If it stays flat: the tool flagged a candidate the SQL disproved — that is
   the designed division of labour; no action but maybe a suppression with
   the measurement in its justification.

CI integration
##############

``quality-assurance.yml`` runs the job ``orm-static-analysis`` on every PR
(including forks — nothing in it needs secrets) and on pushes to ``develop``
and ``master``. It fails the PR only on **new** findings of the blocking
rules; it also writes the Sonar generic-issue JSON and the SARIF report as
workflow artifacts and annotates new findings on the diff. The conditional
``sonarcloud`` job downloads the artifact and passes
``-Dsonar.externalIssuesReportPaths=reports/orm-lint/orm-issues.json`` to the
existing scan — external findings are managed by the tool, not by the Quality
Profile, so no Sonar rule is duplicated by anything here, and the existing
coverage/quality-gate flow is untouched. The generic report declares its
rules with the full Clean Code Taxonomy metadata (``engineId``,
``cleanCodeAttribute``, one ``MAINTAINABILITY`` impact each) that the
scanner's external-issue validator demands — a partial ``rules`` entry
aborts the whole import, which this PR's own CI run learned the hard way.
When Sonar secrets are absent (fork PRs), the standalone job still ran and
its artifacts still answer.

Escalation
##########

Blocking today: 001 and SUP — 001 because the contract it enforces is
decided (#1397) and its fixture suite pins its false-positive behaviour;
advisory today: 004, 005. Escalating an advisory rule to blocking is a human
decision (as every enforcement change here), taken once #1395-style evidence
shows the rule's flags carry signal — it is a one-line change of
``"blocking"`` in the rule table of ``scripts/orm_lint.py`` plus the fixture
suite updated to the new gate semantics. No autofix exists for any rule and
none is planned: rewriting joins, prefetches, indexes or migrations
unsupervised is exactly what #1398 rule 5 forbids.

Writing a new rule
##################

``scripts/orm_lint.py`` is one file, ordered as: rule table (add the ID,
severity, Sonar mapping and gate class there first), queryset-shape helpers,
``FunctionWalker`` (one function in task scope, 001/004/005 visit in it), and
the report writers (nothing to change for a new rule — the formats iterate
over the findings). A finding needs: a stable ID, a message that names the
evidence path (#1395) rather than claiming a cost, and a fingerprint
expression whose text survives line moves (``fp(rule, file, function,
expression)``). The new rule's positive **and negative** fixtures belong in
``scripts/test_orm_lint.py`` before the rule ships — the negative fixtures of
this suite are the library of what must not be flagged, from ``dict.get()``
in a loop to reverse-relation reads to the bounded page.
