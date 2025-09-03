from __future__ import absolute_import

import os
import sys

from celery import Celery
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "MrMap.settings")
app = Celery("MrMap")


# Using a string here means the worker will not have to
# pickle the object when using Windows.
app.config_from_object("django.conf:settings")
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)


def is_celery_process(*keywords: str) -> bool:
    args = " ".join(sys.argv)
    return "celery" in args and all(word in args for word in keywords)


def is_this_a_celery_worker_process():
    return is_celery_process("worker")


def is_this_a_celery_beat_process():
    return is_celery_process("beat")
