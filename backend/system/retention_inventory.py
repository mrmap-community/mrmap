"""Read-only measurement of what the deployment persists and how fast it grows (#1498).

The declarations of the inventory live in :mod:`system.retention_datasets`;
this module asks the database and the filesystem what they actually hold. The
split is deliberate: the declarations are reviewable content whose pull request
is the review, and the numbers are never taken from them.

Three rules govern everything here.

**Read-only, and provably so.** Every statement runs inside one explicit
transaction opened as ``READ ONLY`` at ``REPEATABLE READ``, so a write fails
instead of happening and the whole report describes one instant. A test's outer
``TestCase`` block is already a read-write transaction, where PostgreSQL refuses
the ``SET``; the attempt is what matters and the report carries
``read_only_enforced`` so a reader can see which of the two states it is in.
Nothing in this module issues DDL, ``SET`` of a persistent parameter, a cache
deletion or a task dispatch.

**An unknown is never a zero.** Every measurement is a mapping with the keys
``measured``, ``value`` and ``reason`` (see :func:`measured` and
:func:`unavailable`). "This deployment has no slow request dumps" and "this run
could not read the log directory" are different statements; only the second one
is a gap, and graphing a gap as a flat line is exactly the failure #1498 exists
to prevent. The same rule covers the row estimate: ``reltuples`` of a table
which was never analysed is reported as an estimate-only reason, not as zero
rows.

**Bounded, always.** No full-table materialisation, no unbounded scan. The
growth sample is a bounded random sample whose size travels with the answer, the
media walk stops at a node budget and says it did, and the reference set is read
from one column with ``values_list`` rather than from model instances.

The selection primitives #1499 builds on are the module-level accessors of
:mod:`system.retention_datasets` — ``dataset_for``, ``growing_datasets``,
``gated_datasets``, ``datasets_for_policy``. Nothing in this package creates a
policy, enables a schedule, or deletes a row or a file: #1499 owns the registry
and executor, #1501 owns the file lifecycle, and the domain issues own their
own policies. Existing housekeeping keeps running unchanged until #1508
migrates it.
"""

import importlib
import json
import os
import shutil
import stat
from contextlib import contextmanager
from datetime import timedelta

from django.apps import apps
from django.conf import settings
from django.core.exceptions import FieldDoesNotExist
from django.db import connection, connections, transaction
from django.db import utils as db_utils
from django.utils import timezone
from psycopg import sql as psycopg_sql

from system.retention_datasets import (DATASETS, DECLARATION_VERSION,
                                       GROWTH_BOUNDED,
                                       RETENTION_SETTING_NAMES,
                                       STORAGE_SOURCES)

#: the view of "measure storage growth": how far back one report looks. The
#: window is stated in every answer it produces, because a rate without its
#: window is a guess.
MEASUREMENT_WINDOW_DAYS = 30

#: how far the same rate is projected forward for the risk ranking
HORIZON_DAYS = 90

#: how many timestamp values one growth sample may pull into memory. A table
#: which grew by tens of millions of rows inside the window is precisely the
#: read this module may not do unbounded, so the sample is random, bounded, and
#: its size is stated as the reason of its own answer.
GROWTH_SAMPLE_LIMIT = 20000

#: how many entries one media walk may look at, and how many file names one
#: reference set may hold. Exhausting either is reported as a gap: a partial
#: orphan list presented as a complete one is worse than no orphan list.
MEDIA_SCAN_NODE_BUDGET = 100000
MEDIA_REFERENCE_LIMIT = 100000

#: the depth a media walk descends below a prefix root. The ``upload_to``
#: functions of this project nest one directory per object id, so two levels is
#: the layout; a deeper tree is stopped by the budget rather than by recursion.
MEDIA_TREE_DEPTH = 2

#: the subdirectory of ``LOG_DIR`` the slow request dumps live in, as
#: ``system.logging.formatter`` writes it and ``system.apps`` sweeps it
SLOW_REQUEST_DUMP_SUBDIR = "logs"

#: the three keys every measurement answer carries
MEASURED = "measured"
VALUE = "value"
REASON = "reason"

#: the reason vocabulary. Each names a different thing a reader has to be able
#: to tell apart; none of them is a zero.
REASON_NOT_POSTGRESQL = "not_postgresql"
REASON_QUERY_FAILED = "query_failed"
REASON_TABLE_ABSENT = "table_absent"
REASON_ROW_ESTIMATE_ONLY = "row_estimate_only"
REASON_NO_TIME_FIELD_DECLARED = "no_time_field_declared"
REASON_NO_ROWS_IN_WINDOW = "no_rows_in_window"
REASON_NO_WAL_ACCESS = "no_wal_access"
REASON_NOT_REQUESTED = "not_requested"
REASON_UNSUPPORTED_STORAGE = "storage_without_filesystem_location"
REASON_DIRECTORY_ABSENT = "directory_absent"
REASON_DIRECTORY_UNREADABLE = "directory_unreadable"
REASON_SCAN_BUDGET_EXHAUSTED = "scan_budget_exhausted"
REASON_REFERENCE_LIMIT_EXHAUSTED = "reference_limit_exhausted"
REASON_PATH_OUTSIDE_ROOT = "path_outside_storage_root"
#: a FileField value which names this prefix but has no readable file: the row
#: exists and its document does not, which is #1150's finding and which has no
#: byte count to report
REASON_MISSING_REFERENCES = "references_without_file"
REASON_UNDECLARED = "undeclared_dataset"


class RetentionInventoryError(Exception):
    """The inventory was asked for something it must not answer with silence.

    Raised for an unknown ``--table`` or ``--dataset``: an operator who names a
    dataset and receives an empty report would read that as "this holds
    nothing", which is the opposite of the truth.
    """


def measured(value, **details):
    """An answer which happened. ``details`` says how, never why not."""
    answer = {MEASURED: True, VALUE: value, REASON: None}
    answer.update(details)
    return answer


def unavailable(reason, **details):
    """An answer which did not happen, with the reason it did not."""
    answer = {MEASURED: False, VALUE: None, REASON: reason}
    answer.update(details)
    return answer


def is_postgresql():
    return connections["default"].vendor == "postgresql"


def _model_subclasses(cls=None, found=None):
    """Every model class loaded in this process, abstract ones included."""
    from django.db import models as django_models

    found = {} if found is None else found
    for child in (cls or django_models.Model).__subclasses__():
        found.setdefault(f"{child._meta.app_label}.{child.__name__}", child)
        _model_subclasses(child, found)
    return found


def model_class(app_label, model_name):
    """The model class one declaration names, concrete *or* abstract.

    The app registry only knows the concrete models, and the abstract bases of
    this project's inheritance chains — ``MonitoringRun``, ``ProbeResult``,
    ``HttpRequestLog``, ``HttpResponseLog``, ``ServiceUpdateJob``,
    ``ServiceElementMapping``, ``ServiceAuthentication`` — are exactly what a
    family declaration names, because that is where the semantics and the
    timestamps of the family live. So the registry is asked first and the
    loaded classes second; a name neither knows raises rather than measuring
    something else.
    """
    try:
        return apps.get_model(app_label, model_name)
    except LookupError:
        pass
    model = _model_subclasses().get(f"{app_label}.{model_name}")
    if model is None:
        raise LookupError(
            f"app '{app_label}' provides no model '{model_name}'")
    return model


def db_table(app_label, model_name):
    """The physical table of one declared model, from Django's own metadata.

    Resolved here rather than stored in the declaration so a rename of a model
    or a ``db_table`` changes the inventory by changing the model — the only
    place which knows the truth. ``None`` for an abstract model: the datasets
    declared on an abstract base (the monitoring, probe, proxy-log and update
    chains) name the base because that is where the timestamps and the semantics
    live, while their rows live in the concrete subclasses.
    """
    model = model_class(app_label, model_name)
    if model._meta.abstract:
        return None
    return model._meta.db_table


def concrete_models(dataset):
    """The models of ``dataset`` which physically hold rows.

    An abstract declaration is skipped rather than failing: the datasets declared
    on an abstract base (the monitoring, probe, proxy-log and update chains) name
    the base because that is where the semantics and often the timestamps live,
    while their rows live in the concrete subclasses. A dataset with no concrete
    model at all is a broken declaration and raises, because answering "0 bytes"
    for it would be the false zero this module exists to avoid.
    """
    models = []
    for label in dataset.model_names:
        try:
            model = model_class(*label.split(".", 1))
        except LookupError as error:
            raise RetentionInventoryError(
                f"{dataset.id} declares {label}, which no installed app "
                f"provides: {error}")
        if model._meta.abstract:
            continue
        models.append(model)
    if not models:
        raise RetentionInventoryError(
            f"{dataset.id} declares only abstract models "
            f"({', '.join(dataset.model_names)}) and names no concrete table "
            f"to measure")
    return models


