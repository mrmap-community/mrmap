.. _etf-conformity-retirement:

======================================
ETF conformity retirement (gate #1528)
======================================

This page is the inventory and decision record of #1528, the required gate
of epic #1527 (ETF retirement). It is the reviewed ADR its acceptance names:
the liveness evidence of #1394/#1495 reproduced on current ``develop``, the
complete footprint of the legacy conformity family, the deployment evidence
that first-party inspection cannot answer (**stated as unknown, never as
zero**), the rollout contract #1530/#1532 must honor, and the owner decision
the removal waits for. Nothing on this page has been executed against a
production deployment: #1528 mutates no data.

The decision itself lives in the `Decision register of #1528
<https://github.com/mrmap-community/mrmap/issues/1528>`_, asked and recorded
through ``scripts/decisions`` per :ref:`development-decision-requests`. Until
a row reads
``Accepted``, the removal PRs #1529-#1533 stay gated.

Recommendation (agent): **full retirement** of the family — the ETF validator
stack, the tasks, the plugin helpers and all twelve legacy tables — not the
ETF-only variant that would retain the internal rule machinery. The evidence
below shows the whole family is one closed, unreachable island: the internal
half has no consumer either, so an ETF-only retirement would keep a second
dead half alive for no consumer.

Liveness evidence, reproduced on current develop
#################################################

Re-derived on ``develop`` at ``019f17a42`` (2026-11-18), in the job's own
Compose stack on the prebuilt backend image; commands and results:

.. code:: text

    docker compose run --rm --no-deps -e MRMAP_USER=mrmap -e MRMAP_PASSWORD=mrmap \
      django-tests python manage.py test \
        tests.django.registry.tasks.tests_conformity_tasks \
        tests.django.test_celery_worker_config --noinput
    # Ran 12 tests in 0.026s — OK

What those two guard modules pin (:ref:`celery-task-sql-regression`), and what
the static sweep on this checkout re-confirms:

*   **no first-party dispatcher**: no ``delay``, ``apply_async``,
    ``send_task`` or beat row names ``async_run_conformity_check``,
    ``async_run_conformity_check_etf`` or
    ``async_run_conformity_check_internal``; the only names outside
    ``registry/tasks/conformity.py`` are the test module itself;
*   **no API or UI surface**: zero hits for the family below
    ``registry/serializers``, ``registry/views``, ``registry/urls.py``, the
    schema layer, ``extras/`` and the whole ``frontend/`` tree (one false hit
    in a PNG binary);
*   **no scheduled delivery**: the beat rows created at migrate
    (``registry/apps.py``, see :ref:`celery-task-orm-audit`) do not include
    the family, and nothing else registers a schedule for it;
*   **the tasks could not answer a by-name delivery anyway**: their bodies
    fetch through ``ConformityCheckRun.objects`` — the *abstract* base whose
    table the migration history never created (verified by live
    introspection, see the inventory) — and the external task's plugin calls
    ``resource.get_xml_view_url()``, a method **defined nowhere** in the
    repository, so ``QualityEtf.__init__`` raises ``AttributeError`` before
    any validator HTTP call;
*   the registered task objects remain reachable **by name only** (the tasks
    are imported through ``registry/tasks/__init__.py``, so a broker message
    naming them is still executed by a worker — it just cannot complete; the
    standard worker of ``docker-compose.yml`` consumes the default queue
    without a ``--queues`` restriction and no ``CELERY_TASK_ROUTES`` routes
    the family elsewhere).

The family is dead code kept reachable only through the broker's by-name
delivery. That is exactly the shape a retirement, not a query optimization,
resolves — the disposition #1394 reported and #1495 deferred to the owners.

Table and schema inventory
###########################

The family is 9 concrete models + 3 M2M through tables; the abstract base
``ConformityCheckRun`` creates no table. Table names read live from a
migrated schema (introspection on a fresh migrate of this checkout):

.. code:: text

    registry_conformitycheckconfiguration                      (config base)
    registry_conformitycheckconfigurationexternal              (ETF config)
    registry_conformitycheckconfigurationinternal              (internal config)
    registry_conformitycheckconfigurationinternal_mandatory_rul3508   (M2M)
    registry_conformitycheckconfigurationinternal_optional_rule2986   (M2M)
    registry_ruleset                                           (internal rules)
    registry_rule                                              (internal rules)
    registry_ruleset_rules                                     (M2M)
    registry_conformitycheckrun                                **does not exist** (abstract base)
    registry_wmsconformitycheckrun                             (run subclass)
    registry_layerconformitycheckrun                           (run subclass)
    registry_featuretypeconformitycheckrun                     (run subclass)
    registry_datasetmetadataconformitycheckrun                 (run subclass)

Row counts on a fresh migrate are 0 for all twelve tables — that is a property
of this throwaway database, **not evidence about deployments**: real counts
and stored ETF report sizes are listed as unknown below. No model of the
family carries guardian object-permission tables (no
``*groupobjectpermission`` table exists for any of them), and **no model
outside the family references it**: every FK is intra-family (checked through
``registry/migrations/0001_initial.py`` and every later migration touching
the family: only 0052 text-column null rejection and 0053 access constraints
touch these model names; no FK from services, metadata or history into the
family and none from the family out).

Permissions and content types
##############################

Django's migrate auto-creates the model permissions: **9 content types and 36
permissions** (4 per concrete model) exist in every migrated database. The
removal migration #1530 must take them with the models (deleting the content
types via the contenttypes post-migrate purge, which the model removal
triggers on its own). Nothing grants them: no permission migration, no
group or role rows name them (verified by grep over ``accounts/`` fixtures
and all migrations).

