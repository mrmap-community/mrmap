from __future__ import absolute_import

# This will make sure the app is always imported when
# Django starts so that shared_task will use this app.
from .celery import app as celery_app  # noqa

__all__ = ('celery',)

__version__ = '0.1.0'
VERSION = __version__  # synonym