def dataset_tables(dataset):
    """Every physical table one dataset covers, declared order first.

    The multi-table-inheritance parents are included: a row of ``ProbeResult``
    lives in the base *and* in one subclass table, so measuring only the subclass
    would report the bytes of one monitoring kind and the timestamps of none.
    """
    tables = []
    for model in concrete_models(dataset):
        for concrete in [model, *model._meta.get_parent_list()]:
            table = concrete._meta.db_table
            if table not in tables:
                tables.append(table)
    return tables


def table_of_field(dataset, field_name):
    """The table of ``dataset`` which physically holds ``field_name``, or ``None``.

    An inheritance chain splits its columns over its tables, so the growth
    question is answerable only on the table which carries the timestamp; asking
    a subclass table for a parent's column would report a stale declaration where
    the truth is "this is the child table".
    """
    if not field_name:
        return None
    for model in concrete_models(dataset):
        for concrete in [model, *model._meta.get_parent_list()]:
            try:
                field = concrete._meta.get_field(field_name)
            except FieldDoesNotExist:
                continue
            if field.model is concrete and getattr(field, "column", None):
                return concrete._meta.db_table
    return None


def concrete_descendants(model):
    """``model`` itself plus its concrete descendants, when it holds rows.

    The FileFields of this project live on abstract bases — the probe results,
    the proxy logs, the service authentications — so the column has to be read
    through a concrete subclass, and every subclass needs reading: the values of
    a shared prefix are spread over the whole family.
    """
    if model._meta.abstract:
        models = []
        for child in model.__subclasses__():
            models.extend(concrete_descendants(child))
        return models
    return [model]


def graph_model(dataset):
    """The model whose metadata answers the deletion-graph question."""
    return concrete_models(dataset)[0]


#: the ceiling of one read statement. An unexpectedly huge table must not park
#: the operator's session in an unbounded scan: when the ceiling fires, the
#: answer is ``query_failed`` with its reason, which is honest, rather than a
#: report which never finishes.
STATEMENT_TIMEOUT_MS = 60000


