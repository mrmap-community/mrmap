"""Test-time SQL regression guards for the Celery tasks of the deployment (#1395).

The static audit ``docs/source/development/celery-task-orm-audit.rst`` names the
query paths a task family pays; this module turns those findings into durable
guards which run with the Django test suite. It answers four questions about a
task body, never about its wall time:

*   **How many statements?** `assertQueryCountIndependent` measures the same
    run at growing fixture sizes (0/1/10/100+ shapes) and asserts the statement
    count does not grow with the rows - or grows only with a stated per-row
    allowance, which is how a deliberately per-record transaction (#895) stays
    allowed while an accidental per-row read fails.
*   **Which statement repeats?** `assertNoNPlusOne` fingerprints every captured
    statement (literals, parameter lists and bulk VALUES folded away) and flags
    any fingerprint which appears more often than sanctioned. This catches the
    repeated *write* of an UPDATE-in-a-loop as well as the repeated read, and it
    does not care whether a bulk_create turned the same work into one statement.
*   **How wide is the plan?** `assertStatementTouchesNo` forbids a task plan
    from reading tables a UI-oriented prefetch would pull in - the rule that a
    smaller task plan must not buy its lower query count with
    ``prefetch_whole_*`` breadth (#1397).
*   **How many rows does it read?** `assertRowsReadBound` measures the rows
    every captured SELECT actually returned, straight from the cursor. This
    is the guard a query-count assertion cannot be: a huge unbounded prefetch
    keeps the statement count flat while it drains a whole backlog into
    memory, and it fails here, not there.

Scope rules honored here (#1395): everything measures *statements, plans and
rows*, never runtime. There is no p95/p99 benchmark, no worker-slot profiling
and no CI duration regression detection - that is V2 (#1396), and the existing
#1330/#1326 instrumentation is untouched by anything in this file.

Safety notes for the EXPLAIN helpers:

*   Only ``SELECT`` statements are ever re-executed. `explain_select` refuses
    anything else, because ``EXPLAIN ANALYZE`` runs the statement.
*   ``SELECT ... FOR UPDATE`` is also refused by `explain_select`: EXPLAIN
    ANALYZE would take the row locks for real. Locked reads are guarded by
    statement *order* and count, not by EXPLAIN.
*   The captured SQL of Django's ``CaptureQueriesContext`` is usable for the
    *plan* (EXPLAIN without ANALYZE); it is not a faithful re-execution -
    rendered LIMIT/OFFSET parameters do not survive - so row measurement
    reads the cursor's row counts instead of replaying statements.
"""
import re
from collections import Counter

from django.db import connections
from django.test.utils import CaptureQueriesContext

# the main table a statement reads or writes - same attribution as
# tests_query_performance uses to name the table which grows
TABLE_RE = re.compile(
    r'(?:FROM|JOIN|INSERT INTO|UPDATE|DELETE FROM)\s+"?([a-zA-Z_0-9]+)"?',
    re.IGNORECASE)

# every table a statement names anywhere, for the forbidden-table guard
ANY_TABLE_RE = TABLE_RE

_STRING_LITERAL_RE = re.compile(r"'(?:[^']|'')*'")
_NUMBER_RE = re.compile(r'\b\d+\b')
# an IN list of placeholders of any length is one fingerprint
_IN_LIST_RE = re.compile(r'\bin \(\s*\?\s*(?:,\s*\?\s*)*\)', re.IGNORECASE)
# a bulk INSERT ... VALUES (?), (?), ... is one statement regardless of rows;
# the marker keeps it a different shape from a single-row VALUES, whose row
# count of one is not the same plan to repeat
_VALUES_RE = re.compile(r'values\s*\((?:[^()]|\([^()]*\))*\)\s*(?:,\s*\((?:[^()]|\([^()]*\))*\))+',
                        re.IGNORECASE)


def normalize_sql(sql):
    """The fingerprint of a statement: its shape without its data.

    Two executions of the same ORM read differ only in the literals of their
    parameters and the length of their IN/VALUES lists; after folding those, a
    fingerprint which repeats is a statement executed once per row.
    """
    normalized = _STRING_LITERAL_RE.sub('?', sql)
    normalized = _NUMBER_RE.sub('?', normalized)
    normalized = _IN_LIST_RE.sub('in (?)', normalized)
    # the "many" marker separates a multi-row VALUES from a single-row one:
    # the same INSERT shape repeated per row is the N+1 write, while one
    # bulk INSERT of any size is a single statement - the row count of a
    # single-row VALUES is a different plan to repeat and stays visible
    normalized = _VALUES_RE.sub('values (?) many', normalized)
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized.strip().lower()


