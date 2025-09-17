from logging import Logger
from typing import OrderedDict

from celery import Task
from celery.signals import task_postrun, task_prerun
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from rest_framework.test import APIRequestFactory
from simple_history.models import HistoricalRecords

logger: Logger = settings.ROOT_LOGGER


@task_prerun.connect
def set_current_user(*args, **kwargs):
    try:
        http_request = kwargs["kwargs"].get("http_request", None)
        if http_request:
            dummy_request = None
            if http_request['method'].lower() == 'get':
                dummy_request = APIRequestFactory().get(
                    path=http_request['path'],
                    data=http_request['data'],
                )
            elif http_request['method'].lower() == 'post':
                dummy_request = APIRequestFactory().post(
                    path=http_request['path'],
                    data=http_request['data'],
                    content_type=http_request['content_type']
                )
            if http_request.get('user_pk', None):
                try:
                    dummy_request.user = get_user_model(
                    ).objects.get(pk=http_request['user_pk'])
                except ObjectDoesNotExist:
                    pass
            if dummy_request and (not hasattr(dummy_request, 'query_params') or not dummy_request.query_params):
                dummy_request.query_params = OrderedDict()
            HistoricalRecords.context.request = dummy_request
    except Exception as e:
        logger.exception(e, stack_info=True, exc_info=True)


@task_postrun.connect
def reset_current_user(*args, **kwargs):
    if hasattr(HistoricalRecords.context, "request"):
        del HistoricalRecords.context.request


class SingletonTask(Task):
    """
    Celery Task Basis, der sicherstellt, dass nur eine Instanz gleichzeitig läuft.
    """

    lock_timeout = 300  # Sekunden

    def __call__(self, *args, **kwargs):
        lock_id = f"singleton:{self.name}"

        if not cache.add(lock_id, self.request.id, timeout=self.lock_timeout):
            msg = f"Task {self.name} skipped: another instance is running"
            logger.info(msg)
            self.update_state(state="SKIPPED", meta={"info": msg})
            return msg

        try:
            self.update_state(state="STARTED", meta={"info": "Task started"})
            # Hier wird die normale run-Methode aufgerufen
            return super().__call__(*args, **kwargs)
        finally:
            current_lock = cache.get(lock_id)
            if current_lock == self.request.id:
                cache.delete(lock_id)