@contextmanager
def read_only_report():
    """One consistent, read-only snapshot around the whole report.

    ``SET TRANSACTION ... READ ONLY`` only takes effect as the *first* statement
    of a transaction, so the guarantee depends on where the caller stands:

    *   the management command runs outside any transaction, gets a real
        ``READ ONLY`` ``REPEATABLE READ`` transaction, and a write inside it
        raises instead of happening;
    *   inside the transaction a ``TestCase`` already holds, PostgreSQL refuses
        to downgrade it — the flag answers ``False`` and the report says so,
        instead of claiming a guarantee it does not have. Nothing in this
        module writes either way.

    ``statement_timeout`` is set locally for the same block, which is what makes
    "bounded reads" a property rather than an intention.
    """
    enforced = False
    if not is_postgresql():
        yield enforced
        return
    outermost = not connection.in_atomic_block
    timeout = psycopg_sql.SQL("SET LOCAL statement_timeout = {}").format(
        psycopg_sql.Literal(STATEMENT_TIMEOUT_MS))
    with transaction.atomic():
        with connection.cursor() as cursor:
            if outermost:
                cursor.execute(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                enforced = True
            try:
                cursor.execute(timeout.as_string(connection.connection))
            except db_utils.DatabaseError:
                pass
        yield enforced


def _rows(cursor):
    """The result rows as dicts, keyed by the column names of the query.

    Django hands out plain tuples. Every read below asks the catalog for a
    handful of named columns at once, and reading those by position would make
    a column reorder in a PostgreSQL upgrade a wrong answer rather than a
    failure, so the module reads them by name.
    """
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _row(cursor):
    """The single row of a query, as a dict, or ``None``."""
    rows = _rows(cursor)
    return rows[0] if rows else None


def _exists(cursor, sql, params, column="exists"):
    cursor.execute(sql, params)
    row = _row(cursor)
    return bool(row and row[column])


def table_exists(table_name):
    """Whether the current schema holds a real (or partitioned) table."""
    with connection.cursor() as cursor:
        return _exists(
            cursor,
            "select exists("
            " select 1 from pg_catalog.pg_class c"
            " join pg_catalog.pg_namespace n on n.oid = c.relnamespace"
            " where n.nspname = current_schema()"
            " and c.relname = %s and c.relkind in ('r', 'p')"
            ") as exists",
            [table_name])


def _catalog_row(cursor, table_name):
    """Size, planner estimate and maintenance state of one table, one round trip.

    ``pg_total_relation_size`` is heap plus every index plus TOAST — the number
    an operator's freed disk space compares against. It is deliberately not
    split into heap/index/TOAST columns here: the per-relation counters of
    ``pg_statio_user_tables`` are cumulative since the last stats reset, so
    reading them as a current byte split would be a fabricated measurement. The
    split is named in the report's ``not_measured`` instead.
    """
    cursor.execute(
        "select pg_catalog.pg_total_relation_size(c.oid) as total_bytes,"
        " coalesce(nullif(c.reltuples::real, -1)::bigint, 0)"
        "   as estimated_rows,"
        " c.reltuples < 0 as never_analyzed,"
        " s.last_vacuum, s.last_autovacuum, s.last_analyze,"
        " s.last_autoanalyze, s.n_dead_tup"
        " from pg_catalog.pg_class c"
        " join pg_catalog.pg_namespace n on n.oid = c.relnamespace"
        " left join pg_catalog.pg_stat_user_tables s on s.relid = c.oid"
        " where n.nspname = current_schema()"
        " and c.oid = pg_catalog.to_regclass("
        "   current_schema() || '.' || %s)",
        [table_name])
    return _row(cursor)


def _column_exists(cursor, table_name, column_name):
    return _exists(
        cursor,
        "select exists("
        " select 1 from pg_catalog.pg_attribute a"
        " join pg_catalog.pg_class c on c.oid = a.attrelid"
        " join pg_catalog.pg_namespace n on n.oid = c.relnamespace"
        " where n.nspname = current_schema() and c.relname = %s"
        " and a.attname = %s and a.attnum > 0 and not a.attisdropped"
        ") as exists",
        [table_name, column_name])


def _window_count(cursor, table_name, time_column, since, until):
    """Rows whose time field lies in the window, plus the plan of that read.

    The plan travels with the count on purpose: #1497's acceptance is that a
    retention selection must be indexed, and a retention predicate which reads
    ``Seq Scan`` on a hundred-million-row table is a finding of this inventory,
    not a detail of #1499.
    """
    quoted_table = psycopg_sql.Identifier(table_name)
    quoted_time = psycopg_sql.Identifier(time_column)
    sql = psycopg_sql.SQL(
        "select count(*) as rows_in_window from {table} "
        "where {time} >= %s and {time} < %s"
    ).format(table=quoted_table, time=quoted_time)
    statement = sql.as_string(connection.connection)
    plan = None
    try:
        cursor.execute("explain (format json) " + statement, [since, until])
        plan = _plan_shape((_row(cursor) or {}).get("QUERY PLAN"))
    except db_utils.DatabaseError:
        plan = None
    cursor.execute(statement, [since, until])
    row = _row(cursor)
    return (row or {}).get("rows_in_window"), plan


def _plan_shape(plan):
    """The access method of the window read, as far as ``EXPLAIN`` said."""
    if not plan:
        return None
    try:
        node = plan[0]["Plan"]
    except (KeyError, IndexError, TypeError):
        return None
    shape = {"node_type": node.get("Node Type"),
             "total_cost": node.get("Total Cost"),
             "plan_rows": node.get("Plan Rows")}
    for key, name in (("Relation Name", "relation"), ("Index Name", "index"),
                      ("Index Scan Strategy", "strategy")):
        if node.get(key):
            shape[name] = node[key]
    return shape


def _sum_family(measurements, tables, key):
    """The sum of one answer across the tables of a dataset's family."""
    missing = unavailable(REASON_TABLE_ABSENT)
    parts = [measurements.get(name, {}).get(key, missing) for name in tables]
    complete = [part for part in parts if part[MEASURED]]
    if not complete:
        return parts[0] if parts else unavailable(REASON_TABLE_ABSENT)
    if len(complete) != len(parts):
        return unavailable(
            "some_family_tables_unmeasured",
            counted=sum(part[VALUE] or 0 for part in complete),
            unmeasured=len(parts) - len(complete))
    return measured(sum(part[VALUE] or 0 for part in complete),
                    tables=len(complete))


def _window_sample(cursor, table_name, time_column, since, until):
    """Median inter-arrival time of the window, from a bounded random sample.

    The median and not the mean: one backfill inside the window turns the mean
    gap of an hourly writer into microseconds, while the median of the gaps
    stays what it always was.

    The sample is drawn *before* the sort, so the heap sort holds at most
    ``GROWTH_SAMPLE_LIMIT`` timestamps rather than every timestamp of the
    window; ``sampled_rows`` and ``sample_limit`` travel with the answer so a
    reader knows how much of the window the median describes. What is not
    bounded by the sample is the scan of the window itself — that is bounded by
    the window and by ``STATEMENT_TIMEOUT_MS``, and a table for which even that
    is too much is a finding this report states rather than hides.
    """
    quoted_table = psycopg_sql.Identifier(table_name)
    quoted_time = psycopg_sql.Identifier(time_column)
    sql = psycopg_sql.SQL(
        "select percentile_cont(0.5) within group (order by gap)"
        "  as median_gap_seconds,"
        " count(*) as sampled_rows"
        " from ("
        "   select extract(epoch from (picked - lag(picked)"
        "          over (order by picked))) as gap"
        "   from ("
        "     select {time} as picked from {table}"
        "     where {time} >= %s and {time} < %s"
        "     order by random() limit %s"
        "   ) pick"
        " ) sampled where gap is not null"
    ).format(table=quoted_table, time=quoted_time)
    cursor.execute(sql.as_string(connection.connection),
                   [since, until, GROWTH_SAMPLE_LIMIT])
    return _row(cursor)


def _wal_bytes(cursor):
    """WAL written since startup, when the role may ask.

    ``pg_wal_bytes()`` needs superuser or membership of ``pg_read_all_stats``;
    a deployment whose inventory role has neither gets the reason rather than a
    zero, and the report says which role it ran as.
    """
    try:
        cursor.execute("select pg_catalog.pg_wal_bytes() as wal_bytes")
    except db_utils.DatabaseError:
        return unavailable(REASON_NO_WAL_ACCESS,
                           detail="pg_wal_bytes() needs superuser or "
                                  "pg_read_all_stats")
    row = _row(cursor)
    if not row or row["wal_bytes"] is None:
        return unavailable(REASON_NO_WAL_ACCESS)
    return measured(row["wal_bytes"])


def _role_name(cursor):
    try:
        cursor.execute("select current_user as role")
        row = _row(cursor)
        return row and row["role"]
    except db_utils.DatabaseError:
        return None


def _unanswered_table(reason, window_reason, wal_reason=REASON_NOT_REQUESTED):
    """The answer of a table about which nothing could be asked."""
    return {
        "total_bytes": unavailable(reason),
        "estimated_rows": unavailable(reason),
        "vacuum": unavailable(reason),
        "window_rows": unavailable(window_reason),
        "wal_bytes": unavailable(wal_reason),
        "indexes": [],
        "triggers": [],
    }


def _measure_one_table(cursor, name, answer, time_fields, since, until,
                       window_days, with_wal):
    """Fill one table's answer from the catalog, its indexes and its window."""
    if not table_exists(name):
        return
    row = _catalog_row(cursor, name)
    if row is None:
        return
    answer["total_bytes"] = measured(row["total_bytes"])
    if row["never_analyzed"]:
        answer["estimated_rows"] = unavailable(
            REASON_ROW_ESTIMATE_ONLY,
            detail="reltuples is unset: the table was never "
                   "analysed; the row count of the window is "
                   "still measured")
    else:
        answer["estimated_rows"] = measured(row["estimated_rows"])
    answer["vacuum"] = measured(
        row["n_dead_tup"],
        last_vacuum=row["last_vacuum"],
        last_autovacuum=row["last_autovacuum"],
        last_analyze=row["last_analyze"],
        last_autoanalyze=row["last_autoanalyze"])
    answer["indexes"] = _indexes(cursor, name)
    answer["triggers"] = _triggers(cursor, name)
    if with_wal:
        answer["wal_bytes"] = _wal_bytes(cursor)
    answer["window_rows"] = _window(
        cursor, name, time_fields.get(name), since, until, window_days)


def _mark_unmeasured(answers, detail):
    """Name why an answer the snapshot did not deliver is unknown."""
    for answer in answers.values():
        for key in ("total_bytes", "estimated_rows", "vacuum", "window_rows"):
            if not answer[key][MEASURED]:
                answer[key] = unavailable(REASON_QUERY_FAILED, detail=detail)


def measure_tables(table_names, time_fields=None, since=None, until=None,
                   with_wal=False):
    """One answer per table, in one read-only snapshot.

    Returns ``{table: {"total_bytes": ..., "estimated_rows": ...,
    "vacuum": ..., "window_rows": ..., "indexes": [...], "triggers": [...],
    "wal_bytes": ...}}``. Every number is individually optional; the caller can
    tell "small" from "unknown" without parsing the mapping.
    """
    time_fields = time_fields or {}
    if not is_postgresql():
        return {name: _unanswered_table(REASON_NOT_POSTGRESQL,
                                        REASON_NOT_POSTGRESQL,
                                        REASON_NOT_POSTGRESQL)
                for name in table_names}
    answers = {name: _unanswered_table(REASON_TABLE_ABSENT,
                                       REASON_NO_TIME_FIELD_DECLARED)
               for name in table_names}
    window_days = ((until - since).days if since and until else None)
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            for name in table_names:
                _measure_one_table(cursor, name, answers[name], time_fields,
                                   since, until, window_days, with_wal)
    except db_utils.DatabaseError as error:
        _mark_unmeasured(answers, str(error))
    return answers


def _window(cursor, table_name, time_column, since, until, window_days):
    if not time_column:
        return unavailable(REASON_NO_TIME_FIELD_DECLARED)
    if not _column_exists(cursor, table_name, time_column):
        return unavailable(REASON_NO_TIME_FIELD_DECLARED,
                           time_field=time_column,
                           detail="no such column; the declaration is stale")
    rows, plan = _window_count(cursor, table_name, time_column, since, until)
    details = {"time_field": time_column, "window_days": window_days,
               "plan": plan}
    if not rows:
        return unavailable(REASON_NO_ROWS_IN_WINDOW, rows_in_window=0,
                           **details)
    sample = _window_sample(cursor, table_name, time_column, since, until)
    return measured(rows, median_gap_seconds=sample["median_gap_seconds"],
                    sampled_rows=sample["sampled_rows"],
                    sample_limit=GROWTH_SAMPLE_LIMIT, **details)


def _indexes(cursor, table_name):
    """The indexes of one table, from the catalog.

    Read because the acceptance of #1498 asks for the *index needs* of a
    dataset: whether the retention predicate — "terminal, older than, beyond
    the per-scope cap" — is answerable from an index decides whether a policy
    on that table can be a bounded ``DELETE`` or becomes a scan.
    """
    cursor.execute(
        "select c.relname as name,"
        " pg_catalog.pg_get_indexdef(i.indexrelid) as definition,"
        " i.indisunique as is_unique, i.indisvalid as is_valid"
        " from pg_catalog.pg_index i"
        " join pg_catalog.pg_class c on c.oid = i.indexrelid"
        " join pg_catalog.pg_class t on t.oid = i.indrelid"
        " join pg_catalog.pg_namespace n on n.oid = t.relnamespace"
        " where n.nspname = current_schema() and t.relname = %s"
        " order by c.relname",
        [table_name])
    return [{key: value for key, value in row.items() if value is not None}
            for row in _rows(cursor)]


def _triggers(cursor, table_name):
    """The non-internal triggers of one table, including pgtrigger's.

    A row a policy would take may be guarded by a ``Protect`` trigger — the
    keyword maintenance of #1009 is the first-party example — so a selection
    which does not know its triggers is not a selection, it is a migration
    failure waiting to happen. ``pgtrigger_protection`` is where an orphaned
    protection of a rolled-back migration shows up.
    """
    cursor.execute(
        "select tg.tgname as name,"
        " pg_catalog.pg_get_triggerdef(tg.oid) as definition,"
        " tg.tgenabled <> 'D' as is_enabled"
        " from pg_catalog.pg_trigger tg"
        " join pg_catalog.pg_class t on t.oid = tg.tgrelid"
        " join pg_catalog.pg_namespace n on n.oid = t.relnamespace"
        " where n.nspname = current_schema() and t.relname = %s"
        " and not tg.tgisinternal"
        " order by tg.tgname",
        [table_name])
    return [{key: value for key, value in row.items() if value is not None}
            for row in _rows(cursor)]


def undeclared_tables():
    """Tables of an inventoried app which no declaration covers.

    This is what keeps "the inventory is complete" checkable instead of
    aspirational: an app added to ``INSTALLED_APPS``, or a model added to an
    app, appears here until it is declared. The epic's rule that a new
    continuously growing model must declare its lifecycle is enforced by this
    report rather than by memory.
    """
    if not is_postgresql():
        return []
    declared = set()
    for dataset in DATASETS:
        declared.update(dataset_tables(dataset))
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                "select c.relname as table,"
                " pg_catalog.pg_total_relation_size(c.oid) as total_bytes,"
                " coalesce(nullif(c.reltuples::real, -1)::bigint, 0)"
                "   as estimated_rows"
                " from pg_catalog.pg_class c"
                " join pg_catalog.pg_namespace n on n.oid = c.relnamespace"
                " where n.nspname = current_schema()"
                " and c.relkind in ('r', 'p')"
                " order by total_bytes desc nulls last")
            rows = _rows(cursor)
    except db_utils.DatabaseError:
        return []
    return [dict(row, reason=REASON_UNDECLARED)
            for row in rows if row["table"] not in declared]


