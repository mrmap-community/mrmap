"""The declared persistent-data inventory of #1498 — the content, not the measurement.

This module is the versioned half of the V1 retention inventory. Everything a
reviewer has to agree with lives here as data: which dataset grows, why it
grows, whose it is, what its lifecycle is, which policy of #1497's provisional
proposal it is a candidate for, what must not go while it is still referenced,
what indexes and migrations a policy would need, and which decision still gates
it. The measurement half — what PostgreSQL and the filesystem actually answer —
is :mod:`system.retention_inventory`, which reads these declarations and never
the other way round.

Three rules govern a change to this file:

*   **Declare once, key on the model.** A dataset names ``app_label`` and
    ``model_name``; the physical table comes from Django's own metadata, so an
    engineer who renames a table changes the inventory by changing the model —
    the only place that knows the truth. A model name which does not resolve is
    a bug the tests of this package fail on, not a silent gap.
*   **Nothing here deletes, enables or schedules.** The policy fields describe a
    *candidate*; #1499 owns the registry and executor, #1501 the file lifecycle,
    and the domain issues their own policies. New destructive policies stay
    disabled until an operator opts in (#1497), and a dataset with an unresolved
    ``decision_gate`` must not get one at all.
*   **An unknown is written as unknown.** ``time_field=None`` says "this dataset
    has no single usable timestamp column" — the multi-table-inheritance bases
    are the standing example — and the report renders that as a named reason.
    It never becomes a zero and never a guess. A provisional age or cap is a
    proposal pending sign-off, which is why the fields carrying it are named
    ``provisional_*``.

#1497 states the rule this file exists to make enforceable: a new continuously
growing model must declare its lifecycle. The undeclared-table report of the
inventory is what turns that sentence into a check.
"""

from dataclasses import dataclass

#: bumped whenever a declaration changes, so a report says which version of the
#: inventory it was built from and a comparison between two reports can tell a
#: changed deployment from a changed declaration
DECLARATION_VERSION = 1


# ---------------------------------------------------------------------------
# vocabulary
# ---------------------------------------------------------------------------

#: how a dataset accumulates
GROWTH_ROWS_PER_EVENT = "rows_per_event"
GROWTH_ROWS_PER_RUN = "rows_per_run"
GROWTH_ROWS_PER_OBJECT = "rows_per_object"
GROWTH_VERSIONS_PER_OBJECT = "versions_per_object"
GROWTH_BYTES_PER_REQUEST = "bytes_per_request"
#: something already keeps it finite; #1498 verifies that it does instead of
#: proposing a second sweep next to the existing one (#1508)
GROWTH_BOUNDED = "bounded"
GROWTH_TYPES = (GROWTH_ROWS_PER_EVENT, GROWTH_ROWS_PER_RUN,
                GROWTH_ROWS_PER_OBJECT, GROWTH_VERSIONS_PER_OBJECT,
                GROWTH_BYTES_PER_REQUEST, GROWTH_BOUNDED)

#: what a dataset *is*, which decides how careful a policy has to be — not how
#: big it is. The distinction is #1497's: active work, provenance and audit
#: cannot be treated like cache.
CLASSIFICATION_ACTIVE_WORK = "active_work"
CLASSIFICATION_PROVENANCE = "provenance"
CLASSIFICATION_AUDIT = "audit"
CLASSIFICATION_OPERATIONAL = "operational"
CLASSIFICATION_CACHE = "cache"
CLASSIFICATION_LIVE_DOCUMENT = "live_document"
CLASSIFICATION_REFERENCE = "reference"
CLASSIFICATIONS = (CLASSIFICATION_ACTIVE_WORK, CLASSIFICATION_PROVENANCE,
                   CLASSIFICATION_AUDIT, CLASSIFICATION_OPERATIONAL,
                   CLASSIFICATION_CACHE, CLASSIFICATION_LIVE_DOCUMENT,
                   CLASSIFICATION_REFERENCE)

#: who owns the lifecycle decision. Roles of the project, not individuals: the
#: answer a policy's operator documentation has to name, and whose sign-off a
#: ``decision_gate`` waits for.
OWNER_REGISTRY = "registry maintainers"
OWNER_MONITORING = "monitoring maintainers"
OWNER_SECURITY = "security/audit maintainers"
OWNER_OPS = "deployment operators"
OWNER_PLATFORM = "platform maintainers"
OWNER_ACCOUNTS = "accounts/permissions maintainers"

#: the policy family of #1497's provisional proposal this dataset is a candidate
#: for. ``none`` is a real answer, and it is stated so nobody proposes a sweep
#: for the same table twice.
POLICY_TTL_AND_CAP = "ttl_and_max_count"
POLICY_TTL = "ttl"
POLICY_MAX_COUNT = "max_count"
POLICY_MEDIA_ORPHAN = "media_orphan_reconciliation"
POLICY_NONE = "none"
POLICY_CANDIDATES = (POLICY_TTL_AND_CAP, POLICY_TTL, POLICY_MAX_COUNT,
                     POLICY_MEDIA_ORPHAN, POLICY_NONE)

#: whether a file below a media prefix is live, shared/historical, or already
#: orphan-material — the distinction #1498 asks the media inventory to make
SCOPE_LIVE = "live"
SCOPE_SHARED = "historical_or_shared"
SCOPE_ORPHAN_RELEVANT = "orphan_relevant"
MEDIA_SCOPES = (SCOPE_LIVE, SCOPE_SHARED, SCOPE_ORPHAN_RELEVANT)


@dataclass(frozen=True)
class Dataset:
    """One persistent dataset, in the shape #1498's acceptance list asks for.

    ``time_field`` is the column both the growth measurement and a future policy
    order by: the terminal timestamp where one exists, the creation timestamp
    otherwise, ``None`` when the table has no single usable one.
    ``scope_field`` is what "per object" means for the per-scope maximum of
    #1497 — a history table groups per audited object, harvest relations per
    run, monitoring rows per setting.
    ``family_tables`` names the concrete subclasses of a multi-table-inheritance
    base as ``app_label.ModelName``: a row lives in the base and in exactly one
    subclass, so the inventory measures the family and a policy has to be
    written per concrete model. Declaring it is what keeps a base table which is
    empty by itself (the monitoring bases) from being read as "this dataset
    holds nothing".
    """

    id: str
    app_label: str
    model_name: str
    growth: str
    classification: str
    owner: str
    lifecycle: str
    policy_candidate: str
    #: what keeps a policy from taking rows this dataset still needs, stated as
    #: ``app_label.model:reason``. #1499 turns these into locks and existence
    #: checks; a reviewer checks them against the FK graph the report prints
    #: beside them.
    protected_dependencies: tuple = ()
    growth_drivers: tuple = ()
    writers: tuple = ()
    readers: tuple = ()
    #: the states which end the row's life. Stated as prose where the codebase
    #: has no phase enum at all (monitoring runs close on ``date_done``), which
    #: is a finding of the inventory and not a gap in this table.
    terminal_states: tuple = ()
    #: the existing cleanup this dataset already has: a task or command name,
    #: or ``None``. #1508 migrates these instead of duplicating them.
    existing_cleanup: str = None
    #: the setting which already bounds it, if any
    existing_setting: str = None
    time_field: str = None
    scope_field: str = None
    protected_min: int = None
    provisional_age_days: int = None
    provisional_max_per_scope: int = None
    index_needs: tuple = ()
    migration_needs: tuple = ()
    #: what a focused PostgreSQL test must show about deletion and reference
    #: behaviour when a policy for this dataset lands (#1498's fourth item)
    test_expectations: str = None
    #: the open decision which gates a policy here. Non-empty means: no
    #: destructive policy on this dataset, enabled or preview-only, until the
    #: named decision is answered (#1497: unresolved decisions stay gated).
    decision_gate: str = None
    #: semantics which fit no other field — the note a reviewer needs
    notes: str = None
    family_tables: tuple = ()

    @property
    def label(self):
        return f"{self.app_label}.{self.model_name}"

    @property
    def model_names(self):
        """Every model whose rows belong to this dataset, base first."""
        return (self.label, *self.family_tables)