def fingerprint(queries_or_sql):
    """Fingerprint of one query dict or sql string, or of every query of a list.

    Answers one string for one input and a list for a list, so family tests can
    read naturally either way.
    """
    if isinstance(queries_or_sql, str):
        return normalize_sql(queries_or_sql)
    if isinstance(queries_or_sql, dict):
        return normalize_sql(queries_or_sql['sql'])
    if isinstance(queries_or_sql, CaptureQueriesContext):
        return [normalize_sql(q['sql']) for q in queries_or_sql.captured_queries]
    if isinstance(queries_or_sql, list):
        return [normalize_sql(q['sql']) if isinstance(q, dict) else normalize_sql(q)
                for q in queries_or_sql]
    raise TypeError(queries_or_sql)


def table_of(sql):
    """The main table a statement names, or None when it names none."""
    tables = ANY_TABLE_RE.findall(sql)
    return tables[0] if tables else None


def table_counter(queries):
    """Count the captured statements by the main table they touch.

    Failure messages name the table which is queried over and over, not just a
    number (the pattern of ``tests_query_performance.table_counter``).
    """
    captured = _as_queries(queries)
    counter = Counter()
    for query in captured:
        counter[table_of(query['sql']) or query['sql'][:32]] += 1
    return counter


def write_counter(queries):
    """Count INSERT/UPDATE/DELETE statements per table they write."""
    captured = _as_queries(queries)
    counter = Counter()
    for query in captured:
        sql = query['sql'].lstrip().lower()
        verb = (sql.split(None, 1)[0] if sql else '')
        if verb in ('insert', 'update', 'delete'):
            counter[f"{verb} {table_of(query['sql'])}"] += 1
    return counter


def statements_of(queries, verb=None, table=None):
    """The queries (in captured order) matching a verb and/or a main table.

    ``verb`` is 'select', 'insert', 'update' or 'delete'; statements whose verb
    prefix is unknown never match a verb. Used for order assertions such as the
    process->row lock order of #1263.
    """
    captured = _as_queries(queries)
    matched = []
    for query in captured:
        sql = query['sql']
        if verb and not sql.lstrip().lower().startswith(verb):
            continue
        if table and table_of(sql) != table:
            continue
        matched.append(query)
    return matched


def first_index_of(queries, verb=None, table=None, contains=None):
    """Index of the first captured statement matching the criteria, else None.

    ``contains`` is a case-insensitive substring of the sql.
    """
    captured = _as_queries(queries)
    needle = contains.lower() if contains else None
    for index, query in enumerate(captured):
        sql = query['sql']
        if verb and not sql.lstrip().lower().startswith(verb):
            continue
        if table and table_of(sql) != table:
            continue
        if needle and needle not in sql.lower():
            continue
        return index
    return None


def _as_queries(queries):
    """Accept a CaptureQueriesContext, a list of dicts or a list of strings."""
    if isinstance(queries, CaptureQueriesContext):
        return list(queries.captured_queries)
    if queries and isinstance(queries[0], str):
        return [{'sql': sql} for sql in queries]
    return list(queries)


def plan_nodes(plan):
    """Every node of an EXPLAIN JSON plan tree, depth first."""
    pending = [plan]
    while pending:
        node = pending.pop()
        yield node
        pending.extend(node.get('Plans', []))