# ---------------------------------------------------------------------------
# media
# ---------------------------------------------------------------------------

def _storage_location(storage):
    """The filesystem location of a storage, or ``None`` when it has none.

    Object storage has no ``location``; the source is then reported with the
    reason ``storage_without_filesystem_location`` rather than as zero bytes,
    which is the difference between a gap and a false claim.
    """
    location = getattr(storage, "location", None)
    if not location:
        return None
    return location if os.path.isdir(location) else None


def _is_within(root, candidate):
    """Whether ``candidate`` resolves below ``root`` — the traversal guard.

    Both sides are resolved first, so ``a/../../etc/passwd`` and a symlink out
    of the media root are rejected as findings instead of being opened. The
    inventory never reads the body of a file, so a credential-bearing path
    cannot be disclosed by it either.
    """
    try:
        root_real = os.path.realpath(root)
        candidate_real = os.path.realpath(candidate)
    except OSError:
        return False
    return candidate_real == root_real or candidate_real.startswith(
        root_real + os.sep)


def _file_names(app_label, model_name, field_name):
    """The file names one FileField column holds, deduplicated.

    ``values_list`` on the single column is the whole read: no instance is
    materialised, no relation is followed. When the field lives on an abstract
    base, every concrete descendant is asked — the values of a shared prefix are
    spread over the family and a reference missed is an orphan invented. The
    limit is a budget, not a sample: exhausting it makes the orphan answer
    unavailable rather than partial.
    """
    names = set()
    failed = []
    column = f"{app_label}.{model_name}.{field_name}"
    try:
        models = concrete_descendants(model_class(app_label, model_name))
        if not models:
            raise LookupError(f"{column} has no concrete model")
    except (LookupError, FieldDoesNotExist):
        return names, False, [column]
    for model in models:
        try:
            for name in model.objects.values_list(field_name, flat=True):
                if not name:
                    continue
                if len(names) >= MEDIA_REFERENCE_LIMIT:
                    return names, True, failed
                names.add(name)
        except db_utils.DatabaseError:
            # no such table (a partially migrated deployment) or no privilege:
            # the reference set is incomplete, so the orphan answer of this
            # prefix cannot be claimed at all
            failed.append(f"{app_label}.{model.__name__}.{field_name}")
    return names, False, failed


def _referenced_names(source):
    """Every declared FileField value which could point into this prefix.

    A reference set is the union over ``source.reference_fields`` rather than
    over one column, because the prefixes of this project are shared: the
    ``xml_documents`` tree holds the backups of three record tables and of the
    capability documents alike, and a file named by any of them is referenced.
    """
    names = set()
    truncated = False
    failed = []
    for app_label, model_name, field_name in source.reference_fields:
        found, hit_limit, errors = _file_names(app_label, model_name,
                                               field_name)
        names.update(found)
        truncated = truncated or hit_limit
        failed.extend(errors)
    return names, truncated, failed


def _nested_prefixes(prefix):
    """Declared prefixes strictly below ``prefix``, so nothing is counted twice.

    ``temporary_md_metadata_file/registration`` is a source of its own; walking
    its parent must not also report its files, or the same orphan bytes appear
    under two ids.
    """
    nested = []
    for other in STORAGE_SOURCES:
        if other.prefix == prefix or not other.prefix:
            continue
        if other.prefix.startswith(prefix.rstrip("/") + "/"):
            nested.append(other.prefix)
    return nested


def _walk(root, prefix, budget, skip_prefixes=()):
    """Collect ``(bytes, files, entries, truncated)`` below one prefix.

    Symlinks are never followed and never counted: a media tree holds names
    built partly from remote responses, and following a link out of the prefix
    is exactly what a "read-only, bounded" report must not do. Entries below a
    nested declared prefix are left to that prefix's own source, so the two
    sources of one shared tree never count the same byte twice.
    """
    base = os.path.join(root, *prefix.split("/")) if prefix else root
    if not os.path.isdir(base):
        return 0, 0, [], False
    skip_real = {os.path.realpath(os.path.join(root, *nested.split("/")))
                 for nested in skip_prefixes}
    total_bytes = 0
    total_files = 0
    entries = []
    truncated = False
    stack = [(base, 0)]
    while stack:
        path, depth = stack.pop()
        try:
            with os.scandir(path) as scan:
                entries_here = list(scan)
        except OSError:
            continue
        for entry in entries_here:
            if budget[0] <= 0:
                return total_bytes, total_files, entries, True
            budget[0] -= 1
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if os.path.realpath(entry.path) in skip_real:
                        continue
                    if depth + 1 > MEDIA_TREE_DEPTH:
                        truncated = True
                    else:
                        stack.append((entry.path, depth + 1))
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                size = entry.stat(follow_symlinks=False).st_size
            except OSError:
                continue
            total_bytes += size
            total_files += 1
            if len(entries) < MEDIA_REFERENCE_LIMIT:
                relative = os.path.relpath(entry.path, root)
                entries.append((relative.replace(os.sep, "/"), size))
    return total_bytes, total_files, entries, truncated