@dataclass(frozen=True)
class StorageSource:
    """One media prefix the inventory walks, declared by the fields that own it.

    ``reference_fields`` is the union of FileField columns whose values may
    point into ``prefix``. It is a union on purpose: this project shares
    prefixes — the ``xml_documents`` tree holds the backups of three metadata
    record tables and the capability documents alike — and a file named by *any*
    of them is referenced. Declaring them per field is what lets the inventory
    answer "how much of this tree does which table own", which a directory-level
    sweep cannot.

    The declared prefix is the literal subtree of the ``upload_to`` function, so
    a rename of an ``upload_to`` shows up as bytes in the wrong bucket rather
    than as a silently empty one.
    """

    id: str
    app_label: str
    model_name: str
    field_name: str
    prefix: str
    kind: str
    owner: str
    lifecycle: str
    policy_candidate: str
    reference_fields: tuple = ()
    reference_scope: str = SCOPE_LIVE
    protected_dependencies: tuple = ()
    notes: str = None

    @property
    def label(self):
        return f"{self.app_label}.{self.model_name}"


# the three metadata record tables whose documents /csw serves; the same list
# registry/management/commands/check_xml_backups.py walks
_XML_RECORD_TABLES = (
    ("registry", "DatasetMetadataRecord", "xml_backup_file"),
    ("registry", "ServiceMetadataRecord", "xml_backup_file"),
    ("registry", "ApplicationMetadataRecord", "xml_backup_file"),
)

# the capability documents of the registered services and elements: the upstream
# document an update compares against. Same abstract mixin and same tree as the
# record backups (registry/models/document.py), which is why the reference set of
# the prefix must be the union over all of them.
_XML_CAPABILITY_TABLES = (
    ("registry", "WebMapService", "xml_backup_file"),
    ("registry", "WebFeatureService", "xml_backup_file"),
    ("registry", "CatalogueService", "xml_backup_file"),
    ("registry", "Layer", "xml_backup_file"),
    ("registry", "FeatureType", "xml_backup_file"),
)


# ---------------------------------------------------------------------------
# the growing datasets
# ---------------------------------------------------------------------------

_HARVEST_HISTORY_READERS = (
    "registry/querys/harvest_history.py:complete-snapshot detection, removal "
    "detection and duration statistics all read the history of runs",
)

