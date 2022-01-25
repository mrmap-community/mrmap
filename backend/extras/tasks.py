from typing import OrderedDict

from celery.signals import task_postrun, task_prerun
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from rest_framework.test import APIRequestFactory
from simple_history.models import HistoricalRecords


@task_prerun.connect
def set_current_user(*args, **kwargs):
    http_request = kwargs.get("http_request", None)
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


@task_postrun.connect
def reset_current_user(*args, **kwargs):
    if hasattr(HistoricalRecords.context, "request"):
        del HistoricalRecords.context.request
