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


def is_this_a_celery_process():
    for arg in sys.argv:
        return 'celery' in arg
    return False