DATASETS = (
    # -- harvesting ---------------------------------------------------------
    Dataset(
        id="harvesting_job",
        app_label="registry", model_name="HarvestingJob",
        growth=GROWTH_ROWS_PER_RUN, classification=CLASSIFICATION_OPERATIONAL,
        owner=OWNER_REGISTRY,
        lifecycle="one row per run of a periodic or manual harvest; "
                  "COMPLETED and ABORTED are terminal, ABORT is only the "
                  "request to stop",
        policy_candidate=POLICY_TTL_AND_CAP,
        protected_dependencies=(
            "registry.HarvestedMetadataRelation:the run's harvested records; "
            "removal detection reads the newest complete runs of a catalogue",
            "registry.HarvestingLog:the run's own log lines",
            "registry.HarvestingJobTaskId:broker identities of an in-flight "
            "run — a job whose task ids are gone cannot be recovered or "
            "resumed",
            "notify.BackgroundProcess:the durable report of the operation "
            "(#1208) names the job",
            "registry.PeriodicHarvestingJob:the schedule which still points "
            "at this run as its last",
        ),
        growth_drivers=("every periodic harvest of every catalogue",
                        "manual re-harvests, resumes and aborts"),
        writers=("registry/tasks/harvest.py", "registry/views/harvest.py"),
        readers=_HARVEST_HISTORY_READERS + (
            "the harvesting history screens of the frontend",),
        terminal_states=("COMPLETED", "ABORTED"),
        existing_cleanup="registry.tasks.harvest schedules the cleanup of the "
                         "run's record backlog on its terminal transition",
        existing_setting="HARVEST_TEMP_FILE_CLEANUP_RETENTION_DAYS",
        time_field="date_created", scope_field="service",
        protected_min=5, provisional_age_days=90,
        provisional_max_per_scope=30,
        index_needs=("phase + date_created: the selection is 'terminal and "
                     "older than', which no existing index answers together",
                     "service + date_created DESC: the per-scope keep-newest, "
                     "the same shape the history screen asks for"),
        migration_needs=("none to start: derive eligibility from phase and "
                         "date_created rather than adding a retention marker "
                         "column which can drift out of date"),
        test_expectations="deleting old COMPLETED jobs of a catalogue keeps "
                          "the newest N jobs, keeps every row of any job which "
                          "is not COMPLETED or ABORTED, keeps the job any "
                          "PeriodicHarvestingJob still names, and the daily "
                          "statistics of the retained window answer unchanged",
        decision_gate="the chart window of the harvesting history screens: 90 "
                      "d is provisional until the historical coverage an "
                      "operator must be able to chart is stated (#1497: "
                      "bounded coverage is documented, never silently cut)",
        notes="ABORT (4711) is a request, not a terminal phase — it becomes "
              "ABORTED. A policy which reads it as finished takes rows from a "
              "run which is still winding down.",
    ),
    Dataset(
        id="harvested_metadata_relation",
        app_label="registry", model_name="HarvestedMetadataRelation",
        growth=GROWTH_ROWS_PER_RUN, classification=CLASSIFICATION_PROVENANCE,
        owner=OWNER_REGISTRY,
        lifecycle="one row per (record, run) pair: the run-time state of one "
                  "harvested record inside one run, so it scales as records x "
                  "runs",
        policy_candidate=POLICY_TTL_AND_CAP,
        protected_dependencies=(
            "registry.HarvestingJob:the run these rows belong to",
            "registry/querys/harvest_history.py:the removal detection reads "
            "the complete set of the newest runs — a partial set reads as "
            "'every missing record was removed', which fabricates deletions",
            "the record's own provenance: #1497 states that harvested_through "
            "is independent of the run row and must survive it",
        ),
        growth_drivers=("records x runs: the dominant writer of the database "
                        "at the scale #1237 measured (187 789 rows, 6.7 GB)"),
        writers=("registry/tasks/harvest.py",),
        readers=_HARVEST_HISTORY_READERS + (
            "the daily harvesting statistics (#1316)",),
        terminal_states=("(no phase of its own: a row is finished when its "
                         "run is)"),
        time_field="history_date", scope_field="harvesting_job",
        protected_min=2, provisional_age_days=90,
        index_needs=("harvesting_job + history_date for the per-run "
                     "selection; the statistics index already covers the "
                     "grouping"),
        migration_needs=("none for a bound; a compact summary is a rollup and "
                         "belongs to #1511, which must not overwrite these ids"),
        test_expectations="deleting the rows of an old run keeps the rows of "
                          "the newest complete runs of the same catalogue, "
                          "keeps the provenance of every record which still "
                          "exists, and the removal detection answers the same "
                          "set as before the deletion",
        decision_gate="how many complete runs per catalogue the removal "
                      "detection needs as its baseline (#1497 proposes 10 per "
                      "catalogue, minimum 2 complete plus any needed by active "
                      "runs — provisional until the query is read against real "
                      "data)",
        notes="The table whose row count makes harvesting expensive, and the "
              "primary target of the V2 rollups. V1 gives it a bound, not a "
              "redesign.",
    ),
    Dataset(
        id="temporary_md_metadata_file",
        app_label="registry", model_name="TemporaryMdMetadataFile",
        growth=GROWTH_ROWS_PER_EVENT, classification=CLASSIFICATION_CACHE,
        owner=OWNER_REGISTRY,
        lifecycle="one row per downloaded record of a run plus its file; the "
                  "import deletes what it consumed and the terminal "
                  "transition schedules the rest",
        policy_candidate=POLICY_MEDIA_ORPHAN,
        protected_dependencies=(
            "registry.HarvestingJob:only a job in a terminal phase may have "
            "its backlog taken at all",
            "registry.RegistrationDocumentAcquisition:a document shared by "
            "several references must survive one reference's cleanup",
            "a file named by two rows is shared; taking it because one row "
            "went breaks the other",
        ),
        growth_drivers=("every record of every harvest, until the import "
                        "consumes it"),
        writers=("registry/tasks/harvest.py",),
        readers=("registry/tasks/harvest.py:the import",
                 "registry/management/commands/cleanup_temporary_harvest_files.py"),
        terminal_states=("(follows the job's phase)",),
        existing_cleanup="registry.tasks.harvest cleanup plus manage.py "
                         "cleanup_temporary_harvest_files (#1237)",
        existing_setting="HARVEST_TEMP_FILE_RETENTION_DAYS, "
                         "HARVEST_TEMP_FILE_CLEANUP_RETENTION_DAYS",
        # no time_field on purpose: the table holds no timestamp of its own,
        # and the sweep which owns it (#1237) selects by the phase and the
        # done_at of the owning job, never by an age of the row. Inventing one
        # here would let the inventory rank the backlog by a column which does
        # not exist and would let a future policy select rows whose job is
        # still running.
        time_field=None, scope_field="job",
        decision_gate=(
            "the age of a backlog row is only answerable through its owner: a "
            "policy on this table is the retention of the owning job's phase "
            "and done_at (and of the owning background process for a "
            "registration row), decided together with registry.HarvestingJob "
            "and notify.BackgroundProcess and not beside them"),
        provisional_age_days=0,
        index_needs=("job — already there for the sweep; a time-based "
                     "selection must not be added without it"),
        migration_needs=("none; #1508 migrates the existing path rather than "
                         "adding a second one"),
        test_expectations="a dry run deletes nothing and dispatches nothing; a "
                          "run over one terminal job's backlog leaves every row "
                          "of a running job and every file another row still "
                          "references; re-running is a no-op",
        notes="#1497: preserve behaviour and migrate rather than duplicate. "
              "Declared so the inventory names the mechanism which exists "
              "instead of proposing another beside it.",
    ),
    Dataset(
        id="registration_document_acquisition",
        app_label="registry", model_name="RegistrationDocumentAcquisition",
        growth=GROWTH_ROWS_PER_EVENT, classification=CLASSIFICATION_CACHE,
        owner=OWNER_REGISTRY,
        lifecycle="one row per distinct document fetched for a collecting run "
                  "(#1410); the claim token in the file name makes a lost "
                  "attempt an orphan instead of an overwrite",
        policy_candidate=POLICY_MEDIA_ORPHAN,
        protected_dependencies=(
            "the references which point at this acquisition: a document with "
            "a live reference is not an orphan",
            "REGISTRATION_ORPHAN_FILE_GRACE_SECONDS:bytes of a lost attempt "
            "are orphan-material only after the grace",
            "the fetch lease: a row whose lease has not expired belongs to a "
            "worker which may still finish",
        ),
        growth_drivers=("registrations and re-registrations, including the "
                        "attempts whose worker died"),
        writers=("registry/tasks/harvest.py",),
        readers=("the registration sweep of registry/tasks/harvest.py",),
        terminal_states=("the row drains when its last reference decides"),
        existing_cleanup="the registration sweep of registry.tasks.harvest",
        existing_setting="REGISTRATION_ORPHAN_FILE_GRACE_SECONDS, "
                         "REGISTRATION_REFERENCE_LEASE_SECONDS",
        time_field="request_id", scope_field="background_process",
        index_needs=("background_process + request_id for the sweep's bounded "
                     "batch"),
        test_expectations="a file named by a live reference survives every "
                          "sweep; a file below the prefix named by no row and "
                          "older than the grace is reported; a dry run deletes "
                          "nothing",
        notes="``request_id`` is the planned-at timestamp of the fetch, not a "
              "request id: the name is misleading but it is the only age the "
              "row carries, and the field's own comment says the sweep "
              "measures a never-claimed row by it.",
    ),
    Dataset(
        id="harvesting_log",
        app_label="registry", model_name="HarvestingLog",
        growth=GROWTH_ROWS_PER_EVENT, classification=CLASSIFICATION_OPERATIONAL,
        owner=OWNER_REGISTRY,
        lifecycle="one row per log line of a run, with an optional attachment "
                  "below HarvestingLog/<job pk>/",
        policy_candidate=POLICY_TTL,
        protected_dependencies=(
            "registry.HarvestingJob:a log of a run which is still running is "
            "live output, not history",
            "its attachment shares the job's directory: row and file go "
            "together or neither goes",
        ),
        growth_drivers=("every warning and error of every run; the response "
                        "content of a failing remote answer becomes an "
                        "attachment"),
        writers=("registry/tasks/harvest.py",),
        readers=("the harvesting detail screens",),
        terminal_states=("(append-only)",),
        time_field="timestamp", scope_field="harvesting_job",
        provisional_age_days=30,
        index_needs=("harvesting_job + timestamp for a per-run keep-newest; "
                     "timestamp alone for the age sweep"),
        test_expectations="logs of a running job are never selected; the "
                          "attachment of a deleted row goes with it and nothing "
                          "else below the job's directory goes with it",
        decision_gate="whether an error log is audit evidence and therefore "
                      "holds (#1497 requires the audit-privacy decision to be "
                      "stated, not assumed)",
    ),
    # -- monitoring ---------------------------------------------------------
    Dataset(
        id="monitoring_run",
        app_label="registry", model_name="MonitoringRun",
        growth=GROWTH_ROWS_PER_RUN, classification=CLASSIFICATION_OPERATIONAL,
        owner=OWNER_MONITORING,
        lifecycle="one row per execution of a monitoring setting's task, "
                  "closed by date_done",
        policy_candidate=POLICY_TTL_AND_CAP,
        protected_dependencies=(
            "registry/querys/alerts.py:reads the newest runs and the "
            "failures — taking the newest relevant result or failure away "
            "changes what the alerts answer, which is an alert regression and "
            "not a size win",
            "the latest relevant result of a service is what the API and the "
            "service cards render",
            "registry.ProbeResult:the probes of a run hang below it",
            "notify.BackgroundProcess:the operation report of the run",
        ),
        growth_drivers=("every monitoring setting x its schedule; the "
                        "per-service stagger of system/fields.py spreads the "
                        "load, not the count"),
        writers=("registry/tasks/monitoring.py",),
        readers=("registry/querys/alerts.py",
                 "the monitoring screens and the service cards"),
        terminal_states=("date_done set — there is no phase enum, so a run "
                         "without date_done is unfinished"),
        time_field="date_created", scope_field="setting (on the concrete run)",
        protected_min=10, provisional_age_days=30,
        provisional_max_per_scope=10000,
        index_needs=("setting + date_created DESC on each concrete run table "
                     "for the per-setting keep-newest; the base table carries "
                     "the timestamps but holds no queryable scope, so a "
                     "selection must name the concrete model"),
        migration_needs=("none for the bound; #1484 decides what deleting a "
                         "monitoring setting means, which a run policy must "
                         "not assume past"),
        test_expectations="deleting old runs keeps the newest relevant result "
                          "and the newest failure of every setting, keeps every "
                          "run an alert still names, and the alert state of the "
                          "retained window is unchanged",
        decision_gate="#1484 (monitoring setting deletion semantics) is a "
                      "required decision before the run policy can be written "
                      "(#1497 lists it as a dependency of #1504)",
        family_tables=("registry.WebMapServiceMonitoringRun",
                       "registry.WebFeatureServiceMonitoringRun",
                       "registry.CatalogueServiceMonitoringRun"),
    ),
    Dataset(
        id="probe_result",
        app_label="registry", model_name="ProbeResult",
        growth=GROWTH_ROWS_PER_RUN, classification=CLASSIFICATION_OPERATIONAL,
        owner=OWNER_MONITORING,
        lifecycle="one row per probe of a run; some kinds store their "
                  "response body as a file",
        policy_candidate=POLICY_TTL_AND_CAP,
        protected_dependencies=(
            "registry.MonitoringRun:the run whose execution this documents",
            "its stored artifact: #682's whole point is that an inspector "
            "looks at the run and not at what the service answers today",
            "registry.Probe:the definition (#1484's question, not this "
            "policy's)",
        ),
        growth_drivers=("probes x runs: several probes per run per setting, "
                        "each with its own row and sometimes a body"),
        writers=("registry/tasks/monitoring.py",),
        readers=("registry/querys/alerts.py", "the monitoring detail screens"),
        terminal_states=("date_done set"),
        existing_cleanup="registry.tasks.monitoring."
                         "delete_expired_probe_response_artifacts, which "
                         "bounds the artifact and not the row",
        existing_setting="MONITORING_PROBE_RESPONSE_RETENTION_DAYS",
        time_field="date_created", scope_field="run",
        protected_min=10, provisional_age_days=30,
        index_needs=("run + date_created DESC on each concrete result table "
                     "for the per-probe keep-newest"),
        test_expectations="the newest relevant result and the newest failure "
                          "per probe survive; a result whose artifact still "
                          "exists keeps it; deleting a result which an alert "
                          "names is refused",
        decision_gate="whether the stored response of a *failed* probe is "
                      "audit evidence with a hold, which changes the floor "
                      "from N rows to N failures",
        family_tables=("registry.GetCapabilitiesProbeResult",
                       "registry.GetMapProbeResult",
                       "registry.WebFeatureServiceGetCapabilitiesProbeResult",
                       "registry.WebFeatureServiceGetFeatureProbeResult",
                       "registry.CatalogueServiceGetCapabilitiesProbeResult",
                       "registry.CatalogueServiceGetRecordsProbeResult"),
        notes="Declared on the base table, which is where the timestamps are; "
              "the concrete tables hold only the specialised columns and are "
              "measured with it.",
    ),
    # -- security proxy -----------------------------------------------------
    Dataset(
        id="http_request_log",
        app_label="registry", model_name="HttpRequestLog",
        growth=GROWTH_BYTES_PER_REQUEST, classification=CLASSIFICATION_AUDIT,
        owner=OWNER_SECURITY,
        lifecycle="one row per proxied request, with the request body as a "
                  "file and the headers as json",
        policy_candidate=POLICY_TTL,
        protected_dependencies=(
            "registry.HttpResponseLog:the answer to this request hangs below "
            "it",
            "the concrete log's service FK is PROTECT: a log naming a service "
            "keeps the service from being deleted, which is a retention "
            "finding in its own right",
            "settings.AUTH_USER_MODEL is PROTECT: a log naming a user keeps "
            "the user from being deleted — a privacy question before it is a "
            "size question",
        ),
        growth_drivers=("every proxied request of a secured service; the body "
                        "of a POST is stored in full"),
        writers=("registry/proxy/wms_proxy.py", "registry/proxy/wfs_proxy.py"),
        readers=("the security and audit screens of the administration",),
        terminal_states=("(append-only)",),
        time_field="timestamp", scope_field="service (on the concrete log)",
        provisional_age_days=7,
        index_needs=("timestamp for the age sweep; service + timestamp DESC "
                     "for a per-service cap — neither exists today, so "
                     "today's only possible policy is a scan"),
        test_expectations="deleting old logs never deletes the PROTECTed user "
                          "or service; the response and the analysis of a "
                          "deleted request go with it, and their files with "
                          "them; a request inside the window is untouched",
        decision_gate="#741 security/audit requirements: bodies and headers "
                      "carry credentials and personal data, so no policy here "
                      "is enabled before the audit/privacy review says which "
                      "bodies may be kept at all and for how long",
        family_tables=("registry.WebMapServiceHttpRequestLog",
                       "registry.WebFeatureServiceHttpRequestLog"),
    ),
    Dataset(
        id="http_response_log",
        app_label="registry", model_name="HttpResponseLog",
        growth=GROWTH_BYTES_PER_REQUEST, classification=CLASSIFICATION_AUDIT,
        owner=OWNER_SECURITY,
        lifecycle="one row per proxied response, with the full response body "
                  "as a file below security_proxy/logs/responses/",
        policy_candidate=POLICY_TTL,
        protected_dependencies=(
            "registry.HttpRequestLog:the request it answered — the two "
            "policies must move together or one table accumulates orphans",
            "registry.AnalyzedResponseLog is a PROTECT one-to-one on the "
            "concrete log: the async analysis of #1459 holds the row it "
            "analysed",
        ),
        growth_drivers=("every proxied response; the body file is as large as "
                        "what the remote service sent — a GetCapabilities or a "
                        "GetFeature of a big layer"),
        writers=("registry/proxy/wms_proxy.py", "registry/proxy/wfs_proxy.py"),
        readers=("the security and audit screens", "registry/tasks/security.py"),
        terminal_states=("(append-only)",),
        time_field=None, scope_field="request",
        provisional_age_days=7,
        index_needs=("the concrete subclass tables are the ones with rows and "
                     "with the request link; each needs its own timestamp "
                     "index — the base has none, and the base has no timestamp "
                     "at all"),
        test_expectations="deleting a response takes its body file and its "
                          "analysis row and never the request of another "
                          "response; a response an AnalyzedResponseLog still "
                          "names holds",
        decision_gate="#741 as for the request log, plus whether the bodies "
                      "#1459's async analysis reads are re-creatable (they "
                      "are not) or evidence",
        notes="Declared on the abstract-style base so the finding — a growing "
              "audit table whose base has no timestamp column and which has no "
              "cleanup at all — is recorded where a reviewer will see it. Rows "
              "live in the concrete tables, which the family list measures.",
        family_tables=("registry.WebMapServiceHttpResponseLog",
                       "registry.WebFeatureServiceHttpResponseLog"),
    ),
    # -- service updates ----------------------------------------------------
    Dataset(
        id="service_update_job",
        app_label="registry", model_name="ServiceUpdateJob",
        growth=GROWTH_ROWS_PER_EVENT, classification=CLASSIFICATION_ACTIVE_WORK,
        owner=OWNER_REGISTRY,
        lifecycle="one row per update of a registered service; REVIEW_REQUIRED "
                  "is live work for a person and not a terminal state",
        policy_candidate=POLICY_TTL_AND_CAP,
        protected_dependencies=(
            "the candidate objects a job created: an unreviewed candidate is "
            "live work even when the status looks finished (#1497)",
            "registry.ServiceElementMapping and its children: the mappings a "
            "review decides about",
            "notify.BackgroundProcess:the durable report of the operation",
            "a job in RESUME or WAITING_FOR_PROCESSING is work a worker will "
            "still pick up",
        ),
        growth_drivers=("every update setting x its schedule, plus every "
                        "manual update of a service"),
        writers=("registry/tasks/service.py", "registry/mappers/persistence/"),
        readers=("the update and review screens", "the alerting of #1308"),
        terminal_states=("NO_UPDATE_NEEDED", "UPDATED", "ERROR"),
        time_field="date_created", scope_field="service (on the concrete job)",
        protected_min=5, provisional_age_days=180,
        provisional_max_per_scope=100,
        index_needs=("status + date_created for the terminal-and-older "
                     "selection; service + date_created DESC for the "
                     "per-service cap"),
        test_expectations="a job in REVIEW_REQUIRED is never selected; the "
                          "newest N of every service survive; deleting a job "
                          "leaves the mappings a review still needs and does "
                          "not touch the published service or its history",
        decision_gate="which statuses are truly terminal, given "
                      "REVIEW_REQUIRED and the retry paths (#1497: preserve "
                      "active, retry and review states)",
        family_tables=("registry.WebMapServiceUpdateJob",
                       "registry.WebFeatureServiceUpdateJob",
                       "registry.CatalogueServiceUpdateJob"),
    ),
    Dataset(
        id="service_element_mapping",
        app_label="registry", model_name="ServiceElementMapping",
        growth=GROWTH_ROWS_PER_EVENT, classification=CLASSIFICATION_ACTIVE_WORK,
        owner=OWNER_REGISTRY,
        lifecycle="one row per element a candidate of an update job maps",
        policy_candidate=POLICY_MAX_COUNT,
        protected_dependencies=(
            "registry.ServiceUpdateJob:the job whose review decides about this "
            "mapping",
            "the candidate service element it maps to",
        ),
        growth_drivers=("elements x update jobs, on a service with many layers"),
        writers=("registry/mappers/persistence/",),
        readers=("the review screens",),
        terminal_states=("(decided by the job's review)",),
        time_field=None, scope_field=None,
        test_expectations="the mappings of a deleted job go with it through "
                          "their FK; the mappings of a retained job are never "
                          "touched by a policy written on the job table alone",
        decision_gate="the same terminal-state question as service_update_job",
        family_tables=("registry.LayerMapping", "registry.FeatureTypeMapping"),
    ),
    # -- audit history ------------------------------------------------------
    Dataset(
        id="history_role_definition",
        app_label="accounts", model_name="HistoricalRoleDefinition",
        growth=GROWTH_VERSIONS_PER_OBJECT, classification=CLASSIFICATION_AUDIT,
        owner=OWNER_ACCOUNTS,
        lifecycle="one audit row per change of a role definition, including "
                  "its permission set (#741)",
        policy_candidate=POLICY_TTL_AND_CAP,
        protected_dependencies=(
            "the live RoleDefinition row: the current state is never a history "
            "row",
            "the anchor row of a live object — #1502 keeps the creation audit",
            "the permission-set history table: a change of the set is not a "
            "column of the row, so a row policy which ignores it silently "
            "leaves a permission change out",
        ),
        growth_drivers=("role edits and the sync of the role definitions",),
        writers=("simple_history through the model's change_log",),
        readers=("the role history screens", "the audit answers of #741"),
        terminal_states=("(append-only)",),
        time_field="history_date", scope_field="history_id of the audited row",
        protected_min=2, provisional_age_days=365,
        provisional_max_per_scope=100,
        index_needs=("audited pk + history_date for the per-object "
                     "keep-newest; today only history_date is indexed, so the "
                     "cap selection is a scan"),
        test_expectations="deleting old rows keeps the anchor row of every "
                          "live definition and the newest N per object, and "
                          "keeps every row needed to answer who granted a "
                          "permission still in effect",
        decision_gate="the audit retention requirement of #741: a hold, not a "
                      "number, until it is named",
    ),
    Dataset(
        id="history_role",
        app_label="accounts", model_name="HistoricalRole",
        growth=GROWTH_VERSIONS_PER_OBJECT, classification=CLASSIFICATION_AUDIT,
        owner=OWNER_ACCOUNTS,
        lifecycle="one audit row per change of a role, including its retirement",
        policy_candidate=POLICY_TTL_AND_CAP,
        protected_dependencies=(
            "the live Role row",
            "the anchor row (#1502)",
            "the group a role links to: an audit which cannot name the role "
            "behind a guardian grant cannot answer what the grant was for",
        ),
        growth_drivers=("role edits, organisation changes and retirements",),
        writers=("simple_history through the model's change_log",),
        readers=("the permission history screens",),
        terminal_states=("(append-only)",),
        time_field="history_date", scope_field="history_id of the audited row",
        protected_min=2, provisional_age_days=365,
        provisional_max_per_scope=100,
        index_needs=("audited pk + history_date for the per-object cap"),
        test_expectations="the audit of a still-effective group grant stays "
                          "answerable; the newest N rows per role survive",
        decision_gate="#741 audit retention",
    ),
    Dataset(
        id="history_role_membership",
        app_label="accounts", model_name="HistoricalRoleMembership",
        growth=GROWTH_VERSIONS_PER_OBJECT, classification=CLASSIFICATION_AUDIT,
        owner=OWNER_ACCOUNTS,
        lifecycle="one audit row per grant, change or revocation of a "
                  "membership; an expiry writes one too, with its reason",
        policy_candidate=POLICY_TTL_AND_CAP,
        protected_dependencies=(
            "the live RoleMembership of a grant still in effect",
            "the anchor row of a live membership (#1502)",
            "the historical creator of a still-live object: a history row is "
            "often the only place a creator is recorded (#1502)",
            "history_change_reason: expiry is told apart from a revocation by "
            "a person only through this column",
        ),
        growth_drivers=("every membership change, including bulk grants and "
                        "the expiry task"),
        writers=("simple_history through the model's change_log",),
        readers=("the permission history screens", "the audit of #741"),
        terminal_states=("(append-only)",),
        time_field="history_date", scope_field="history_id of the audited row",
        protected_min=2, provisional_age_days=365,
        provisional_max_per_scope=100,
        index_needs=("audited pk + history_date for the per-object cap"),
        test_expectations="deleting old rows never removes the row which "
                          "records how a still-effective grant happened; bulk "
                          "writes keep history "
                          "(bulk_update_with_history)",
        decision_gate="#741 audit retention, plus the privacy question of how "
                      "long a revoked membership stays queryable",
    ),
    Dataset(
        id="history_service_records",
        app_label="registry", model_name="HistoricalWebMapService",
        growth=GROWTH_VERSIONS_PER_OBJECT, classification=CLASSIFICATION_AUDIT,
        owner=OWNER_REGISTRY,
        lifecycle="one audit row per change of a service, layer, feature "
                  "type, map context or metadata record",
        policy_candidate=POLICY_TTL_AND_CAP,
        protected_dependencies=(
            "the live row of the audited object",
            "the anchor row (#1502)",
            "registry/querys/historical.py:the diff view answers *between* "
            "two rows, so a hole in the middle changes what the diff says "
            "rather than only shortening it",
            "the generated history_day/week/month/year columns are what the "
            "per-day statistics group by: a deleted range must read as no "
            "coverage, never as zero changes",
        ),
        growth_drivers=("every save of every audited object — the harvest and "
                        "update writes included, saves which changed nothing "
                        "included (delta_size tells them apart)"),
        writers=("simple_history through the models' change_log",
                 "simple_history.utils.bulk_create_with_history of "
                 "registry/mappers/persistence/handler.py"),
        readers=("registry/querys/historical.py",
                 "the per-day statistics of the history screen"),
        terminal_states=("(append-only)",),
        time_field="history_date", scope_field="history_id of the audited row",
        protected_min=2, provisional_age_days=365,
        provisional_max_per_scope=100,
        index_needs=("audited pk + history_date for the per-object "
                     "keep-newest; the statistics keep needing the generated "
                     "day column, which is indexed"),
        migration_needs=("a per-object retention marker would defeat the "
                         "purpose of an audit trail; derive from history_date"),
        test_expectations="the newest N rows and the anchor row of every live "
                          "object survive; a diff inside the retained window "
                          "answers as before; a window whose rows went "
                          "reports no coverage rather than zero changes",
        decision_gate="#1480/#1482 history correctness lands first (#1497 "
                      "lists it as coordination), and #741 sets the audit "
                      "retention",
        notes="One declaration for a family of history tables: they are one "
              "policy question with one set of holds, and the report lists "
              "each table's size separately. They are named in family_tables "
              "so no operator reads the size of one of them as the size of the "
              "audit trail.",
        family_tables=("registry.HistoricalWebFeatureService",
                       "registry.HistoricalCatalogueService",
                       "registry.HistoricalLayer",
                       "registry.HistoricalFeatureType",
                       "registry.HistoricalMapContext",
                       "registry.HistoricalMapContextLayer",
                       "registry.HistoricalDatasetMetadataRecord",
                       "registry.HistoricalServiceMetadataRecord",
                       "registry.HistoricalApplicationMetadataRecord",
                       "registry.HistoricalHarvestingJob"),
    ),
    # -- background operations ---------------------------------------------
    Dataset(
        id="background_process",
        app_label="notify", model_name="BackgroundProcess",
        growth=GROWTH_ROWS_PER_EVENT, classification=CLASSIFICATION_OPERATIONAL,
        owner=OWNER_PLATFORM,
        lifecycle="one row per background operation — the job history of "
                  "#1208, bounded by its own sweep",
        policy_candidate=POLICY_NONE,
        protected_dependencies=(
            "everything which reports into it: harvesting jobs, update jobs, "
            "monitoring runs and the registration work rows point at it",
            "notify.BackgroundProcessLog:its own log lines, by CASCADE",
        ),
        growth_drivers=("every background operation of the deployment",),
        writers=("notify/tasks.py",),
        readers=("the job history screens", "the operational watchdog of #1320"),
        terminal_states=("COMPLETED", "FAILED", "ABORTED"),
        existing_cleanup="notify.tasks.delete_expired_background_processes",
        existing_setting="BACKGROUND_PROCESS_RETENTION_DAYS",
        time_field="date_created", scope_field=None,
        index_needs=("status + date_created for the existing sweep's "
                     "terminal-and-older selection"),
        test_expectations="an unfinished process is never purged whatever its "
                          "age, and the existing setting keeps its current "
                          "default and meaning",
        notes="#1497: existing timed cleanup — preserve behaviour and migrate "
              "rather than duplicate (#1508). Declared with no policy so "
              "nobody proposes a second sweep for it.",
    ),
    Dataset(
        id="background_process_log",
        app_label="notify", model_name="BackgroundProcessLog",
        growth=GROWTH_ROWS_PER_EVENT, classification=CLASSIFICATION_OPERATIONAL,
        owner=OWNER_PLATFORM,
        lifecycle="one row per log line of a background process, with an "
                  "optional attachment below BackgroundProcessLog/<id>/",
        policy_candidate=POLICY_NONE,
        protected_dependencies=(
            "notify.BackgroundProcess is CASCADE: the process's own sweep "
            "takes the logs, and a second policy would race it",
            "its attachment file and the row go together",
        ),
        growth_drivers=("log lines per operation x the verbosity of the "
                        "operation"),
        writers=("notify/tasks.py",),
        readers=("the process detail screens",),
        terminal_states=("(append-only)",),
        existing_cleanup="with its process, through the existing sweep",
        existing_setting="BACKGROUND_PROCESS_RETENTION_DAYS",
        time_field="date", scope_field="background_process",
        test_expectations="the cascade of a purged process takes its rows and "
                          "its files, and nothing is left below the directory "
                          "of a process whose row is gone",
    ),
    Dataset(
        id="operational_incident",
        app_label="notify", model_name="OperationalIncident",
        growth=GROWTH_ROWS_PER_EVENT, classification=CLASSIFICATION_OPERATIONAL,
        owner=OWNER_OPS,
        lifecycle="one row per deduplicated problem (#1319); RESOLVED is "
                  "terminal and bounded by its own sweep",
        policy_candidate=POLICY_NONE,
        protected_dependencies=(
            "an ACTIVE incident is current state, not history — a partial "
            "unique index enforces one active row per dedup key",
            "the resource it names: a service, a harvesting job, an update "
            "job or a monitoring run",
        ),
        growth_drivers=("every distinct problem and its recurrences",),
        writers=("notify/tasks.py", "the publishers of #1320"),
        readers=("the operational incident screens", "the notification centre"),
        terminal_states=("RESOLVED",),
        existing_cleanup="notify.tasks.delete_expired_operational_incidents",
        existing_setting="OPERATIONAL_INCIDENT_RETENTION_DAYS",
        time_field="last_occurred_at", scope_field="dedup_key",
        test_expectations="an ACTIVE incident is never purged whatever its "
                          "age; a resolved one goes only after the retention",
    ),
    Dataset(
        id="celery_task_attempt",
        app_label="system", model_name="CeleryTaskAttempt",
        growth=GROWTH_ROWS_PER_EVENT, classification=CLASSIFICATION_OPERATIONAL,
        owner=OWNER_PLATFORM,
        lifecycle="one row per attempt of a Celery task (#1330), bounded by a "
                  "retention window and a row cap",
        policy_candidate=POLICY_NONE,
        protected_dependencies=(
            "system.capacity_snapshot:the snapshots read the measured window; "
            "taking rows inside the horizon makes rho unanswerable rather "
            "than smaller",
            "an attempt with an empty outcome is unfinished observation — the "
            "abandon grace closes it before it may be taken",
        ),
        growth_drivers=("every task attempt of every queue"),
        writers=("system.capacity_telemetry",),
        readers=("system.capacity_measures.py", "system.capacity_snapshot.py"),
        terminal_states=("SUCCESS", "FAILURE", "RETRY", "REVOKED"),
        existing_cleanup="system.tasks bounding sweep (retention and row cap)",
        existing_setting="CAPACITY_TELEMETRY_RETENTION_DAYS, "
                         "CAPACITY_TELEMETRY_MAX_ATTEMPTS",
        time_field="started_at", scope_field="queue",
        test_expectations="a sample inside the snapshot horizon is never "
                          "taken; an open attempt is closed by the grace "
                          "before it can be purged",
    ),
    Dataset(
        id="service_alert",
        app_label="registry", model_name="ServiceAlert",
        growth=GROWTH_BOUNDED, classification=CLASSIFICATION_OPERATIONAL,
        owner=OWNER_PLATFORM,
        lifecycle="one row per open problem of a service; the identity of the "
                  "row is the identity of the problem, so a fixed problem "
                  "leaves no row",
        policy_candidate=POLICY_NONE,
        protected_dependencies=(
            "registry/querys/alerts.py:the row *is* the alert state — a "
            "policy here silences alerts",
        ),
        growth_drivers=("open problems; the refresh replaces the rows of a "
                        "service rather than adding to them"),
        writers=("registry/querys/alerts.py",),
        readers=("the alert endpoints and the frontend's attention",),
        terminal_states=("(deleted when the problem is fixed)",),
        time_field="occurred_at", scope_field="service",
        test_expectations="no policy: the refresh must answer the same set "
                          "before and after a retention pass over the "
                          "neighbouring tables",
        notes="Declared as bounded so the inventory proves the bound instead "
              "of assuming it: a row count which grows while the open-problem "
              "count does not is a refresh bug, not a retention gap.",
    ),
    # -- third-party persistence of this deployment -------------------------
    Dataset(
        id="beat_periodic_task",
        app_label="django_celery_beat", model_name="PeriodicTask",
        growth=GROWTH_ROWS_PER_OBJECT, classification=CLASSIFICATION_REFERENCE,
        owner=OWNER_OPS,
        lifecycle="one row per schedule: every housekeeping sweep of the "
                  "deployment and every monitoring, update and harvest "
                  "setting is a row here",
        policy_candidate=POLICY_NONE,
        protected_dependencies=(
            "registry.PeriodicHarvestingJob and the monitoring and update "
            "settings subclass these rows — deleting one deletes a setting",
            "the housekeeping rows of notify/, registry/ and system/apps.py "
            "are looked up by their name, so a deleted row silently stops a "
            "sweep",
        ),
        growth_drivers=("registered services x settings; it tracks the "
                        "corpus, not the clock"),
        writers=("django_celery_beat's DatabaseScheduler",
                 "every apps.py which registers a housekeeping sweep"),
        readers=("the beat scheduler", "the schedule screens"),
        terminal_states=("(reference data)",),
        test_expectations="no policy: the inventory shows the count tracks "
                          "registered services plus the known housekeeping "
                          "rows, and that a repeated migrate does not add "
                          "another of each",
    ),
    Dataset(
        id="beat_crontab_schedule",
        app_label="django_celery_beat", model_name="CrontabSchedule",
        growth=GROWTH_ROWS_PER_OBJECT, classification=CLASSIFICATION_REFERENCE,
        owner=OWNER_OPS,
        lifecycle="one row per distinct crontab shape; #1273 is what happens "
                  "when a get_or_create asks for less than the whole shape",
        policy_candidate=POLICY_NONE,
        protected_dependencies=("every PeriodicTask which uses the shape",),
        growth_drivers=("distinct schedule shapes; the per-service stagger of "
                        "system/fields.py legitimately holds many, which is "
                        "the shape of this table and not growth"),
        writers=("system/fields.py", "every apps.py"),
        readers=("the beat scheduler",),
        terminal_states=("(reference data)",),
        test_expectations="no policy; the inventory watches the count for the "
                          "unbounded growth a per-object crontab would cause",
    ),
    Dataset(
        id="knox_token",
        app_label="knox", model_name="AuthToken",
        growth=GROWTH_ROWS_PER_EVENT, classification=CLASSIFICATION_REFERENCE,
        owner=OWNER_ACCOUNTS,
        lifecycle="one row per issued API token; expiry is a field and no "
                  "sweep has ever read it",
        policy_candidate=POLICY_TTL,
        protected_dependencies=(
            "the user the token authenticates",
            "a token whose expiry has not passed is a live credential, however "
            "long it has sat unused",
        ),
        growth_drivers=("every login which issues a token; TOKEN_TTL bounds "
                        "the age of a usable token, nothing bounds the number "
                        "of rows"),
        writers=("knox",),
        readers=("the token authentication path",),
        terminal_states=("expire_date in the past",),
        time_field="created", scope_field="user_id",
        index_needs=("expire_date — without it the only possible cleanup is a "
                     "scan of every token ever issued"),
        test_expectations="an unexpired token of an active user is never "
                          "taken; an expired token goes, and the user it "
                          "belonged to is not taken with it",
        decision_gate="whether deleting an expired token destroys the audit "
                      "answer of who authenticated when — it is a credential "
                      "record and a security log at once",
        notes="Third-party model of this deployment; declared because it is "
              "growing and because nothing has ever bounded it.",
    ),
    Dataset(
        id="django_session",
        app_label="sessions", model_name="Session",
        growth=GROWTH_ROWS_PER_EVENT, classification=CLASSIFICATION_CACHE,
        owner=OWNER_OPS,
        lifecycle="one row per browser session; Django's own ``flush`` "
                  "clears expired rows and is the operator's existing "
                  "mechanism",
        policy_candidate=POLICY_NONE,
        protected_dependencies=("the login state of a live session",),
        growth_drivers=("every session start",),
        writers=("django.contrib.sessions",),
        readers=("the session authentication path",),
        terminal_states=("expire_date in the past",),
        time_field="expire_date", scope_field=None,
        index_needs=("expire_date (already there)",),
        test_expectations="``flush`` keeps its behaviour and no new task "
                          "duplicates it",
        notes="Third-party persistence of this instance belongs in the "
              "inventory whether or not first-party code wrote a row — that "
              "is exactly what #1498's 'all installed third-party "
              "persistence' asks for.",
    ),
    Dataset(
        id="django_admin_log",
        app_label="admin", model_name="LogEntry",
        growth=GROWTH_ROWS_PER_EVENT, classification=CLASSIFICATION_AUDIT,
        owner=OWNER_OPS,
        lifecycle="one row per change made through the Django admin",
        policy_candidate=POLICY_TTL,
        protected_dependencies=(
            "its content type and object reference: a deleted object leaves an "
            "unresolvable reference, which is the audit answer",
        ),
        growth_drivers=("admin edits; small where the admin is a curiosity, "
                        "large where it is the operator's tool"),
        writers=("django.contrib.admin",),
        readers=("the admin's own log page",),
        terminal_states=("(append-only)",),
        time_field="action_time", scope_field=None,
        provisional_age_days=365,
        test_expectations="a log of an object which still exists is kept at "
                          "least as long as the object",
        decision_gate="#741: whether the admin log is audit evidence which "
                      "must outlive the object, or operational noise",
    ),
    Dataset(
        id="guardian_object_permissions",
        app_label="guardian", model_name="UserObjectPermission",
        growth=GROWTH_ROWS_PER_OBJECT, classification=CLASSIFICATION_REFERENCE,
        owner=OWNER_ACCOUNTS,
        lifecycle="one row per (permission, object) grant; scales with the "
                  "shared corpus, not with time",
        policy_candidate=POLICY_NONE,
        protected_dependencies=(
            "every shared object: deleting a row revokes access, which is a "
            "permissions incident and not a retention win",
            "the permission and content type rows",
        ),
        growth_drivers=("objects x permissions x users and groups",),
        writers=("accounts/ and the sharing endpoints",),
        readers=("every permission-filtered queryset of the API",),
        terminal_states=("(reference data)",),
        test_expectations="no policy; the inventory's job is to show the count "
                          "tracks the shared corpus and to catch an orphan row "
                          "whose object is gone — that is #1501's "
                          "reconciliation, not a sweep",
        family_tables=("guardian.GroupObjectPermission",),
        notes="One of the largest tables at scale, and the one where a "
              "retention bug would be a security bug. Its orphan rows are a "
              "real finding of this inventory.",
    ),
    Dataset(
        id="contenttypes",
        app_label="contenttypes", model_name="ContentType",
        growth=GROWTH_BOUNDED, classification=CLASSIFICATION_REFERENCE,
        owner=OWNER_PLATFORM,
        lifecycle="one row per model class; bounded by the code, not by time",
        policy_candidate=POLICY_NONE,
        protected_dependencies=("guardian, the admin and every generic "
                                "relation",),
        growth_drivers=("model classes",),
        writers=("the contenttypes post_migrate",),
        readers=("guardian", "django.contrib.admin"),
        terminal_states=("(reference data)",),
        test_expectations="no policy; stale rows of removed models are an "
                          "operator finding",
    ),
)


