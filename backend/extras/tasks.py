from collections import OrderedDict
from contextlib import contextmanager
from logging import Logger

from celery import Task
from celery.signals import task_postrun, task_prerun
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.db import (DEFAULT_DB_ALIAS, DatabaseError, InterfaceError,
                       connections)
from django.db.utils import load_backend
from rest_framework.test import APIRequestFactory
from simple_history.models import HistoricalRecords

logger: Logger = settings.ROOT_LOGGER


@task_prerun.connect
def set_current_user(*args, **kwargs):
    try:
        http_request = kwargs["kwargs"].get("http_request", None)
        if http_request:
            dummy_request = None
            if http_request['method'].lower() == 'get':
                dummy_request = APIRequestFactory().get(
                    path=http_request['path'],
                    data=http_request['data'],
                )
            elif http_request['method'].lower() == 'post':
                dummy_request = APIRequestFactory().post(
                    path=http_request['path'],
                    data=http_request['data'],
                    content_type=http_request['content_type']
                )
            if http_request.get('user_pk', None):
                try:
                    dummy_request.user = get_user_model(
                    ).objects.get(pk=http_request['user_pk'])
                except ObjectDoesNotExist:
                    pass
            if dummy_request and (not hasattr(dummy_request, 'query_params') or not dummy_request.query_params):
                dummy_request.query_params = OrderedDict()
            HistoricalRecords.context.request = dummy_request
    except Exception as e:
        logger.exception(e, stack_info=True, exc_info=True)


@task_postrun.connect
def reset_current_user(*args, **kwargs):
    if hasattr(HistoricalRecords.context, "request"):
        del HistoricalRecords.context.request


def singleton_lock_id(name):
    """The key the singleton of one task name is locked under.

    Args:
        name: the name of the task, which is what identifies it to celery

    Returns:
        str: the text the advisory lock of that task is derived from
    """
    return f"singleton:{name}"


def singleton_connection():
    """The database session a singleton lock is taken on.

    A run reports its state to celery on the connection of the task, and celery
    closes those connections after every run (`MrMap/celery.py`), so the lock
    needs a session of its own. That session must also end with the run, which a
    pooled one does not: it is given back to the pool for the next borrower. So
    this asks for the default database without its pooling - as the celery
    processes of this project already run it, where pooling is off deliberately.

    Returns:
        the wrapper of one new connection of the default database
    """
    database = connections.settings[DEFAULT_DB_ALIAS]
    options = {
        key: value
        for key, value in (database.get("OPTIONS") or {}).items()
        if key != "pool"
    }
    backend = load_backend(database["ENGINE"])
    return backend.DatabaseWrapper(
        {**database, "OPTIONS": options}, DEFAULT_DB_ALIAS)


@contextmanager
def singleton_lock(name):
    """Hold the singleton lock of `name` and answer whether it was taken.

    The lock is an advisory lock of one dedicated database session, so every fire
    of the task asks the same database - in this worker process or in another one -
    and a holder which dies, be it killed, crashed or a network which goes away,
    is answered by the postmaster itself: it ends the session and with it the
    lock. A lock which only expires by a clock did neither (#837): its timeout
    equalled the beat interval, so a run which outlived that interval met the next
    fire with a free lock and started a second concurrent run of itself.

    The number to lock is `hashtext` of that text, so two task names which that
    hash puts on the same number share one lock: such a collision only ever
    skips a fire, it never lets two runs of one task start.

    Args:
        name: the name of the task which wants to be alone

    Yields:
        bool: whether this call holds the lock; the body must not run if not
    """
    lock_id = singleton_lock_id(name)
    connection = singleton_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_try_advisory_lock(hashtext(%s))", [lock_id])
            if not cursor.fetchone()[0]:
                yield False
                return
        try:
            yield True
        finally:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT pg_advisory_unlock(hashtext(%s))", [lock_id])
            except (DatabaseError, InterfaceError) as error:
                # the session of this run is gone - which is also how its lock is
                # gone, so nothing waits for this run to unlock and this is told
                # instead of raised on top of a run which has already happened
                logger.warning(
                    f"Singleton lock '{lock_id}' could not be unlocked: {error}")
    finally:
        connection.close()


class SingletonTask(Task):
    """Celery task basis which runs at most one instance of itself at a time.

    A fire which finds the lock taken does not run its body a second time
    alongside the first one: it is logged and answered as skipped, which is what
    the beat schedule of a task which sometimes runs longer than its interval
    needs. The lock belongs to the run which holds it and not to a clock, so a
    long run is never interrupted by a second one and a dead run never blocks a
    later one (#837).
    """

    def __call__(self, *args, **kwargs):
        with singleton_lock(self.name) as acquired:
            if not acquired:
                msg = f"Task {self.name} skipped: another instance is running"
                logger.info(msg)
                self.update_state(state="SKIPPED", meta={"info": msg})
                return msg

            self.update_state(state="STARTED", meta={"info": "Task started"})
            # Hier wird die normale run-Methode aufgerufen
            return super().__call__(*args, **kwargs)