def measure_media_source(source, include_media=True):
    """One declared prefix: bytes, files, referenced, unreferenced, undetermined.

    ``unreferenced_bytes`` is the finding #1501 owns: bytes below a
    retention-relevant prefix which no declared FileField column names. It is
    reported and never deleted here — deleting is #1501's work, behind its own
    safety gates.
    """
    answer = {
        "id": source.id,
        "prefix": source.prefix,
        "kind": source.kind,
        "owner": source.owner,
        "lifecycle": source.lifecycle,
        "policy_candidate": source.policy_candidate,
        "reference_scope": source.reference_scope,
        "protected_dependencies": list(source.protected_dependencies),
        "referenced_by": [f"{app}.{model}.{field}" for app, model, field
                          in source.reference_fields],
    }
    if not include_media:
        for key in ("total_bytes", "files", "referenced_bytes",
                    "unreferenced_bytes", "undetermined_bytes"):
            answer[key] = unavailable(REASON_NOT_REQUESTED)
        answer["reasons"] = [REASON_NOT_REQUESTED]
        return answer

    try:
        models = concrete_descendants(
            model_class(source.app_label, source.model_name))
        if not models:
            raise LookupError(f"{source.label} has no concrete model")
        storage = models[0]._meta.get_field(source.field_name).storage
    except (LookupError, AttributeError, FieldDoesNotExist) as error:
        # a stale declaration must fail loudly, in the report rather than in a
        # silently empty bucket
        for key in ("total_bytes", "files", "referenced_bytes",
                    "unreferenced_bytes", "undetermined_bytes"):
            answer[key] = unavailable(REASON_QUERY_FAILED, detail=str(error))
        answer["reasons"] = [REASON_QUERY_FAILED]
        return answer

    location = _storage_location(storage)
    if location is None:
        for key in ("total_bytes", "files", "referenced_bytes",
                    "unreferenced_bytes", "undetermined_bytes"):
            answer[key] = unavailable(REASON_UNSUPPORTED_STORAGE)
        answer["reasons"] = [REASON_UNSUPPORTED_STORAGE]
        return answer

    root = os.path.realpath(location)
    budget = [MEDIA_SCAN_NODE_BUDGET]
    total_bytes, files, entries, truncated = _walk(
        root, source.prefix, budget, _nested_prefixes(source.prefix))
    answer["total_bytes"] = measured(total_bytes, files=files, root=root)
    answer["files"] = measured(files)

    referenced, refs_truncated, refs_failed = _referenced_names(source)
    walked = dict(entries)
    referenced_bytes = sum(size for name, size in walked.items()
                           if name in referenced)
    unreferenced_bytes = sum(size for name, size in walked.items()
                             if name not in referenced)
    unreferenced_files = sum(1 for name in walked if name not in referenced)
    prefix_root = source.prefix.rstrip("/")
    nested_real = {os.path.realpath(os.path.join(root, *nested.split("/")))
                   for nested in _nested_prefixes(source.prefix)}
    missing_references = []
    outside = []
    reasons = []
    for name in sorted(referenced):
        # a value which does not resolve below the storage root is a finding:
        # it is named, never opened. The inventory reads no file body at all,
        # so it cannot disclose what a bad path points at.
        if os.path.isabs(name) or not _is_within(root, os.path.join(root, name)):
            outside.append(name)
            continue
        if name in walked:
            continue
        if not name.startswith(prefix_root + "/"):
            # the file belongs to another declared prefix and is measured there
            continue
        if os.path.realpath(os.path.join(root, *name.split("/"))) in (
                nested_real):
            continue
        # the reference names this prefix but has no readable file: the row
        # exists and its document does not. Its bytes cannot be measured, so
        # they are neither counted as referenced nor as orphan bytes.
        if _size_below(root, name) is None:
            missing_references.append(name)

    if truncated:
        answer["total_bytes"] = unavailable(REASON_SCAN_BUDGET_EXHAUSTED,
                                            bytes_counted=total_bytes,
                                            files_counted=files)
        answer["unreferenced_bytes"] = unavailable(
            REASON_SCAN_BUDGET_EXHAUSTED,
            detail=f"the walk stopped at {MEDIA_SCAN_NODE_BUDGET} entries")
        reasons.append(REASON_SCAN_BUDGET_EXHAUSTED)
    else:
        answer["unreferenced_bytes"] = measured(unreferenced_bytes,
                                                files=unreferenced_files)
    if refs_failed:
        # an incomplete reference set would report the rows it could not read
        # as orphans, which is the one error a read-only inventory must not
        # make: its output is the evidence #1501 would delete by
        unreadable = ", ".join(sorted(set(refs_failed))[:10])
        answer["referenced_bytes"] = unavailable(
            REASON_QUERY_FAILED,
            detail=f"unreadable reference columns: {unreadable}")
        answer["unreferenced_bytes"] = unavailable(
            REASON_QUERY_FAILED,
            detail=f"the reference set is incomplete ({unreadable}), so "
                   f"nothing below this prefix may be called orphaned")
        reasons.append(REASON_QUERY_FAILED)
    elif refs_truncated:
        answer["referenced_bytes"] = unavailable(
            REASON_REFERENCE_LIMIT_EXHAUSTED,
            detail=f"the reference set stopped at {MEDIA_REFERENCE_LIMIT} "
                   f"names")
        reasons.append(REASON_REFERENCE_LIMIT_EXHAUSTED)
    else:
        answer["referenced_bytes"] = measured(referenced_bytes,
                                              references=len(referenced))
    if missing_references:
        # the bytes of a file which is not there cannot be measured; the count
        # and a sample of names are the honest answer, and they are the number
        # which makes a /csw page fail (#1150)
        answer["undetermined_bytes"] = unavailable(
            REASON_MISSING_REFERENCES, files=len(missing_references),
            examples=missing_references[:20],
            detail="references which name this prefix but have no readable "
                   "file: the record exists and its document does not")
        reasons.append(REASON_MISSING_REFERENCES)
    else:
        answer["undetermined_bytes"] = measured(0)
    if outside:
        answer["paths_outside_storage_root"] = outside[:20]
        reasons.append(REASON_PATH_OUTSIDE_ROOT)
    answer["reasons"] = reasons
    return answer


def _size_below(root, name):
    """The size of one referenced file below ``root``, or ``None`` if unknown.

    ``None`` means "the storage could not say", which the caller counts as
    undetermined. It never means zero: an unreadable file is not an absent one.
    """
    path = os.path.join(root, name)
    if not _is_within(root, path):
        return None
    try:
        info = os.stat(path)
    except OSError:
        return None
    return info.st_size if stat.S_ISREG(info.st_mode) else None


def measure_log_directory(include_media=True):
    """The slow request dumps below ``LOG_DIR`` — the deployment's own writes.

    Nothing in the database references these, by design: their lifecycle is the
    sweep of ``system.apps`` and the operator's retention setting. They are
    therefore reported as unreferenced *from the database's point of view*,
    which is a statement about the reference set and not a claim that the files
    may go.
    """
    answer = {"id": "slow_request_dumps", "prefix": SLOW_REQUEST_DUMP_SUBDIR,
              "kind": "operational_logs", "owner": "deployment operators",
              "lifecycle": "written by the request path, bounded by the sweep "
                           "of system.apps",
              "policy_candidate": "none",
              "reference_scope": "orphan_relevant",
              "protected_dependencies": [
                  "system.tasks.delete_old_slow_request_dumps is the existing "
                  "mechanism (#1508 migrates it, does not duplicate it)"],
              "referenced_by": []}
    log_dir = getattr(settings, "LOG_DIR", None)
    if not include_media:
        for key in ("total_bytes", "files", "referenced_bytes",
                    "unreferenced_bytes", "undetermined_bytes"):
            answer[key] = unavailable(REASON_NOT_REQUESTED)
        answer["reasons"] = [REASON_NOT_REQUESTED]
        return answer
    if not log_dir or not os.path.isdir(log_dir):
        for key in ("total_bytes", "files", "unreferenced_bytes"):
            answer[key] = unavailable(REASON_DIRECTORY_ABSENT, path=log_dir)
        answer["referenced_bytes"] = measured(0)
        answer["undetermined_bytes"] = measured(0)
        answer["reasons"] = [REASON_DIRECTORY_ABSENT]
        return answer
    budget = [MEDIA_SCAN_NODE_BUDGET]
    total_bytes, files, _, truncated = _walk(
        log_dir, SLOW_REQUEST_DUMP_SUBDIR, budget)
    answer["total_bytes"] = (
        measured(total_bytes, files=files, root=os.path.realpath(log_dir))
        if not truncated else
        unavailable(REASON_SCAN_BUDGET_EXHAUSTED, bytes_counted=total_bytes))
    answer["files"] = measured(files)
    answer["referenced_bytes"] = measured(
        0, detail="no database reference exists by design")
    answer["unreferenced_bytes"] = measured(
        total_bytes, files=files,
        detail="unreferenced from the database's point of view; the existing "
               "sweep owns this tree")
    answer["undetermined_bytes"] = measured(0)
    answer["reasons"] = ([REASON_SCAN_BUDGET_EXHAUSTED] if truncated else [])
    return answer


def measure_media(include_media=True):
    """Every declared media prefix, plus the log tree, plus the media totals."""
    sources = [measure_media_source(source, include_media)
               for source in STORAGE_SOURCES]
    sources.append(measure_log_directory(include_media))
    totals = {}
    for key in ("total_bytes", "referenced_bytes", "unreferenced_bytes",
                "undetermined_bytes"):
        parts = [source[key] for source in sources]
        complete = [part for part in parts if part[MEASURED]]
        if len(complete) == len(parts):
            totals[key] = measured(sum(part[VALUE] or 0 for part in complete))
        else:
            totals[key] = unavailable(
                "some_sources_unmeasured",
                bytes_counted=sum(part[VALUE] or 0 for part in complete),
                unmeasured=len(parts) - len(complete))
    totals["sources_not_measured"] = sum(
        1 for source in sources if not source["total_bytes"][MEASURED])
    return {"sources": sources, **totals}


