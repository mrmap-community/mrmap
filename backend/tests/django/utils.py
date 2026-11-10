from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from celery import Celery
from celery.app.trace import build_tracer


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
