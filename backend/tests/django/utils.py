import re
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from celery import Celery
from celery.app.trace import build_tracer
from django.db import connection
from django.test.utils import CaptureQueriesContext


class MockResponse:

    def __init__(self, content, status_code=200, elapsed=timedelta(seconds=1),
                 url="", headers=None):
        self.status_code = status_code
        self.elapsed = elapsed
        self.url = url
        # a real requests.Response always answers its headers; the code under
        # test reads the content type out of them, so the mock carries them
        # too - empty by default, which reads as an unknown content type
        self.headers = headers or {}

        if isinstance(content, Path):
            in_file = open(content, "rb")
            self.content: bytes = in_file.read()
            in_file.close()
            try:
                self.text: str = self.content.decode("UTF-8")
            except UnicodeDecodeError:
                self.text = ""

        if isinstance(content, str):
            self.text: str = content
            self.content: bytes = content.encode("UTF-8")

    @property
    def ok(self):
        return self.status_code < 400 if self.status_code else False


class WorkerRunMixin:
    """Answers tasks the way a worker does, so their signals are really sent.

    What a task reports about its progress runs in the signal handlers which
    celery's tracer sends while the task is answered (`notify/tasks.py`), so a
    test which wants those reports has to go through the tracer instead of
    calling the handlers with hand made arguments.

    The app is of its own and its result backend is celery's in-process one:
    no broker is needed to answer a task, and the Redis result backend of the
    deployment (#1178) must not be reached by accident from here either.
    """

    def setUp(self):
        super().setUp()
        self.app = Celery('worker-run-test', set_as_current=False)
        self.addCleanup(self.app.close)
        self.app.conf.result_backend = 'cache+memory://'
        self.task_id = str(uuid4())

    def task(self, function, **options):
        task = self.app.task(shared=False, **options)(function)
        task._backend = self.app.backend
        return task

    def answer(self, task, task_id=None, task_kwargs=None):
        """Run `task` once, through the same tracer a worker uses."""
        request = {'id': task_id or self.task_id}
        trace = build_tracer(task.name, task, app=self.app)
        return trace(task_id or self.task_id, (), task_kwargs or {}, request)


# every table a statement names in a FROM or JOIN clause - the same shape
# `tests_query_performance.py` reads out of endpoint queries, here applied to
# the statement of one queryset
QUERY_TABLE_RE = re.compile(
    r'(?:FROM|JOIN)\s+"?([a-zA-Z_0-9]+)"?', re.IGNORECASE)


class QueryPlanMixin:
    """Measure what a call answers and which tables it reads to answer it.

    The query-plan methods of #1397 (`docs/source/development/
    queryset-manager-conventions.rst`) promise two things a plain equality
    test cannot see: that the call answers its rows with a stated number of
    statements no matter how much data has accumulated around the row, and
    that it reads exactly the relations its plan names. `measure` answers the
    call and the statements it executed; `tables_read` names the tables of a
    statement, so a red test points at the table that crept into the plan
    instead of only complaining about a number. #1395 builds its repeatable
    query-count and bound tests on this helper.
    """

    def measure(self, function, *args, **kwargs):
        """Call ``function`` and answer ``(result, list of SQL statements)``."""
        with CaptureQueriesContext(connection) as context:
            result = function(*args, **kwargs)
        return result, [q['sql'] for q in context.captured_queries]

    @staticmethod
    def tables_read(*sqls):
        """The set of tables the given statements read (FROM and JOIN)."""
        return {
            table
            for sql in sqls
            for table in QUERY_TABLE_RE.findall(sql)
        }