# ---------------------------------------------------------------------------
# caches, broker, disk, postgres
# ---------------------------------------------------------------------------

def _redact(location):
    """Keep the shape of a connection URI, drop any credential in it.

    This report is meant to be pasted into an issue and attached to a ticket; a
    URL carrying a password is not.
    """
    if not location:
        return None
    text = str(location)
    if "://" in text and "@" in text.split("://", 1)[1]:
        scheme, rest = text.split("://", 1)
        return f"{scheme}://***@{rest.rsplit('@', 1)[-1]}"
    return text


def cache_facts():
    """What the caches and the broker are, and which bound applies to them.

    Redis holds three things the PostgreSQL inventory never sees: the Celery
    result backend, the default cache and the broker queues. Answered from the
    *configured* bounds rather than from a live ``INFO`` on purpose — a network
    round trip would make a read-only report depend on a broker being reachable,
    and the configured bound is the number an operator acts on. The measured key
    count and byte total of the broker is #1500's, which is the CLI.
    """
    caches = {}
    for name, config in (getattr(settings, "CACHES", {}) or {}).items():
        backend = config.get("BACKEND", "") or ""
        caches[name] = {
            "backend": backend.rsplit(".", 2)[-2] if backend else None,
            "location": _redact(config.get("LOCATION")),
            "timeout": config.get("TIMEOUT", 300),
            "bounded_by": ("redis maxmemory policy" if "redis" in backend.lower()
                           else "process lifetime"),
        }
    return {
        "caches": caches,
        "celery_result_backend": _redact(
            getattr(settings, "CELERY_RESULT_BACKEND", None)),
        "celery_result_expires_seconds": getattr(
            settings, "CELERY_RESULT_EXPIRES", None),
        "celery_broker_url": _redact(getattr(settings, "CELERY_BROKER_URL", None)),
        "note": "configured bounds read from settings; the measured key count "
                "and bytes of the broker and of the result backend belong to "
                "#1500",
    }


def disk_facts():
    """Free bytes and inodes of the filesystems the deployment writes to.

    "The tables are small" and "the disk is full" are invisible to both
    ``pg_total_relation_size`` and a media walk, which is why the issue asks for
    disk bytes and inodes. It is also why the vacuum state and the WAL counter
    travel with the table sizes: ``DELETE`` returning space to PostgreSQL does
    not return it to the operating system until a vacuum, a rewrite or a
    checkpoint reclaims the WAL.
    """
    facts = {}
    for label, path in (("media_root", getattr(settings, "MEDIA_ROOT", None)),
                        ("log_dir", getattr(settings, "LOG_DIR", None))):
        if not path:
            facts[label] = unavailable(REASON_DIRECTORY_ABSENT)
            continue
        probe = path
        while probe and not os.path.exists(probe):
            probe = os.path.dirname(probe)
        if not probe:
            facts[label] = unavailable(REASON_DIRECTORY_ABSENT, path=path)
            continue
        try:
            usage = shutil.disk_usage(probe)
            stats = os.statvfs(probe)
        except OSError as error:
            facts[label] = unavailable(REASON_DIRECTORY_UNREADABLE,
                                       detail=str(error), path=path)
            continue
        # a directory the deployment has not written to yet is answered with
        # the filesystem it would land on, and says so: "the log dir does not
        # exist" is not "there is no space problem"
        facts[label] = measured(
            usage.free, path=os.path.realpath(probe),
            exists=os.path.realpath(probe) == os.path.realpath(path),
            total_bytes=usage.total, used_bytes=usage.used,
            inodes_free=stats.f_ffree, inodes_total=stats.f_files)
    return facts


def postgresql_facts(with_wal=False):
    """Cluster-level answers: version, the autovacuum/WAL settings, WAL bytes."""
    facts = {"version": connection.pg_version if is_postgresql() else None,
             "role": None,
             "wal_bytes": unavailable(REASON_NOT_POSTGRESQL),
             "settings": unavailable(REASON_NOT_POSTGRESQL)}
    if not is_postgresql():
        return facts
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            facts["role"] = _role_name(cursor)
            if with_wal:
                facts["wal_bytes"] = _wal_bytes(cursor)
            else:
                facts["wal_bytes"] = unavailable(REASON_NOT_REQUESTED,
                                                 detail="ask with --wal")
            cursor.execute(
                "select name, setting, unit from pg_catalog.pg_settings"
                " where name in ('autovacuum', 'autovacuum_max_workers',"
                " 'autovacuum_vacuum_scale_factor',"
                " 'autovacuum_vacuum_cost_delay', 'max_wal_size',"
                " 'wal_level', 'track_counts', 'maintenance_work_mem')"
                " order by name")
            facts["settings"] = measured(
                {row["name"]: {"setting": row["setting"],
                               "unit": row["unit"]}
                 for row in _rows(cursor)})
    except db_utils.DatabaseError as error:
        facts["settings"] = unavailable(REASON_QUERY_FAILED, detail=str(error))
    return facts


def setting_value(name):
    """Resolve one setting, from ``settings`` or from the owning app's module.

    This project keeps some of its knobs in ``registry/settings.py`` rather than
    in the project settings, and the storage-bounding ones are spread over both.
    Reporting only ``django.conf.settings`` would call the harvest grace period
    and the registration lease *absent*, which is exactly the kind of false gap
    this report must not contain.

    Returns ``(value, source)``; ``source`` is ``None`` when no settings module
    of the installed apps defines the name, which the caller reports as absent
    rather than defaulting — a default silently restored by a refactor is how a
    retention window goes from 90 days to forever without anyone noticing.
    """
    if hasattr(settings, name):
        return getattr(settings, name), "settings"
    for config in apps.get_app_configs():
        module_name = f"{config.name}.settings"
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        if hasattr(module, name):
            return getattr(module, name), module_name
    return None, None


def retention_settings():
    """The storage-bounding settings exactly as this instance has them.

    The names come from the single list in :mod:`system.retention_datasets`, so
    the report, the operator documentation and #1499's registry cannot disagree
    about which knobs bound storage.
    """
    answer = {}
    for name in RETENTION_SETTING_NAMES:
        value, source = setting_value(name)
        answer[name] = {"value": value, "declared": source is not None,
                        "source": source}
    return answer


# ---------------------------------------------------------------------------
# the report
# ---------------------------------------------------------------------------

def dataset_rows():
    """One row per declared dataset, with its deletion graph.

    The graph is read from Django's own metadata rather than transcribed here:
    an ``on_delete`` an engineer changes is reflected in the inventory by
    changing the model, which is the only place that knows it. ``incoming`` is
    the dangerous half for a policy — the references which either take rows of
    this dataset with them (``CASCADE``) or refuse the deletion (``PROTECT``),
    which is the FK graph #1497 forbids a sweep to walk blindly.
    """
    rows = []
    for dataset in DATASETS:
        tables = dataset_tables(dataset)
        rows.append({
            "id": dataset.id,
            "model": dataset.label,
            "tables": tables,
            "table": tables[0],
            "growth_table": table_of_field(dataset, dataset.time_field),
            "app_label": dataset.app_label,
            "growth": dataset.growth,
            "classification": dataset.classification,
            "owner": dataset.owner,
            "lifecycle": dataset.lifecycle,
            "policy_candidate": dataset.policy_candidate,
            "protected_dependencies": list(dataset.protected_dependencies),
            "growth_drivers": list(dataset.growth_drivers),
            "writers": list(dataset.writers),
            "readers": list(dataset.readers),
            "terminal_states": list(dataset.terminal_states),
            "existing_cleanup": dataset.existing_cleanup,
            "existing_setting": dataset.existing_setting,
            "time_field": dataset.time_field,
            "scope_field": dataset.scope_field,
            "protected_min": dataset.protected_min,
            "provisional_age_days": dataset.provisional_age_days,
            "provisional_max_per_scope": dataset.provisional_max_per_scope,
            "index_needs": list(dataset.index_needs),
            "migration_needs": list(dataset.migration_needs),
            "test_expectations": dataset.test_expectations,
            "decision_gate": dataset.decision_gate,
            "notes": dataset.notes,
            "references": _reference_rows(dataset),
        })
    return rows


