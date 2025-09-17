from __future__ import absolute_import

import os
import sys

from celery import Celery
from celery.signals import after_setup_logger, task_postrun, task_prerun
from django.db import close_old_connections, connections


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