class SqlGuardMixin:
    """Query-count, duplicate-SQL, plan-width and plan-shape assertions.

    Mixed into any TestCase. Every guard takes a *runnable* - a zero-argument
    callable which performs exactly the work to measure - so the fixture setup
    which builds the rows is outside the measured block by construction: the
    same comparable fixture data exists before the statements are counted.

    Cardinality fixtures: seed the fixture with 0/1/10/100+ related entities
    and measure the same runnable at each size (see `assertQueryCountIndependent`
    for the growing-shape contract); a constant count is what the task families
    of #1392/#1393/#1394 have to keep.
    """

    def capture(self, run):
        """Run `run` while capturing the statements of the default connection.

        Returns:
            tuple: what ``run`` answered, and the CaptureQueriesContext
        """
        with CaptureQueriesContext(connections['default']) as context:
            result = run()
        return result, context

    def statements_of(self, queries, verb=None, table=None):
        """Captured statements matching a verb and/or a main table, in order."""
        return statements_of(queries, verb=verb, table=table)

    def first_index_of(self, queries, verb=None, table=None, contains=None):
        """Index of the first captured statement matching the criteria, else None."""
        return first_index_of(queries, verb=verb, table=table, contains=contains)

    def assertQueryCountIndependent(self, sizes, seed, run, per_row=0, extra=0,
                                    label=''):
        """The statement count of `run` does not grow with the seeded rows.

        Args:
            sizes: ascending fixture sizes to measure at, e.g. (1, 10, 100)
            seed: ``seed(size)`` builds the fixture for that size; it runs
                before the measured block, so its own writes are not counted
            run: the zero-argument callable to measure at each size
            per_row: allowed statement growth per seeded row - the honest way
                to allow a deliberate per-record transaction (a locked read
                and its commit is one sanctioned statement per record, #895)
                while an accidental per-row read of anything else fails
            extra: constant slack on top of the smallest measurement
            label: what these numbers mean, for the failure message

        Returns:
            dict: the measured ``{size: statement count}`` for the test log.
        """
        measured = {}
        counters = {}
        for size in sizes:
            seed(size)
            _, context = self.capture(run)
            measured[size] = len(context.captured_queries)
            counters[size] = table_counter(context)
        base = measured[sizes[0]]
        for size in sizes:
            allowed = base + per_row * size + extra
            self.assertLessEqual(
                measured[size], allowed,
                msg=(f"{label or 'the measured run'} costs {measured[size]} "
                     f"statements at {size} seeded rows but only {allowed} are "
                     f"allowed (measured {measured}; tables at the largest "
                     f"size: {dict(counters[sizes[-1]])})"))
        return measured

    def assertNoNPlusOne(self, run, sanctioned=None, exclude=None,
                         max_repeats=1, label=''):
        """No statement fingerprint repeats more often than sanctioned.

        This is the guard which detects an intentionally introduced N+1
        (#1395 acceptance): the fingerprint of `normalize_sql` folds literals
        and parameter lists away, so ``SELECT ... WHERE id = 1`` and
        ``WHERE id = 2`` are one fingerprint - once per row is a violation.
        A statement legitimately run once per record (the locked per-record
        read of the import, #895) is allowed by naming it in `sanctioned`: a
        mapping of sql-substring to the amount of repeats which is exactly the
        number of records - an allowance which grows only with the rows it
        names, never a free pass.

        ``exclude`` names sql-substrings of statements the whole task base
        pays per record by contract - the ``simple_history`` writes of every
        saved row are the standing example - and are left out of the
        comparison entirely. Name them narrowly: an exclude which swallows
        the statement under test makes the guard meaningless.

        Returns:
            the CaptureQueriesContext, for further assertions by the caller.
        """
        _, context = self.capture(run)
        counts = Counter(fingerprint(context))
        violations = {}
        for shape, count in counts.items():
            if any(needle in shape for needle in (exclude or [])):
                continue
            allowed = max_repeats
            for needle, amount in (sanctioned or {}).items():
                if needle in shape:
                    allowed = max(allowed, amount)
            if count > allowed:
                violations[shape] = (count, allowed)
        report = {shape[:160]: (seen, allowed)
                  for shape, (seen, allowed) in violations.items()}
        self.assertFalse(
            violations,
            msg=(f"{label or 'the measured run'} repeats statements "
                 f"(shape, seen, allowed): {report} "
                 f"tables: {dict(table_counter(context))}"))
        return context

    def assertStatementTouchesNo(self, run, forbidden_tables, label=''):
        """No captured statement names any forbidden table.

        The narrow-plan rule of #1397: a task plan may not reach the breadth of
        the UI reads (``prefetch_whole_*`` pulls contacts, styles, time extents
        and remote metadata for the API screens). A family test names the
        tables of the relations its config does not use; if a future change
        buys a lower query count with a broader prefetch, this fails there.
        """
        _, context = self.capture(run)
        offenders = []
        for query in context.captured_queries:
            named = {match.lower() for match in ANY_TABLE_RE.findall(query['sql'])}
            hit = named & {table.lower() for table in forbidden_tables}
            if hit:
                offenders.append((sorted(hit), query['sql'][:160]))
        self.assertFalse(
            offenders,
            msg=(f"{label or 'the measured run'} touches forbidden tables: "
                 f"{offenders} - a task plan stays narrow and does not pay a "
                 f"UI-oriented prefetch"))
        return context

    def explain_select(self, sql, analyze=False):
        """The EXPLAIN plan tree of a captured SELECT, executed safely.

        Plans without ANALYZE: the plan shape (scan type, index names) is
        decided by the planner without running the read - and the captured
        text is not a faithful re-execution anyway (rendered LIMIT/OFFSET
        parameters do not survive Django's query rendering), which is why
        row counting goes through `rows_of_selections` instead.

        Refuses anything but a plain SELECT as a standing precaution: with
        ``analyze=True`` EXPLAIN runs the statement.
        """
        stripped = sql.lstrip().lower()
        if not stripped.startswith('select'):
            raise ValueError('explain_select only explains SELECT statements')
        if 'for update' in stripped or 'for share' in stripped:
            raise ValueError('explain_select never explains locking reads; '
                             'guard those by statement order instead')
        with connections['default'].cursor() as cursor:
            cursor.execute(
                'EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ' + sql
                if analyze else 'EXPLAIN (BUFFERS, FORMAT JSON) ' + sql)
            return cursor.fetchone()[0][0]['Plan']

    def rows_of_selections(self, run):
        """Run `run` and answer what each SELECT actually returned.

        The row counts are read from the cursor after each execute - the
        number of rows the statement handed to the task, which is the memory
        question #1395 asks. (EXPLAIN ANALYZE over the captured text would
        re-execute a *different* statement, because a sliced queryset's LIMIT
        is not part of Django's rendered SQL.)

        Returns:
            tuple: what ``run`` answered, the CaptureQueriesContext and the
            list of ``(sql, row_count)`` per SELECT, in captured order.
        """
        rows = []

        def count_selections(execute, sql, params, many, context):
            # the innermost executor is Django's own `_execute`, which ignores
            # the wrapper args beyond params - forward all four positionally
            cursor = execute(sql, params, many, context)
            if sql.lstrip().lower().startswith('select'):
                rows.append((sql, cursor.rowcount))
            return cursor

        connection = connections['default']
        with connection.execute_wrapper(count_selections):
            result, context = self.capture(run)
        return result, context, rows

    def assertRowsReadBound(self, run, max_rows, per_statement=True, label=''):
        """No captured SELECT returns more rows than the bound.

        This is why a huge unbounded prefetch does not pass simply because
        the statement count fell: draining 100 backlog rows (or a whole
        deployment's worth of lookup rows) through one statement still
        returns 100 rows to the task; a plan which reads them per-row fails
        the count guard above instead.
        """
        _, context, rows = self.rows_of_selections(run)
        violations = []
        total = 0
        for sql, row_count in rows:
            total += row_count
            if per_statement and row_count > max_rows:
                violations.append((row_count, sql[:160]))
        if not per_statement and total > max_rows:
            violations.append((total, f'{len(rows)} statements'))
        self.assertFalse(
            violations,
            msg=(f"{label or 'the measured run'} returns more rows than bounded "
                 f"({max_rows}): {violations} - a prefetch which drains whole "
                 f"tables is not an optimization (#1397)"))
        return context

    def assertPlanUsesIndex(self, sql, table, index=None, label=''):
        """The plan of the captured SELECT reads ``table`` through an index.

        Every plan node which scans ``table`` must be an index scan (or a
        bitmap heap scan whose child is a bitmap index scan); with ``index``
        given, the named index has to be among them. This is how a checklist
        item like "the duplicate guard reads ["job_id","requested_url"]"
        becomes an assertion instead of a hope.

        ``sql`` must be a plain SELECT - see `explain_select` for why.
        """
        plan = self.explain_select(sql)
        scans = [node for node in plan_nodes(plan)
                 if node.get('Relation Name') == table]
        self.assertTrue(scans, msg=f'nothing in the plan reads {table}: {sql[:160]}')
        used_indexes = set()
        for node in scans:
            node_type = node.get('Node Type')
            if node_type in ('Index Scan', 'Index Only Scan'):
                used_indexes.add(node.get('Index Name'))
            elif node_type == 'Bitmap Heap Scan':
                children = [
                    child for child in node.get('Plans', [])
                    if child.get('Node Type') == 'Bitmap Index Scan']
                self.assertTrue(
                    children,
                    msg=(f"{label or 'the plan'} reads {table} with a bitmap "
                         f"heap scan without a bitmap index scan: {sql[:160]}"))
                used_indexes.update(child.get('Index Name') for child in children)
            else:
                self.fail(
                    f"{label or 'the plan'} reads {table} with a {node_type}, "
                    f"expected an index scan: {sql[:160]}")
        if index is not None:
            matched = any(name and index in name for name in used_indexes)
            self.assertTrue(
                matched,
                msg=(f"{label or 'the plan'} does not use the index {index!r} "
                     f"on {table}; used: {sorted(str(n) for n in used_indexes)}"))
