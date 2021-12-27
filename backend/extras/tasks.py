from abc import ABC
from typing import OrderedDict

from celery import Task
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from rest_framework.test import APIRequestFactory
from simple_history.models import HistoricalRecords


# TODO: rename
class CurrentUserTaskMixin(Task, ABC):
    """ Set current user and owner for models which uses CommonInfo

    """

    def _set_current_request(self, request=None):
        if request:
            dummy_request = None
            if request['method'].lower() == 'get':
                dummy_request = APIRequestFactory().get(
                    path=request['path'],
                    data=request['data'],
                )
            elif request['method'].lower() == 'post':
                dummy_request = APIRequestFactory().post(
                    path=request['path'],
                    data=request['data'],
                    content_type=request['content_type']
                )
            if request.get('user_pk', None):
                try:
                    dummy_request.user = get_user_model(
                    ).objects.get(pk=request['user_pk'])
                except ObjectDoesNotExist:
                    pass
            if dummy_request and (not hasattr(dummy_request, 'query_params') or not dummy_request.query_params):
                dummy_request.query_params = OrderedDict()
            HistoricalRecords.context.request = dummy_request

    def _reset_current_request(self):
        if hasattr(HistoricalRecords.context, "request"):
            del HistoricalRecords.context.request

    def __call__(self, *args, **kwargs):
        # all task functions uses the same class instance; so we need to reset the stored pending pending task variable
        # to avoid of using the same pending task object for different task/workflow runs.
        self._set_current_request(kwargs.get("request", None))
        return super().__call__(*args, **kwargs)

    def on_success(self, retval, task_id, args, kwargs):
        self._reset_current_request()
        return super().on_success(retval, task_id, args, kwargs)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        self._reset_current_request()
        return super().on_failure(exc, task_id, args, kwargs, einfo)

    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        self._reset_current_request()
        return super().after_return(status, retval, task_id, args, kwargs, einfo)

    def update_state(self, task_id=None, state=None, meta=None, **kwargs):
        if self.request.id:
            return super().update_state(task_id=task_id, state=state, meta=meta, **kwargs)
