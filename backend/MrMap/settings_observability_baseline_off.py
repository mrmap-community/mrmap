"""Settings of the diagnostics-off arm of the #1777 observability benchmark.

Imported only by ``scripts/observability_bench.py``, which boots the web tier of
its own disposable stack with ``DJANGO_SETTINGS_MODULE`` pointing here (compose
sets it, and ``MrMap.wsgi`` reads it with ``setdefault``, so the value wins). It
is not a deployment option: nothing in the shipped compose files names it.

One difference from ``MrMap.settings``, and the reason the module exists:
``system.logging.middleware.LogSlowRequestsMiddleware`` is removed from the
middleware chain. That middleware is the legacy HTTP detector of the stack - it
wraps every request in a ``connection.execute_wrapper``, copies every statement
and its parameters, and hands the list to the logger when the request crosses
the threshold - and there is no knob which turns the capture off, only
``MRMAP_SLOW_REQUEST_THRESHOLD_MS`` which decides what is *reported* after the
capture already happened. So a "diagnostics off" reading of the web tier which
booted the shipped chain would be measuring a stack whose detector still runs,
and the paired number #1780 compares against would be wrong in the direction
that flatters the detector.

Nothing else is changed. In particular the Celery-side knobs of #1389/#1391/
#1392/#1401 are opt-in settings which that arm's *environment* sets, and this
module sets none of them: an arm is defined by its own definition in
``docs/source/development/evidence/observability-1777-arms.json``, and a
settings module which quietly enabled something would break that.
"""

from MrMap.settings import *  # noqa: F401,F403  (the arm differs by one line)

LEGACY_HTTP_DETECTOR = "system.logging.middleware.LogSlowRequestsMiddleware"

MIDDLEWARE = [entry for entry in MIDDLEWARE if entry != LEGACY_HTTP_DETECTOR]  # noqa: F405

#: what this module promises about itself, so a run can be read without opening
#: this file and a reviewer can see at a glance that the removal is the whole
#: difference. ``scripts/observability_bench.py verify`` has nothing to check
#: against here - the middleware either ran or it did not - but a manifest
#: which records the module name is the evidence that it was asked not to.
MRMAP_OBSERVABILITY_BASELINE_OFF = LEGACY_HTTP_DETECTOR