# ---------------------------------------------------------------------------
# the media prefixes
# ---------------------------------------------------------------------------

STORAGE_SOURCES = (
    StorageSource(
        id="xml_backup_documents",
        app_label="registry", model_name="DatasetMetadataRecord",
        field_name="xml_backup_file", prefix="xml_documents",
        kind="xml", owner=OWNER_REGISTRY,
        lifecycle="written with the record and read by /csw and the record "
                  "detail; only the record's own deletion takes it",
        policy_candidate=POLICY_NONE,
        reference_fields=_XML_RECORD_TABLES + _XML_CAPABILITY_TABLES,
        reference_scope=SCOPE_LIVE,
        protected_dependencies=(
            "#1497: XML backups are live documents, not disposable cache",
            "a missing file makes every /csw page which contains the record "
            "fail with DocumentUnavailable (#1150), so an orphan here is an "
            "availability incident",
            "the three record tables and the capability documents share this "
            "one prefix: the reference set is their union",
        ),
        notes="The largest and most dangerous prefix in the inventory: bytes "
              "here are neither cache nor history. It is also where #1150 "
              "measured a large share of the demo corpus pointing at a file "
              "which is not there, so the split between unreferenced bytes and "
              "missing references is the number an operator graphs.",
    ),
    StorageSource(
        id="harvest_temporary_records",
        app_label="registry", model_name="TemporaryMdMetadataFile",
        field_name="md_metadata_file", prefix="temporary_md_metadata_file",
        kind="xml", owner=OWNER_REGISTRY,
        lifecycle="the downloaded record of a run until the import consumes "
                  "it; the terminal transition schedules the rest",
        policy_candidate=POLICY_MEDIA_ORPHAN,
        reference_fields=(("registry", "TemporaryMdMetadataFile",
                           "md_metadata_file"),),
        reference_scope=SCOPE_ORPHAN_RELEVANT,
        protected_dependencies=(
            "the terminal phase of the job: a running job's backlog is live",
            "a file referenced by more than one row is shared",
            "the registration subtree below this prefix is a source of its "
            "own and is not counted twice",
        ),
    ),
    StorageSource(
        id="registration_documents",
        app_label="registry", model_name="RegistrationDocumentAcquisition",
        field_name="md_metadata_file",
        prefix="temporary_md_metadata_file/registration",
        kind="xml", owner=OWNER_REGISTRY,
        lifecycle="fetched once per distinct document of a collecting run; "
                  "the claim token in the name makes a lost attempt an orphan "
                  "instead of an overwrite (#1410)",
        policy_candidate=POLICY_MEDIA_ORPHAN,
        reference_fields=(("registry", "RegistrationDocumentAcquisition",
                           "md_metadata_file"),
                          ("registry", "TemporaryMdMetadataFile",
                           "md_metadata_file")),
        reference_scope=SCOPE_ORPHAN_RELEVANT,
        protected_dependencies=(
            "the references of #1410 which point at the acquisition",
            "REGISTRATION_ORPHAN_FILE_GRACE_SECONDS",
        ),
        notes="#1263 put the registration work rows below the harvesting "
              "prefix deliberately; the nested declaration is what keeps the "
              "two lifecycles from being counted as one.",
    ),
    StorageSource(
        id="harvesting_log_attachments",
        app_label="registry", model_name="HarvestingLog",
        field_name="extented_description", prefix="HarvestingLog",
        kind="log_attachment", owner=OWNER_REGISTRY,
        lifecycle="the response content of a failing remote answer, below the "
                  "job's own directory (#1045 keeps the name off the display "
                  "string)",
        policy_candidate=POLICY_TTL,
        reference_fields=(("registry", "HarvestingLog",
                           "extented_description"),),
        reference_scope=SCOPE_LIVE,
        protected_dependencies=("the HarvestingLog row whose id names the "
                                "directory",),
    ),
    StorageSource(
        id="background_process_attachments",
        app_label="notify", model_name="BackgroundProcessLog",
        field_name="extented_description", prefix="BackgroundProcessLog",
        kind="log_attachment", owner=OWNER_PLATFORM,
        lifecycle="the report attachment of one log line of a background "
                  "process",
        policy_candidate=POLICY_NONE,
        reference_fields=(("notify", "BackgroundProcessLog",
                           "extented_description"),),
        reference_scope=SCOPE_LIVE,
        protected_dependencies=(
            "its BackgroundProcessLog row, which goes with its process through "
            "the existing sweep (#1508)",
        ),
    ),
    StorageSource(
        id="probe_response_artifacts",
        app_label="registry", model_name="ProbeResult",
        field_name="response_body", prefix="probe_responses",
        kind="probe_body", owner=OWNER_MONITORING,
        lifecycle="the stored body of one probe result (#682); the file name "
                  "is fixed and nothing from the remote response reaches it",
        policy_candidate=POLICY_MEDIA_ORPHAN,
        reference_fields=(("registry", "ProbeResult", "response_body"),),
        reference_scope=SCOPE_LIVE,
        protected_dependencies=(
            "its ProbeResult row is the only reference",
            "MONITORING_PROBE_RESPONSE_RETENTION_DAYS bounds the age and not "
            "the count, so a busy setting keeps its whole window",
        ),
    ),
    StorageSource(
        id="proxy_request_bodies",
        app_label="registry", model_name="HttpRequestLog",
        field_name="body", prefix="security_proxy/logs/requests",
        kind="request_body", owner=OWNER_SECURITY,
        lifecycle="the body of one proxied request; no sweep has ever taken "
                  "it",
        policy_candidate=POLICY_TTL,
        reference_fields=(("registry", "HttpRequestLog", "body"),),
        reference_scope=SCOPE_LIVE,
        protected_dependencies=(
            "its HttpRequestLog row",
            "an open security incident may name this file as its evidence",
        ),
        notes="Bytes-per-request growth with no existing cleanup at all: the "
              "most likely first finding of a real deployment's media tree, "
              "and the reason this source is declared even though its policy "
              "is gated.",
    ),
    StorageSource(
        id="proxy_response_bodies",
        app_label="registry", model_name="HttpResponseLog",
        field_name="content", prefix="security_proxy/logs/responses",
        kind="response_body", owner=OWNER_SECURITY,
        lifecycle="the full body of one proxied response; no sweep has ever "
                  "taken it",
        policy_candidate=POLICY_TTL,
        reference_fields=(("registry", "HttpResponseLog", "content"),),
        reference_scope=SCOPE_LIVE,
        protected_dependencies=(
            "its HttpResponseLog row",
            "the AnalyzedResponseLog of #1459's async analysis, which PROTECTs "
            "the row",
        ),
        notes="Grows with the size of whatever the remote services answer — "
              "the least predictable growth in the inventory, because an "
              "operator does not control it.",
    ),
    StorageSource(
        id="mapcontext_preview_images",
        app_label="registry", model_name="MapContextLayer",
        field_name="preview_image", prefix="preview_images",
        kind="image", owner=OWNER_REGISTRY,
        lifecycle="an uploaded or generated preview of one map context layer",
        policy_candidate=POLICY_NONE,
        reference_fields=(("registry", "MapContextLayer", "preview_image"),),
        reference_scope=SCOPE_LIVE,
        protected_dependencies=("its MapContextLayer row",),
    ),
    StorageSource(
        id="external_authentication_keys",
        app_label="registry", model_name="ServiceAuthentication",
        field_name="key_file", prefix="ext_auth_keys",
        kind="credential", owner=OWNER_SECURITY,
        lifecycle="the key file of one external authentication setting",
        policy_candidate=POLICY_NONE,
        reference_fields=(("registry", "ServiceAuthentication", "key_file"),),
        reference_scope=SCOPE_LIVE,
        protected_dependencies=("its ServiceAuthentication row: the file *is* "
                                "the credential",),
        notes="Counted by bytes only. The inventory never reads the body of a "
              "file, so a credential-bearing path cannot be disclosed by it; "
              "a path which resolves outside the storage root is reported as a "
              "finding instead of opened.",
    ),
)


