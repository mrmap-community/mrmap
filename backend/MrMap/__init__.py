from __future__ import absolute_import

# The canonical application version is the root VERSION file, projected into
# the package by scripts/canonical_version.py (#1579). Imported first, so the
# name VERSION is bound before anything the imports below can pull in - such
# as MrMap.settings, which does `from . import VERSION` - reads the package.
from .version import VERSION  # generated; do not edit
# This will make sure the app is always imported when
# Django starts so that shared_task will use this app.
from .celery import app as celery_app  # noqa

__all__ = ('celery',)


__version__ = VERSION  # synonym kept for compatibility