def _reference_rows(dataset):
    model = graph_model(dataset)
    incoming = []
    for relation in model._meta.related_objects:
        field = relation.field
        if field.related_model is None:
            continue
        on_delete = getattr(field.remote_field, "on_delete", None)
        incoming.append({
            "from": f"{field.model._meta.app_label}."
                    f"{field.model._meta.model_name}",
            "field": field.name,
            "on_delete": on_delete.__name__ if on_delete else None,
            "nullable": bool(field.null),
        })
    outgoing = []
    for field in model._meta.fields:
        if not field.is_relation or field.related_model is None:
            continue
        on_delete = getattr(field.remote_field, "on_delete", None) \
            if field.remote_field else None
        outgoing.append({
            "to": f"{field.related_model._meta.app_label}."
                  f"{field.related_model._meta.model_name}",
            "field": field.name,
            "on_delete": on_delete.__name__ if on_delete else None,
            "nullable": bool(field.null),
        })
    return {"incoming": sorted(incoming, key=lambda row: (row["from"],
                                                          row["field"])),
            "outgoing": sorted(outgoing, key=lambda row: (row["to"],
                                                          row["field"]))}


def _round(value, digits=0):
    """Round a measured number, keeping "not measured" distinct from zero."""
    return None if value is None else round(value, digits)


def _growth_rates(window, total, estimated_rows, window_days):
    """The two rates of one dataset, or ``None`` where measurement failed.

    ``rows_per_day`` is counted over the window; ``bytes_per_day`` multiplies it
    by the current average row size and therefore inherits the uncertainty of
    the row estimate. Either is ``None`` when its input is unknown, so a
    dataset is ranked only when both are known.
    """
    if not window[MEASURED]:
        return None, None, None
    days = window.get("window_days") or window_days
    if not days:
        return None, None, None
    rate = (window[VALUE] or 0) / days
    if not (total[MEASURED] and estimated_rows[MEASURED]
            and estimated_rows[VALUE]):
        return rate, None, None
    avg_row_bytes = (total[VALUE] or 0) / estimated_rows[VALUE]
    return rate, rate * avg_row_bytes, avg_row_bytes


def growth_estimates(rows, measurements, window_days, horizon_days):
    """Risk-ranked growth estimates, measured where measurement was possible.

    Two rates are answered and never merged, because they are different
    statements:

    ``rows_per_day``
        counted rows of the window over the window — a measurement, whose
        reason travels with it when the window held nothing;
    ``bytes_per_day``
        that rate times the current average row size, so it inherits every
        uncertainty of the row estimate and is labelled ``estimated``.

    A third number, ``projected_bytes``, is the second one over the horizon. It
    is the ranking key: the ranking of this deployment's risk is derived from
    what this deployment holds, which is what "risk-ranked, measured where
    possible" asks for, and never from a table of assertions. A dataset whose
    window could not be measured keeps ``rank`` of ``None`` rather than a rank
    invented from its declaration.
    """
    estimates = []
    for row in rows:
        answer = measurements.get(row["table"], {})
        window = answer.get("window_rows", unavailable(REASON_NOT_REQUESTED))
        # an inheritance chain stores one row over several tables, so the bytes
        # and the rows of a dataset are the sum over its family; a table which
        # could not be measured makes the whole sum unmeasured rather than small
        total = _sum_family(measurements, row["tables"], "total_bytes")
        estimated_rows = _sum_family(measurements, row["tables"],
                                     "estimated_rows")
        rate, bytes_per_day, avg_row_bytes = _growth_rates(
            window, total, estimated_rows, window_days)
        estimates.append({
            "id": row["id"],
            "table": row["table"],
            "owner": row["owner"],
            "growth": row["growth"],
            "classification": row["classification"],
            "policy_candidate": row["policy_candidate"],
            "time_field": row["time_field"],
            "window_rows": window.get(VALUE),
            "window_reason": window.get(REASON),
            "median_gap_seconds": window.get("median_gap_seconds"),
            "rows_per_day": _round(rate, 3),
            "avg_row_bytes": _round(avg_row_bytes, 1),
            "bytes_per_day": _round(bytes_per_day),
            "total_bytes": total.get(VALUE),
            "estimated_rows": estimated_rows.get(VALUE),
            "projected_bytes": _round(bytes_per_day * horizon_days)
            if bytes_per_day is not None else None,
            "rank": None,
        })
    ranked = sorted(
        [item for item in estimates if item["bytes_per_day"] is not None],
        key=lambda item: -item["bytes_per_day"])
    for position, item in enumerate(ranked, start=1):
        item["rank"] = position
    return estimates


def _measurement_units(rows, only_tables=None, only_datasets=None):
    """The physical tables one report measures, after any narrowing.

    A family declaration contributes all of its tables: the history family is
    one policy question answered over eleven physical tables, and an operator
    who asks for ``history_service_records`` wants the eleven, not the one the
    declaration names for its timestamps.
    """
    selected = []
    for row in rows:
        if only_datasets and row["id"] not in only_datasets:
            continue
        if only_tables and not (set(row["tables"]) & set(only_tables)):
            continue
        selected.append(row)
    if only_tables:
        known = {name for row in rows for name in row["tables"]}
        unknown = sorted(set(only_tables) - known)
        if unknown:
            raise RetentionInventoryError(
                f"no declared dataset covers {', '.join(unknown)}; the "
                f"catalog knows {len(known)} declared tables — run without "
                f"--table to see the undeclared ones")
    if only_datasets:
        known = {row["id"] for row in rows}
        unknown = sorted(set(only_datasets) - known)
        if unknown:
            raise RetentionInventoryError(
                f"no dataset named {', '.join(unknown)}; ask for one of the "
                f"{len(known)} declared ids")
    return selected


def build_inventory(window_days=MEASUREMENT_WINDOW_DAYS, horizon_days=HORIZON_DAYS,
                    tables=None, datasets=None, with_wal=False,
                    include_media=True, include_disk=True):
    """The whole report: declarations, measurements, estimates and provenance.

    One read-only snapshot is opened around the database half, so the catalog
    sizes, the window counts and the FK-derived graph describe one instant; the
    media walk happens outside it, because a filesystem has no snapshot and the
    walk must not hold a transaction open while it counts directories.
    """
    started = timezone.now()
    until = started
    since = until - timedelta(days=window_days)
    rows = dataset_rows()
    units = _measurement_units(rows, only_tables=tables, only_datasets=datasets)
    table_names = sorted({name for row in units for name in row["tables"]})
    # only the table which physically carries the declared timestamp can answer
    # the growth question; the other tables of a family are measured for size
    time_fields = {name: None for row in units for name in row["tables"]}
    for row in units:
        if row["growth_table"] in time_fields:
            time_fields[row["growth_table"]] = row["time_field"]
    with read_only_report() as enforced:
        measurements = measure_tables(table_names, time_fields, since, until,
                                      with_wal=with_wal)
        undeclared = undeclared_tables()
        postgres = postgresql_facts(with_wal=with_wal)
    estimates = growth_estimates(units, measurements, window_days, horizon_days)
    report = {
        "inventory": {
            "schema_version": 1,
            "declaration_version": DECLARATION_VERSION,
            "declaration_source": "backend/system/retention_datasets.py",
            "generated_at": started.isoformat(),
            "engine": connection.vendor,
            "database": str(_database_name()),
            "window_days": window_days,
            "window_since": since.isoformat(),
            "window_until": until.isoformat(),
            "horizon_days": horizon_days,
            "declared_datasets": len(DATASETS),
            "growing_datasets": sum(1 for dataset in DATASETS
                                    if dataset.growth != GROWTH_BOUNDED),
            "measured_tables": table_names,
            "undeclared_tables": [row["table"] for row in undeclared],
            "undeclared": undeclared,
        },
        "datasets": rows,
        "measurements": measurements,
        "growth": estimates,
        "media": measure_media(include_media),
        "caches": cache_facts(),
        "disk": disk_facts() if include_disk else {},
        "postgresql": postgres,
        "settings": retention_settings(),
        "gates": [{"id": dataset.id, "decision": dataset.decision_gate}
                  for dataset in DATASETS if dataset.decision_gate],
        "provenance": _provenance(enforced),
    }
    return report


def _database_name():
    try:
        return settings.DATABASES["default"]["NAME"]
    except (KeyError, TypeError, AttributeError):
        return None


