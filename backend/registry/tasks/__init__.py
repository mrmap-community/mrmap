# The task registration of the app: the worker imports the "tasks" module of
# every installed app, and this package is where that import arrives. A task
# module missing from this list is never imported by the worker, and every
# message naming one of its tasks is then discarded as unregistered (#1199).
# tests/django/test_celery_task_registration.py guards this list; the task
# modules of this package which are not named here are listed there with the
# import which reaches the worker instead.
from .alerts import *  # noqa
from .conformity import *  # noqa
from .harvest import *  # noqa
from .monitoring import *  # noqa
from .security import *  # noqa
