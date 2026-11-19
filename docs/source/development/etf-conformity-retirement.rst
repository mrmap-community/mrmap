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
through ``scripts/decisions`` per :ref:`development-decision-requests`. The
three rows below still read ``Pending`` — re-read them with
``scripts/decisions --issue 1528 scan`` rather than trusting this page. The
removal PRs (#1458, #1529, #1530, #1531, #1532) were carried out on the operator's
instruction while those rows stood open; that deviation from the gate is
recorded where it happened, below, and no executed merge on this page is
presented as an accepted decision. What the open rows still govern is the
destructive half: applying ``0062`` to a live database (Q2), any scope a
deployment still retains (Q1) and the fate of #1507 (Q3).

Recommendation (agent): **full retirement** of the family — the ETF validator
stack, the tasks, the plugin helpers and all twelve legacy tables — not the
ETF-only variant that would retain the internal rule machinery. The evidence
below shows the whole family is one closed, unreachable island: the internal
half has no consumer either, so an ETF-only retirement would keep a second
dead half alive for no consumer.

Liveness evidence, reproduced on current develop
#################################################

Re-derived on ``develop`` at ``019f17a42`` (2026-11-18), in the job's own
Compose stack on the prebuilt backend image. The run and its answer are kept
as the audit trail of the gate. It is **not a runnable command any more** —
the first module was removed by #1458 and the family with #1530; what still
runs today is named in the last section of this page.

.. code:: text

    # as executed on 019f17a42 on 2026-11-18 (do not copy: the first
    # selection target no longer exists)
    docker compose run --rm --no-deps -e MRMAP_USER=mrmap -e MRMAP_PASSWORD=mrmap \
      django-tests python manage.py test \
        tests.django.registry.tasks.tests_conformity_tasks \
        tests.django.test_celery_worker_config --noinput
    # Ran 12 tests in 0.026s — OK

What those two guard modules pinned at that revision, and what the static
sweep on this checkout re-confirms:

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

That last bullet is the one claim above which no longer holds on current
``develop``, and it holds no more by a wider margin: #1458 unregistered the
tasks, so a delivery naming them is discarded as unregistered (the #1199
behaviour) instead of executed and failed, and #1530 removed the models, the
managers and all twelve tables. Nothing on develop can answer those three
task names at all now. The guard module which pinned the liveness evidence is
itself gone, which is why the matrix of :ref:`celery-task-sql-regression`
lists the family as retired rather than green.

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

Code and infrastructure surface (what left, and which PR took it)
####################################################################

**Executed partway (#1458).** The task half of this list has already left:
``backend/registry/tasks/conformity.py``, its import in
``registry/tasks/__init__.py``, the liveness guard
``backend/tests/django/registry/tasks/tests_conformity_tasks.py``, the two
``CONFORMITY_ETF_TASK_*_TIME_LIMIT_SECONDS`` constants and the
``test_celery_worker_config`` assertions which read them are removed by
#1458, carried out on the operator's instruction while Q1 below stands
open. The tasks are no longer registered: a by-name delivery is now
discarded as unregistered (the #1199 behaviour) instead of executed and
failed. Everything else on this page - models, managers, enums, the plugin
helpers, the fixtures, the ``CONFORMITY_DEFAULT_*`` messages,
``BASE_URL_FOR_ETF``, the validator infrastructure and the twelve tables -
remains gated on Q1-Q3 and owned by #1529/#1530/#1531.

**Executed (#1530).** On the operator's instruction — the same shape as
#1458 and #1529 above — the whole family left the codebase with #1530
while the Q1-Q3 rows below still read Pending; that deviation from the
gate is recorded here, not hidden. Removed: ``registry/models/conformity.py``
(all 9 models) and its re-export in ``registry/models/__init__.py``,
``registry/managers/conformity.py``, ``registry/enums/conformity.py``,
``registry/helper/plugins/`` (``etf.py``, ``internal.py`` and the package
itself) and ``registry/helper/mapping_helper.py``; the six seed fixtures;
and all twelve tables through the one migration
``registry/migrations/0062_retire_conformity_check_family``, which follows
the then-current leaf 0061 and additionally deletes the family's 9 content
types (post-migrate never prunes them, and an explicit drop keeps the
database free of ghost permissions). The upgrade path was verified on a
scratch database built from pre-#1530 code: fixtures loaded, representative
ETF/internal run rows, unrelated rows, then the new code — twelve tables
and their permissions gone, survivors intact, reverse-then-forward clean.
The German catalog lost the family's four run help texts via the canonical
``makemessages``. What the family page named as remaining — the
``CONFORMITY_DEFAULT_*`` messages and ``BASE_URL_FOR_ETF`` — was retired
by #1531, the documentation and audit sweep ran with #1532, and the
final verification — the exhaustive tracked-tree sweep, the fresh
installs, the upgrade rehearsal and the runtime checks — ran with #1533
and is recorded at the end of this page.
Applying the migration to a live deployment stays destructive data work:
the export-before-drop and maintenance-window contract below binds the
operator, and nothing in the migration invents or re-derives data.

**Executed (#1531).** The settings residuals named above are removed.
``BASE_URL_FOR_ETF`` (env ``MRMAP_BASE_URL_FOR_ETF``) left
``MrMap/settings.py`` — nothing read it after the ETF client retired —
and so did the three unused ``CONFORMITY_DEFAULT_*_MESSAGE`` strings of
``registry/settings.py``; the German catalog lost their msgids via the
canonical ``makemessages``. The ETF validator rationale left the
allow-list comment, while the shipped ``ALLOWED_HOSTS_PRESET``, its
environment docs and its ``test_allowed_hosts_settings`` guard stay for
the callers which still reach the backend without a browser Host.

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
  registry leaf** — it shipped as ``0062_retire_conformity_check_family``,
  renumbered once develop's keyword-link migration took 0061.
  ``scripts/migration_graph_smoke.py`` is the check which names that
  collision before a push, and it is what any later branch beside this leaf
  runs.

Validator infrastructure (**executed (#1529)**): the service, its image
and its development tooling are removed:

* ``docker/inspire-validator/`` (Dockerfile, Dockerrun.aws.json, README,
  VERSION, LICENSE, res/docker-entrypoint.sh, res/squid.conf, the apache
  proxy config and the bundled Functx resources);
* the ``inspire-validator`` service in ``docker-compose.dev.yml`` (port
  5557:8080, ``extra_hosts`` for the callback), the prebuilt-file comment
  naming its unpinned port, the ``inspire-validator`` term in the AGENTS.md
  list of host-pinned ports, and - with the subtree gone - the
  ``docker/inspire-validator/**`` Sonar exclusion;
* the "run ETF validator" task in ``.vscode/tasks.json``;
* the environment docs entry for ``MRMAP_BASE_URL_FOR_ETF``: the
  ``DJANGO_ALLOWED_HOST_DEFAULTS`` description no longer names the validator
  as a caller. The settings constant itself and the shipped allow-list
  preset stay for #1531.

Nothing else in the tracked tree referenced the service: the prebuilt image
work (``dev-images.yml``, ``scripts/dev_image_id.py``) never built or
published it, and no workflow, nginx conf or deployment manifest names it.
The regression guard is ``scripts/test_validator_retirement.py``: it sweeps
the tracked Compose, VS Code, Sonar and ``docker/`` surfaces for the
validator's name and, where docker is present, resolves every committed
Compose variant - failing on a validator service, on its build context, on
its old host port 5557, or on a resolution in which the shared networks no
longer survive.

Operator cleanup: what a host may still carry (#1529)
######################################################

The removal is a checkout change; it deletes nothing that already sits on a
host. An ``inspire-validator`` container, the image it was built into, or a
mount it used can outlive the service definition, and only the operator of
that host can tell whether the object is still wanted. Every step below is
targeted removal by exact name - the rule the agent stacks follow as well
(AGENTS.md "Docker ownership and cleanup"): a blanket ``docker volume
prune``, ``docker container prune`` or ``docker system prune`` would also
take the named volumes of other stacks (``frontend-node-modules`` is one of
them) and the shared, deliberately retained prebuilt dependency images.

1. **Containers.** List first, then remove by exact id, never by a name
   pattern that could match a running job:

   .. code:: text

       docker ps -a --filter "name=inspire-validator"
       docker ps -a --filter "label=com.docker.compose.service=inspire-validator"
       docker rm <exact-container-id>

   The label filter also finds containers of agent stacks whose project name
   prefixed the container name; ``docker inspect`` shows the project label to
   check before removing one another job might own. A *running* container
   named for the validator is a deployment doing something this repository
   no longer ships: find out what reads it before removing anything.

2. **Images.** The dev compose built the image under the project-prefixed tag
   ``<project>-inspire-validator`` (``docker compose config --images``
   listed it per project); hand-built or hand-tagged copies can carry any
   name. List candidates, then remove only what no container references:

   .. code:: text

       docker images --format '{{.Repository}}:{{.Tag}}' | grep -Ei 'inspire-validator|etf-webapp'
       docker rmi <exact-image-name-or-id>

   Its base image ``jetty:9.4.58-jre8`` is shared: remove it only when
   ``docker ps -a --filter ancestor=jetty:9.4.58-jre8`` comes back empty.
   The validator image was never published centrally - ``dev-images.yml``
   built only the backend and frontend dev images - so there is nothing to
   retire in the registry.

3. **Mounts and volumes.** A validator container started outside the compose
   tree can hold a bind mount or named volume of its own (deployment check 5
   below). Read the mounts *before* removing the container:

   .. code:: text

       docker inspect --format '{{json .Mounts}}' <container-id>

   and remove only a named volume that the inspection names, that no other
   container references (``docker ps -a --filter volume=<exact-volume>``)
   and whose content the operator has confirmed disposable.

4. **Env and override footprint.** A deployment may still set
   ``MRMAP_BASE_URL_FOR_ETF``; the value was inert from #1529 on and the
   setting itself retired with #1531 - an env which still sets it is now
   simply unread. A compose override outside this tree
   that still adds the service now adds one without image and without
   build: it cannot start and is dead weight - remove the block, the way
   this PR removed it from ``docker-compose.dev.yml``.

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

Operator rollout and recovery contract (live deployments)
##########################################################

This is the contract the gate asked for, retuned for the state after #1530:
the drop is no longer something a future PR may do, it ships as
``registry/migrations/0062_retire_conformity_check_family`` on ``develop``.
Nothing in it has run against a deployment: a migration runs where an operator
upgrades and migrates, not where a pull request merges. So every step below
belongs to the operator of one deployment, and belongs there **before** that
deployment's ``migrate``:

1. **export before drop**: ``pg_dump -t`` of the twelve tables (or a full
   backup taken after the last write), stored outside the database, plus the
   restore rehearsal #1509 owns; the export is the rollback object. A report
   column of a run table is the only copy an ETF result ever had — once the
   table is gone there is nothing to re-derive it from.
2. **drain the broker first**: no by-name caller left (unknown 1), queued
   messages for the three names at zero and no ETF task in flight (unknown 2)
   — or the operator deliberately purges those queue entries inside the
   maintenance window and says so. Since #1458 a late delivery cannot start
   work, it is discarded as unregistered; purging it is still the honest
   record of what was dropped.
3. **Beat rows through the deployment's own admin**: a deployed database can
   hold ``PeriodicTask``/``CrontabSchedule`` rows naming the legacy tasks
   (unknown 3). Delete them where they exist through the deployment's admin,
   never by a silent migration, so the audit trail names who removed them.
4. **maintenance window with destructive approval**: dropping twelve tables
   is destructive data work; per epic rule it carries an explicit approval
   from the operator of each deployment, never a migration that "just runs".
5. **migration order and the worker restart**: code removal and the table
   drop are one migration following the then-current leaf; the export exists
   before it, the worker restart after it. A deployment mid-upgrade must not
   run a worker from before #1530 against a database from after it — the
   tasks would be registered while their tables are gone (their by-name
   delivery fails anyway on the abstract read, which is the safety margin
   here, not a plan).
6. **rollback**: restore the export and the previous image; no data is
   re-derived. ``0062`` reverses cleanly on a scratch database (verified in
   #1530), but a reverse is not the rollback of a production drop — the
   export is.

Q2 asked whether this is the agreed shape. While that row reads ``Pending``,
treat the steps as the recommended procedure an operator still approves
per deployment, not as an approved procedure. Where one of the unknowns above
comes back "not zero", that step is the one which decides the window; record
the answer in the deployment's own runbook, because this page can only name
the question.

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
  full retirement, #1507 is superseded — retention on tables whose drop
  already shipped on ``develop`` is churn — and its graph edge and
  parent-scope mention are removed from #1509. If ETF-only is chosen instead,
  #1507 narrows to the retained internal scope, which then still needs its
  retention policy. Either outcome is recorded in the issue bodies and the
  native dependency metadata as part of this gate.
* The #1528 decision also settles the storage question #1497 lists the family
  under: full retirement bounds that growth by removing the tables outright,
  strictly better than a retention policy on dead rows.

What still names the family today (#1533 sweep)
##################################################

**Executed (#1531).** The three settings sites and the one test comment
which still carried the family's name after #1530 are gone:
``BASE_URL_FOR_ETF`` (env ``MRMAP_BASE_URL_FOR_ETF``) and the stale
worker-budget comment of ``MrMap/settings.py``, the three unread
``CONFORMITY_DEFAULT_*_MESSAGE`` strings of ``registry/settings.py`` with
their catalog msgids, and the validator-callback comment of
``test_allowed_hosts_settings.py``.

**Executed (#1533).** The sweep of #1533 then walked every tracked file —
code, docs, hidden files, assets, environment examples, Docker, CI, tests,
manifests, lockfiles and fixtures — for the word ``ETF``, the terms
``inspire-validator``, ``etf-webapp``, port ``5557``, ``squid``,
``functx``, ``conformity`` in any casing, the task names
``async_run_conformity*``, the settings names ``CONFORMITY_*`` and
``BASE_URL_FOR_ETF``, ``QualityEtf``/``QualityInternal``,
``mapping_helper``, the ``registry_rule``/``registry_ruleset`` table
names, the six seed-fixture names as ``loaddata`` targets and the
``report_type`` columns. Every hit belongs to a permitted holder: the
historical migrations (``0001``, ``0052``, ``0053``, ``0062``, and
``0063`` only through its dependency line on ``0062``), ``CHANGELOG.md``,
this page, the three audit pages and the introduction's "What MrMap Is
Not" note, the guard ``scripts/test_validator_retirement.py`` — plus
coincidental byte matches in binary images, in ``GETFEATURE`` and
``IETF`` inside the bundled OGC schema documents, in bounding-box numbers
of WMS test fixtures and in the ``jettySize`` style attribute of drawio
diagrams. No live legacy reference remained.

Kept on purpose, and not orphans: the family's name in the historical
migrations (``0001``, ``0052``, ``0053`` — history is never edited) and in
``0062_retire_conformity_check_family`` itself, in ``CHANGELOG.md`` (a release
note describes the release which carried the change), in
``scripts/test_validator_retirement.py`` (a guard has to name what it forbids)
and in the audit trail of the three audit pages named below.

Epic status at this sweep
#########################

Read from the tracker and from ``scripts/decisions`` on 2026-11-19, not
inferred from this page:

.. list-table::
   :widths: 12 20 68
   :header-rows: 1

   * - Issue
     - State
     - What it means here
   * - #1528 (the gate)
     - closed; Q1-Q3 still ``Pending``
     - this page is its ADR; with the rows unanswered, the destructive half
       stays a per-deployment operator approval, see the contract above
   * - #1529
     - closed
     - the validator service, its image subtree and its development tooling
       are gone; the host cleanup section is what a machine may still carry
   * - #1530
     - closed
     - models, managers, enums, plugin helpers, the six fixtures and the
       twelve tables are gone through ``0062``
   * - #1531
     - closed
     - the residual settings, catalog entries and stale comment of the
       section above are gone
   * - #1532
     - closed
     - the documentation, the agent instructions and the audit dispositions
       carry the retired status recorded below
   * - #1533
     - closed by its verification PR
     - the tracked-tree sweep, the fresh installs, the upgrade rehearsal
       and the runtime confirmation ran on ``develop`` — evidence at the
       end of this page; what no checkout can answer stays the deployment
       unknowns above
   * - #1507
     - open, on hold
     - superseded or narrowed by Q3, which is still unanswered

Dispositions recorded here
###########################

These are the dispositions the retirement answers with. Each names what the
earlier audit found, and what became of it — the evidence is kept with a
retired status, never deleted, so a reader can still tell what was measured
and when.

* **#1394** (audit housekeeping task): its reported evidence — the family was
  registered, unreachable by first-party dispatch and could not answer —
  stands reproduced on ``019f17a42`` above. Its "left to its owners" question
  is still the open Q1 row of this page; what its audit trail describes is
  gone from the codebase, and :ref:`celery-task-orm-audit` keeps its
  conformity section as that trail with the retired status on it rather than
  as an open finding.
* **#1409 R16 / P-6** (:ref:`outbound-ogc-request-audit`): the ETF client's
  unpooled, timeout-less transport (R16) and the P-6 proposal it produced are
  **resolved by retirement, not by pooling** — the client left with the
  family in #1530, so P-6 is withdrawn from the audit's proposed-issue list
  and no issue should ever be filed for it. Under the ETF-only variant Q1
  offers, P-6 would come back as a live finding; that is Q1's to decide, not
  this page's.
* **The #1495 matrix** (:ref:`celery-task-sql-regression`) deliberately pinned
  no query guard for the family — a guard would have measured a dead path.
  Its matrix row and its "not covered" entry now read *retired with #1458 and
  #1530* instead of carrying a baseline that nothing regresses any more.
* **The documentation and agent instruction sweep (#1532)**: the introduction
  no longer lists an "ETF testing framework interface" as a supported feature,
  and names in "What MrMap Is Not" what validation the product does run
  instead; the conformity rows of the three audit pages carry their retired
  status; the retirement commands which named modules #1458 and #1530 removed
  are marked as non-runnable history instead of staying as copyable commands;
  the agent instruction files carry nothing to unlearn — root ``AGENTS.md``
  names the validator in exactly one place, the guard which keeps it out
  (``scripts/test_validator_retirement.py``), and ``backend/registry/AGENTS.md``
  and the ``mrmap-celery`` skill name it and the family nowhere at all.

Open decision (owner, via scripts/decisions)
#############################################

The question asked on #1528 with this recommendation:

* **Q1 — scope**: full legacy retirement (recommended) vs ETF-only with a
  named retained internal scope. Nothing in-repository answers which (if any)
  external party reads the internal rule configuration; that is owner
  knowledge. The code half of the choice has already run: on ``develop`` no
  internal rule machinery is left to retain, so an ``ETF-only`` answer now
  reads as "put it back", and this is the row which would say so.
* **Q2 — rollout contract**: is the contract above (export-before-drop,
  drained broker, per-deployment destructive approval, one migration at the
  current leaf) the agreed shape? It is the shape #1530 shipped, and it is the
  procedure the operator section hands to each deployment; what Q2 settles is
  whether a deployment may treat it as approved rather than as recommended.
* **Q3 — #1507**: supersede it on full retirement as described? #1507 is open
  and on hold until this row is answered.

An answer arrives as a ``Q1: A``-style reply on #1528 and is recorded with
``scripts/decisions --issue 1528 record --write`` plus ``register --write``,
which is what turns a row to ``Accepted``. Silence records nothing, and no
merge described anywhere on this page counts as an answer.

How to re-derive every claim
#############################

The historical run of the liveness section is archived there and no longer
runs. What follows answers on today's ``develop``, with the stack recipe of
``backend/AGENTS.md`` ("Prebuilt") for the two container commands:

.. code:: text

    # 1. the worker-wide time limits and their per-task resolution still hold
    #    (this is all that guard of #1454 has left to pin)
    docker compose run --rm --no-deps -e MRMAP_USER=mrmap -e MRMAP_PASSWORD=mrmap \
      django-tests python manage.py test \
        tests.django.test_celery_worker_config --noinput
    # 2. nothing dispatches, imports or names the family (run from the repo root)
    git grep -n "async_run_conformity" -- backend       # empty
    #    (the name survives only in docs/ and CHANGELOG.md, as audit trail)
    git grep -in conformity -- backend | grep -v migrations
    # -> empty since #1531 removed the last three CONFORMITY_DEFAULT_*
    #    definitions
    git grep -n "ETF" -- backend | grep -v migrations
    # -> nothing which is ours: only GETFEATURE and IETF inside the
    #    bundled OGC schema documents, not names to rename
    git grep -n "ETF" -- docs ':(exclude)docs/source/development'
    # -> only the retirement note of "What MrMap Is Not" in the introduction
    # 3. the twelve tables and their content types are gone on a migrated db
    docker compose run --rm --no-deps backend python manage.py shell -c \
      "from django.db import connection as c; \
       print(sorted(t for t in c.introspection.table_names() \
       if 'conformity' in t or t in ('registry_rule', 'registry_ruleset', \
       'registry_ruleset_rules')))"
    # -> []
    # 4. the validator cannot creep back into the tracked infrastructure
    python3 scripts/test_validator_retirement.py

The live counts of a *deployment* are not derivable from a checkout at all —
they are the numbered unknowns above, and only that deployment's operator can
answer them.


Verification evidence of the final gate (#1533)
###############################################

Re-executed on ``develop`` at ``0ac18ad93`` (2026-11-19) in the job's own
Compose stack on the prebuilt backend image (fingerprint ``fcbd17dfa3b5``).
Everything below was measured there, not inferred, and no deployment was
touched.

*   **Tracked-tree sweep:** clean, as the section above records; the guard
    ``python3 scripts/test_validator_retirement.py`` passes its 76 checks
    and every committed Compose variant resolves without a validator
    service, without its build context and without port 5557.
*   **Fresh installs:** three databases migrated from scratch to the
    current leaf ``0063`` (the test runner's ``test_mrmap``, the backend
    service's ``mrmap`` and the rehearsal scratch), each with
    ``manage.py check`` reporting no issues, ``makemigrations --check
    --dry-run`` reporting no drift, and the full CI pre-submit check green
    (flake8, migration drift, translation freshness);
    ``scripts/migration_graph_smoke.py`` reports one leaf per app.
*   **Upgrade rehearsal:** on a scratch database the schema was reversed
    to ``registry/0061``, the family was re-seeded — the six retired seed
    fixtures' rows reproduced as SQL (they cannot pass ``loaddata`` under
    current code, their models being gone: itself the confirmation that
    no loader of theirs survives) — plus representative rows in all four
    run tables carrying ETF report bodies (finished, still running with
    ``passed`` NULL, and failed variants) and unrelated fixture rows
    (users, CRS, keywords, a WMS with layers). Migrated forward through
    ``0062`` and ``0063``: all twelve tables, the 9 content types and the
    36 permissions were gone, while 187 survivor tables — the metadata
    profile rule tables among them —, the 110 remaining registry content
    types and every other permission row compared identical. A second
    reverse-then-forward pass verified the same again.
*   **Worker and Beat state:** the celery registry of the migrated
    application holds 44 tasks and none of the three retired names;
    ``PeriodicTask`` holds 13 rows, none naming the family. Broker queue
    contents and Beat rows of a *deployment* remain the operator unknowns
    above.
*   **Ordinary work unaffected:** the worker time-limit guard
    (``tests.django.test_celery_worker_config``, 7 tests), the
    harvesting/update/monitoring task modules (44 tests) and the whole
    Behave suite (96 features, 708 scenarios, 4701 steps, 0 failures) ran
    green; the generated OpenAPI schema (170945 lines, exit 0) carries no
    conformity or ETF resource; the frontend type check, lint and the
    full Vitest coverage run (1723 tests, the MetadataEditor screens
    among them) passed.
*   **Host footprint:** the targeted listings of the operator cleanup
    section — container by name, container by compose-service label,
    image by ``inspire-validator``/``etf-webapp`` — came back empty on
    the verification host; the runbook commands are executable as
    written.
*   **Still open after this gate (owners, not code):** Q1-Q3 of #1528
    read ``Pending``, so applying ``0062`` to a live database, the fate
    of #1507 and the export/restore rehearsal owned by #1509 remain
    per-deployment owner decisions exactly as the contract above draws
    them.