Seed fixtures
###############

Six fixtures seed the family's configuration and rule data:

.. code:: text

    backend/registry/fixtures/conformityCheckConfigurationInit.json
    backend/registry/fixtures/conformityCheckConfigurationExternalInit.json
    backend/registry/fixtures/conformityCheckConfigurationExternalWmsInit.json
    backend/registry/fixtures/conformityCheckConfigurationInternalInit.json
    backend/registry/fixtures/ruleInit.json
    backend/registry/fixtures/ruleSetInit.json

**No code loads any of them** — no ``loaddata`` call, no ``post_migrate``
handler and no management command names these fixtures anywhere in the
repository; an operator who wanted the seed data had to load them by hand.
Whether any deployment did is unknown (see below). #1530 removes them with
the family.

Code and infrastructure surface (the removal list for #1529/#1530)
####################################################################

Backend (all imports are family-internal; the only outside importer is
``tests/django/test_celery_worker_config.py`` consuming the time-limit
constants):

* ``backend/registry/models/conformity.py`` (180 lines, all 9 models) and its
  re-export in ``registry/models/__init__.py``;
* ``backend/registry/managers/conformity.py`` (52), ``registry/enums/conformity.py``
  (56, imported only by the family);
* ``backend/registry/tasks/conformity.py`` (115, the three tasks) and its import
  in ``registry/tasks/__init__.py``;
* ``backend/registry/helper/plugins/etf.py`` (186) and ``internal.py`` (146) —
  the only importers are ``tasks/conformity.py``; the ``plugins/`` package
  itself has no other module;
* ``backend/registry/settings.py``: ``CONFORMITY_ETF_TASK_SOFT_TIME_LIMIT_SECONDS``
  / ``HARD`` (consumed only by ``tasks/conformity.py`` and
  ``tests/django/test_celery_worker_config.py`` — the test's assertions move
  out with the constants in the same PR) and the three
  ``CONFORMITY_DEFAULT_*_MESSAGE`` strings;
* ``backend/MrMap/settings.py``: ``BASE_URL_FOR_ETF`` (env
  ``MRMAP_BASE_URL_FOR_ETF``) and the comment block at the
  ``CELERY_TASK_SOFT_TIME_LIMIT`` which is justified by the ETF task budget —
  the comment must be re-grounded, the worker-wide limit itself stays;
* ``backend/tests/django/registry/tasks/tests_conformity_tasks.py`` (85) —
  the guards retire with the family they pin; the coverage matrix and the
  conformity disposition in :ref:`celery-task-sql-regression` and
  :ref:`celery-task-orm-audit` update in the same PR;
* ``backend/locale/de/LC_MESSAGES/django.po``: the family's msgids drop out on
  the next ``makemessages`` (regenerate, never hand-edit);
* migrations: the historical 0001/0052/0053 stay untouched (never edit
  history); the retirement is **one new migration following the current
  registry leaf** (``0057`` at the time of writing — re-check the leaf when
  #1530 branches, run ``scripts/migration_graph_smoke.py``).

Validator infrastructure (#1529):

* ``docker/inspire-validator/`` (Dockerfile, Dockerrun.aws.json, README,
  res/docker-entrypoint.sh, res/squid.conf);
* the ``inspire-validator`` service in ``docker-compose.dev.yml`` (port
  5557:8080, ``extra_hosts`` for the callback) and the prebuilt-file comment
  naming its unpinned port;
* the "run ETF validator" task in ``.vscode/tasks.json``;
* the environment docs entry for ``MRMAP_BASE_URL_FOR_ETF``.

Deployment evidence that first-party inspection cannot answer
##############################################################

Each of these is **unknown from this repository** and must be answered by the
operator of every deployment **before** the destructive migration of #1530
runs — none of them may be assumed to be zero:

1. **by-name task callers outside this repository**: custom scripts, other
   deployments' automation or hand-built broker messages delivering
   ``async_run_conformity_check*``. First-party code names nothing (proven
   above); external callers are invisible here. Broker evidence to request:
   a ``celery inspect`` / flower listing plus a queue-content dump of the
   ``default`` queue.
2. **queued and in-flight deliveries**: message counts for the three names on
   the broker right now, and any running ETF task (a full attempt may wait
   for the validator up to the 6 h soft limit,
   ``CONFORMITY_ETF_TASK_SOFT_TIME_LIMIT_SECONDS``).
3. **Beat rows in deployed databases**: ``django_celery_beat`` is installed,
   so a deployment's database can hold ``PeriodicTask``/``CrontabSchedule``
   rows naming the legacy tasks even though nothing in-repository creates
   them. Query every deployment before removing the task names.
4. **row counts and report sizes** in the twelve real tables (the run tables
   store ETF reports as text columns; #1507 exists precisely because their
   timestamps are unreliable — see the retention coordination).
5. **env/override footprint**: ``MRMAP_BASE_URL_FOR_ETF`` values, any compose
   override adding the validator service, and any mounted volume belonging to
   an ``inspire-validator`` container started outside this compose tree.
6. **manual fixture loads**: whether any deployment ever ran ``loaddata`` on
   the six seed fixtures.

Rollout contract for #1530 and #1532
#####################################

Derived from the unknowns above; #1530 (schema) and #1532 (runtime removal)
may only execute this after the owner decision and the operator sign-off
that the checks came back clean:

* **export before drop**: ``pg_dump -t`` of the twelve tables (or a full
  backup taken after the last write), stored outside the database, plus the
  restore rehearsal #1509 owns; the export is the rollback object.
* **drain first**: no by-name caller left (check 1), queued messages for the
  three names at zero and no ETF task in flight (check 2) — or the operator
  deliberately purges those queue entries inside the maintenance window;
  Beat rows (check 3) deleted via the deployment's own admin, not by silent
  migration, so the audit trail names who removed them.
* **maintenance window with destructive approval**: dropping twelve tables is
  destructive data work; per epic rule it carries an explicit approval from
  the operator of each deployment, never a migration that "just runs".
* **migration order**: code removal and the drop table lands as one PR on one
  registry migration following the then-current leaf; the export exists
  before it, the worker restart after it. A deployment mid-upgrade must not
  run a worker from before the PR against a database from after it — the
  tasks would be registered but their tables gone (their by-name delivery
  fails anyway on the abstract read, which is the safety margin here).
* **rollback**: restore the export and the previous image; no data is
  re-derived.

Validation invariants that must stay untouched
###############################################

The retirement must not touch any validation that is not the conformity
family. Independent of this family, and verified to have no import edge into
it, are: the ISO/INSPIRE metadata profile validation of records, the CSW
harvest-time documents, the monitoring/probe checks, the security proxy's OWS
request validation and the XML schema parsing of ``registry/mappers``. The
ETF validator only ever consumed a public XML re-render
(``BASE_URL_FOR_ETF + ...`` — a method not even defined anymore) and wrote
into the twelve tables; removing it removes no validation capability, it
removes a quality-test round-trip whose results no screen, API or export
answers today.

Retention coordination with #1497
##################################

* #1507 (conformity lifecycle and bounded report retention) is **on hold**
  per its own banner while this decision stands open. If the owner approves
  full retirement, #1507 is superseded — retention on tables about to be
  dropped is churn — and its graph edge and parent-scope mention are removed
  from #1509. If ETF-only is chosen instead, #1507 narrows to the retained
  internal scope. Either outcome is recorded in the issue bodies and the
  native dependency metadata as part of this gate.
* The #1528 decision also settles the storage question #1497 lists the family
  under: full retirement bounds that growth by removing the tables outright,
  strictly better than a retention policy on dead rows.

Dispositions recorded here
###########################

* **#1394** (audit housekeeping task): its reported evidence — the family is
  registered, unreachable by first-party dispatch, cannot answer — stands
  reproduced on ``019f17a42`` above; #1394's "left to its owners" question is
  now the open decision row of this page.
* **#1409 R16 / P-6** (:ref:`outbound-ogc-request-audit`): the ETF client's
  unpooled, timeout-less transport (R16) and its pending P-6 are **moot under
  full retirement** — the transport retires with the family instead of being
  pooled; under ETF-only retention P-6 stays a live finding. This disposition
  is recorded so the audit page stays honest once #1530 lands.
* **The #1495 matrix** (:ref:`celery-task-sql-regression`) deliberately pins
  no query guard for the family; its baseline entries retire with it under
  full retirement.

Open decision (owner, via scripts/decisions)
#############################################

The question asked on #1528 with this recommendation:

* **Q1 — scope**: full legacy retirement (recommended) vs ETF-only with a
  named retained internal scope. Nothing in-repository answers which (if any)
  external party reads the internal rule configuration; that is owner
  knowledge.
* **Q2 — rollout contract**: is the contract above (export-before-drop,
  drained broker, per-deployment destructive approval, one migration at the
  current leaf) the agreed shape for #1530/#1532?
* **Q3 — #1507**: supersede it on full retirement as described?

Until these rows are ``Accepted`` the implementation PRs stay gated; silence
records nothing.

How to re-derive every claim
#############################

.. code:: text

    # liveness guards (this stack recipe: backend/AGENTS.md "Prebuilt")
    docker compose run --rm --no-deps -e MRMAP_USER=mrmap -e MRMAP_PASSWORD=mrmap \
      django-tests python manage.py test \
        tests.django.registry.tasks.tests_conformity_tasks \
        tests.django.test_celery_worker_config --noinput
    # by-name dispatch / API / frontend sweep (run from backend/)
    git grep -n "async_run_conformity"        # only tasks + their tests
    git grep -ln "Conformity" -- registry/serializers registry/views registry/urls.py extras
    # (empty) ; git grep -iln conformity -- frontend/   # only a PNG false hit
    # live table names / counts / permission footprint
    docker compose run --rm --no-deps backend python manage.py shell -c "..." \
      # introspection table_names() filtered to the family, ContentType/Permission counts
