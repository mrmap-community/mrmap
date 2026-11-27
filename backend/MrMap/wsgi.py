"""
WSGI config for MrMap project.
It exposes the WSGI callable as a module-level variable named ``application``.
For more information on this file, see
https://docs.djangoproject.com/en/2.1/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "MrMap.settings")

application = get_wsgi_application()

# The telemetry of the HTTP tier is initialized here and in the ``post_fork`` hook
# of ``gunicorn.conf.py``, and the two are not in conflict: the lifecycle creates a
# provider at most once per process and replaces, by pid, what a forked child
# inherited. This line is therefore what covers a WSGI server without Gunicorn and
# the ``--preload`` shape; the hook is what covers the fork. One owner either way,
# and nothing at all while ``MRMAP_OTEL_MODE`` is off (#1779).
from MrMap.telemetry import lifecycle  # noqa: E402

lifecycle.initialize_for_process(role=lifecycle.ROLE_HTTP)
