from __future__ import absolute_import

import logging
import os
import sys

from celery import Celery
from celery.signals import (after_setup_logger, celeryd_after_setup,
                            task_postrun, task_prerun)
from django.db import close_old_connections, connections

# the "celery" tree of the LOGGING config of MrMap/settings.py, so the line
# below reads like every other line of a worker start-up
logger = logging.getLogger("celery")


# Helper functions
def is_celery_process(*keywords: str) -> bool:
    args = " ".join(sys.argv)
    return "celery" in args and all(word in args for word in keywords)


def is_this_a_celery_worker_process():
    return is_celery_process("worker")


def is_this_a_celery_beat_process():
    return is_celery_process("beat")


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "MrMap.settings")


app = Celery("MrMap")

# Using a string here means the worker will not have to
# pickle the object when using Windows.
app.config_from_object("django.conf:settings", namespace="CELERY")


@after_setup_logger.connect
def config_loggers(*args, **kwargs):
    from logging.config import dictConfig

    from django.conf import settings

    dictConfig(settings.LOGGING)


@task_prerun.connect
def close_connections_before_task(*args, **kwargs):
    close_old_connections()


@task_postrun.connect
def close_connections_after_task(*args, **kwargs):
    connections.close_all()


app.autodiscover_tasks()


# What a worker must never do in silence is accept work it cannot reach: a
# message published to a queue without a consumer is neither refused nor
# lost, it waits unread while the job it belongs to stalls (ten hours of it
# in the stranded harvest of #1038). The stock worker therefore starts
# without -Q and consumes everything MrMap declares; a worker which was
# started with a narrower list says so at start-up (#1040).
def queues_without_consumer(celery_app=app):
    """The declared queues which the starting worker process does not consume.

    ``celeryd_after_setup`` fires after the ``-Q`` option has been applied,
    so ``amqp.queues.consume_from`` answers what the worker really reads and
    the ``task_queues`` of the settings answer what the app routes to. A
    worker started without ``-Q`` consumes every declared queue and this
    returns empty.
    """
    declared = {queue.name for queue in celery_app.conf.task_queues}
    return sorted(declared - set(celery_app.amqp.queues.consume_from))


def tasks_routed_to(queue_name, celery_app=app):
    """The task names the app publishes to ``queue_name``.

    This project routes through the ``queue=`` of the task declarations
    (there are no ``CELERY_TASK_ROUTES``); tasks without one are published
    to the default queue.
    """
    names = sorted(
        name for name, task in celery_app.tasks.items()
        if getattr(task, "queue", None) == queue_name)
    if queue_name == celery_app.conf.task_default_queue:
        names.append("(and every task without a queue of its own)")
    return names


@celeryd_after_setup.connect
def check_consumed_queues(sender=None, **kwargs):
    """Logs every queue the app declares but this worker was started without.

    A deployment which runs a split fleet - one worker per group of queues,
    each with its own ``-Q`` - sees this line at every worker start and
    knows the split is as intended; for a single worker it names the
    misconfiguration whose work would otherwise wait unread (#1040).
    """
    missing = queues_without_consumer()
    if not missing:
        return
    logger.error(
        "worker %s does not consume %d of the queues the app declares: %s. "
        "Messages published to these queues are never read; this is right "
        "only if another worker consumes them (#1040).",
        sender, len(missing),
        "; ".join(
            "'%s' carries: %s" % (
                name, ", ".join(tasks_routed_to(name))
                or "(nothing routes to it yet)")
            for name in missing))