def _provenance(read_only_enforced):
    """Where every number came from, and what was deliberately not measured.

    The last key is as important as the first: a reader must be able to see the
    edges of the report, or a missing measurement reads as a small one.
    """
    return {
        "declarations": f"system/retention_datasets.py, version "
                        f"{DECLARATION_VERSION}",
        "sizes": "pg_total_relation_size (heap + all indexes + TOAST) per table",
        "rows": "reltuples as the planner's estimate; the window count is "
                "count(*) over the declared time field",
        "growth": f"count(*) and the median inter-arrival of a random sample "
                  f"of at most {GROWTH_SAMPLE_LIMIT} rows of the window; "
                  f"bytes/day is that rate times the current average row size",
        "read_plan": "EXPLAIN (FORMAT JSON) of the window read, so an "
                     "unindexed retention predicate is visible",
        "graph": "Django model metadata (on_delete of every incoming and "
                 "outgoing FK/O2O) plus pg_index and pg_trigger",
        "media": f"os.scandir below each declared storage location, symlinks "
                 f"not followed, {MEDIA_TREE_DEPTH} levels deep, budget of "
                 f"{MEDIA_SCAN_NODE_BUDGET} entries per prefix and "
                 f"{MEDIA_REFERENCE_LIMIT} names per reference set",
        "settings": "django.conf.settings of the running instance",
        "read_only_enforced": read_only_enforced,
        "not_measured": _NOT_MEASURED,
    }


#: what no run of the inventory can answer, named rather than left as an empty
#: space: a reader who cannot see the edges of a report reads a missing
#: measurement as a small one.
_NOT_MEASURED = {
    "heap_index_toast_split": (
        "the per-relation counters of pg_statio_user_tables are cumulative "
        "since the last stats reset and are not a current byte split"),
    "broker_and_result_backend_bytes": (
        "needs a broker round trip; #1500's CLI"),
    "per_table_wal": (
        "pg_wal_bytes() answers cluster-wide since startup, not per table"),
    "media_on_object_storage": (
        "a storage without a filesystem location has no walk; its sources "
        "carry the reason"),
    "deleted_space_reclaim": (
        "DELETE does not return space to the operating system until vacuum, "
        "rewrite or WAL reclaim"),
}


def format_report(report, fmt="text"):
    """Render a report. ``json`` is the machine-readable whole; ``text`` the summary."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True, default=str)
    return _format_text(report)


def _bytes(value):
    if value is None:
        return "—"
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if abs(size) < 1024 or unit == "PiB":
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}PiB"


def _from(measure, key=VALUE, formatter=_bytes):
    """One answer as text: a value which was never measured is a dash."""
    if not isinstance(measure, dict) or not measure.get(MEASURED):
        return "—"
    value = measure.get(key)
    if value is None:
        return "—"
    return formatter(value)


def _count(measure):
    return _from(measure, formatter=lambda value: f"{int(value):,}")


def _format_text(report):
    meta = report["inventory"]
    out = []
    out.extend([
        "MrMap persistent-data inventory (#1498) — READ ONLY, nothing "
        "here deleted or changed",
        f"  declaration   v{meta['declaration_version']} "
        f"({meta['declaration_source']}), schema "
        f"v{meta['schema_version']}",
        f"  generated     {meta['generated_at']}",
        f"  database      {meta['engine']} {report['postgresql'].get('version') or ''}"
        f" ({meta['database']}) role="
        f"{report['postgresql'].get('role') or '—'}",
        f"  window        {meta['window_days']} d "
        f"({meta['window_since']} .. {meta['window_until']}), horizon "
        f"{meta['horizon_days']} d",
        f"  declared      {meta['declared_datasets']} datasets, "
        f"{meta['growing_datasets']} growing, "
        f"{len(meta['measured_tables'])} tables measured",
        "",
        "Growing datasets, ranked by measured growth",
        "",
        f"  {'#':>3}  {'dataset':<32}{'rows':>11}{'total':>9}"
        f"{'rows/24h':>10}{'MB/24h':>9}  owner",
        "  " + "-" * 86,
    ])
    ranked = sorted(report["growth"],
                    key=lambda item: (item["rank"] is None,
                                      item["rank"] or 0, item["id"]))
    for item in ranked:
        answer = report["measurements"].get(item["table"], {})
        rank = item["rank"] if item["rank"] is not None else "—"
        rows_per_day = ("—" if item["rows_per_day"] is None
                        else f"{item['rows_per_day']:.1f}")
        bytes_per_day = ("—" if item["bytes_per_day"] is None
                         else f"{item['bytes_per_day'] / 1048576:.1f}")
        out.append(
            f"  {str(rank):>3}  "
            f"{item['id']:<32}{_count(answer.get('estimated_rows')):>11}"
            f"{_from(answer.get('total_bytes')):>9}"
            f"{rows_per_day:>10}{bytes_per_day:>9}  {item['owner']}")
    out.append("")

    reasons = {}
    for item in report["growth"]:
        if item["window_reason"]:
            reasons.setdefault(item["window_reason"], []).append(item["id"])
    if reasons:
        out.append("Growth not measured, and why (an unknown is not a zero)")
        for reason in sorted(reasons):
            ids = reasons[reason]
            shown = ", ".join(ids[:5]) + (", …" if len(ids) > 5 else "")
            out.append(f"  {reason:<34}{len(ids):>3}  {shown}")
        out.append("")

    media = report["media"]
    out.extend([
        "Media below each declared storage location",
        "",
        f"  {'prefix':<34}{'total':>9}{'referenced':>12}"
        f"{'unreferenced':>13}  scope",
        "  " + "-" * 82,
    ])
    for source in media["sources"]:
        out.append(
            f"  {source['id']:<34}{_from(source['total_bytes']):>9}"
            f"{_from(source['referenced_bytes']):>12}"
            f"{_from(source['unreferenced_bytes']):>13}  "
            f"{source['reference_scope']}")
        for reason in source.get("reasons") or []:
            out.append(f"      ! {reason}")
    out.extend([
        f"  {'total':<34}{_from(media['total_bytes']):>9}"
        f"{_from(media['referenced_bytes']):>12}"
        f"{_from(media['unreferenced_bytes']):>13}"
        f"   ({media['sources_not_measured']} sources unmeasured)",
        f"  undetermined (references whose file the walk did not see): "
        f"{_from(media['undetermined_bytes'])}",
        "",
    ])

    out.append("Disk, caches and PostgreSQL")
    for label, entry in report["disk"].items():
        if entry[MEASURED]:
            out.append(f"  {label:<14}{_bytes(entry[VALUE]):>9} free of "
                       f"{_bytes(entry['total_bytes'])}  inodes "
                       f"{entry['inodes_free']:,}/{entry['inodes_total']:,}")
        else:
            out.append(f"  {label:<14}{'—':>9}  {entry[REASON]}")
    wal = report["postgresql"]["wal_bytes"]
    out.append(f"  wal_bytes   {_from(wal):>9}  "
               f"{wal[REASON] or 'pg_wal_bytes(), cluster-wide since startup'}")
    caches = report["caches"]
    for name, config in caches["caches"].items():
        out.append(f"  cache {name:<9}{str(config['bounded_by'])}  "
                   f"timeout={config['timeout']}")
    out.append(f"  celery results backend={caches['celery_result_backend']} "
               f"expires={caches['celery_result_expires_seconds']}s")
    out.append("")

    undeclared = meta["undeclared_tables"]
    out.append(f"Undeclared tables ({len(undeclared)}) — a table of an "
               f"inventoried app with no declaration")
    if undeclared:
        for row in meta["undeclared"]:
            out.append(f"  {row['table']:<44}{_bytes(row.get('total_bytes')):>9}"
                       f"  rows {row.get('estimated_rows', 0):,}")
    else:
        out.append("  none — every table of an inventoried app is declared")
    out.append("")

    gates = report["gates"]
    out.append(f"Unresolved decisions ({len(gates)}) — no destructive policy "
               f"on these until the named decision is answered (#1497)")
    for gate in gates:
        out.append(f"  {gate['id']:<32}{gate['decision']}")
    out.append("")

    read_only = report["provenance"]["read_only_enforced"]
    out.append("Statements ran in a "
               + ("READ ONLY, REPEATABLE READ transaction."
                  if read_only else
                  "transaction which the backend would not mark READ ONLY "
                  "(inside an existing read-write transaction, e.g. a test); "
                  "nothing in this code path writes either way.")
               + " Heap/index/TOAST split, broker bytes and per-table WAL are "
                 "named in provenance.not_measured.")
    return "\n".join(out)
