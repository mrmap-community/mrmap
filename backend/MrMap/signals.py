from celery import states
from celery.signals import before_task_publish
from django.conf import settings
from MrMap.celery import app as celery_app

db_result_backend = None
registered_task_names = celery_app.tasks.keys()


def create_task_result_on_publish(sender=None, headers=None, **kwargs):  # noqa: ARG001
    """
    This is a workaround for an issue where django-celery-results
    is not adding PENDING tasks to the database.

    # ref: https://github.com/celery/django-celery-results/issues/286
    """

    if "task" not in headers or not db_result_backend or sender not in registered_task_names:
        return

    # essentially transforms a single-level of the headers dictionary
    # into an object with properties
    request = type('request', (object,), headers)

    db_result_backend.store_result(
        headers["id"],
        None,
        states.PENDING,
        traceback=None,
        request=request,
    )


celery_backend = getattr(settings, 'CELERY_RESULT_BACKEND', '')
is_django_celery_installed = 'django_celery_results' in getattr(
    settings, 'INSTALLED_APPS', [])

if is_django_celery_installed and celery_backend == 'django-db':
    # We are good to import DatabaseBackend
    from django_celery_results.backends.database import DatabaseBackend

    db_result_backend = DatabaseBackend(celery_app)
    # And now register the signal
    before_task_publish.connect(
        create_task_result_on_publish, dispatch_uid='create_task_result_on_publish')