# ---------------------------------------------------------------------------
# the settings which bound storage
# ---------------------------------------------------------------------------

#: every setting name which bounds how much persistent data the deployment
#: holds — one list, so the inventory report, the operator documentation and
#: #1499's registry cannot disagree about which knobs exist. A name the running
#: instance does not have is reported as ``declared: false`` rather than being
#: filled in from a default the code no longer sets.
RETENTION_SETTING_NAMES = (
    # harvesting backlog (#1237, #1295)
    "HARVEST_TEMP_FILE_RETENTION_DAYS",
    "HARVEST_TEMP_FILE_CLEANUP_RETENTION_DAYS",
    "HARVEST_TEMP_FILE_CLEANUP_BATCH_SIZE",
    "HARVEST_TEMP_FILE_CLEANUP_ROWS_PER_RUN",
    # registration acquisitions (#1410)
    "REGISTRATION_ORPHAN_FILE_GRACE_SECONDS",
    "REGISTRATION_REFERENCE_LEASE_SECONDS",
    # monitoring artifacts (#682)
    "MONITORING_PROBE_RESPONSE_RETENTION_DAYS",
    "MONITORING_PROBE_RESPONSE_MAX_SIZE",
    # background operations and incidents (#1208, #1319)
    "BACKGROUND_PROCESS_RETENTION_DAYS",
    "OPERATIONAL_INCIDENT_RETENTION_DAYS",
    # the deployment's own observability
    "SLOW_REQUEST_DUMP_RETENTION_DAYS",
    "SLOW_REQUEST_DUMP_MAX_FILES",
    "CAPACITY_TELEMETRY_RETENTION_DAYS",
    "CAPACITY_TELEMETRY_MAX_ATTEMPTS",
    "CAPACITY_TELEMETRY_ABANDON_GRACE_HOURS",
    # caches and broker
    "CELERY_RESULT_EXPIRES",
    "RESPONSE_CACHE_TIME",
)


