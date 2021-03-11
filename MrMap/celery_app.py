"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 12.08.19

"""

from __future__ import absolute_import
import os

from celery import Celery
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MrMap.settings')
app = Celery('MrMap')

# Using a string here means the worker will not have to
# pickle the object when using Windows.
app.config_from_object('django.conf:settings')
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

app.conf.beat_scheduler = settings.CELERY_BEAT_SCHEDULER

@app.task(bind=True)
def debug_task(self):
    print('Request: {0!r}'.format(self.request))


def get_number_active_workers():
    """ Returns the amount of current celery workers

    Returns:
         active_workers (int):
    """
    i = app.control.inspect()
    d = i.active()
    try:
        e = [v for k, v in d.items()][0]
        active_workers = len(e)
    except IndexError:
        active_workers = 0
    return active_workers