# ---------------------------------------------------------------------------
# accessors — the API #1499 builds its registry and executor on (#1397:
# selection logic belongs to the owner of the data, and this is the only place
# the retention semantics of a dataset are stated)
# ---------------------------------------------------------------------------

_BY_ID = {dataset.id: dataset for dataset in DATASETS}


def dataset_for(dataset_id):
    """The declaration of one dataset, or ``None``.

    ``None`` and not a default: a caller which asks for an undeclared dataset
    has a bug, and the difference between "not declared" and "declared as
    nothing" is precisely the difference this inventory exists to keep visible.
    """
    return _BY_ID.get(dataset_id)


def dataset_for_model(app_label, model_name):
    """The declarations which cover one model, base or concrete subclass."""
    label = f"{app_label}.{model_name}"
    return tuple(dataset for dataset in DATASETS if label in dataset.model_names)


def declared_datasets():
    return DATASETS


def growing_datasets():
    """Every dataset whose row count or byte count increases with time."""
    return tuple(dataset for dataset in DATASETS
                 if dataset.growth != GROWTH_BOUNDED)


def datasets_for_policy():
    """The datasets a policy of #1499 may be proposed for.

    Excludes the ones whose candidate is ``none`` — they are declared precisely
    so that nobody proposes a sweep for them twice.
    """
    return tuple(dataset for dataset in DATASETS
                 if dataset.policy_candidate != POLICY_NONE)


def gated_datasets():
    """The datasets whose policy stays behind an unresolved decision.

    #1497's rule that unresolved decisions are explicitly gated, expressed as
    data: a registry which enabled a policy on a gated dataset is wrong by this
    list, and the operator documentation renders it.
    """
    return tuple(dataset for dataset in DATASETS if dataset.decision_gate)


def storage_sources():
    return STORAGE_SOURCES


def storage_sources_for_model(app_label, model_name):
    label = f"{app_label}.{model_name}"
    return tuple(source for source in STORAGE_SOURCES
                 if source.label == label
                 or label in {f"{app}.{model}"
                              for app, model, _ in source.reference_fields})
