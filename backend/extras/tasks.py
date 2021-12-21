from abc import ABC
from typing import OrderedDict

from celery import Task
from crum import set_current_request, set_current_user
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from rest_framework.test import APIRequestFactory


class CurrentUserTaskMixin(Task, ABC):
    """ Set current user and owner for models which uses CommonInfo

    """

    def set_current_user(self, user_pk=None):
        try:
            if user_pk:
                set_current_user(user=get_user_model().objects.get(id=user_pk))
            else:
                raise ObjectDoesNotExist
        except ObjectDoesNotExist:
            pass

    def set_current_request(self, request=None):
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
            if dummy_request and (not hasattr(dummy_request, 'query_params') or not dummy_request.query_params):
                dummy_request.query_params = OrderedDict()
            set_current_request(request=dummy_request)

    def common_info_setup(self, **kwargs):
        self.set_current_user(kwargs.get("current_user", None))
        self.set_current_request(kwargs.get("request", None))

    def __call__(self, *args, **kwargs):
        # all task functions uses the same class instance; so we need to reset the stored pending pending task variable
        # to avoid of using the same pending task object for different task/workflow runs.
        self.common_info_setup(**kwargs)
        return super().__call__(*args, **kwargs)

    def on_success(self, retval, task_id, args, kwargs):
        set_current_user(False)
        set_current_request(False)
        return super().on_success(retval, task_id, args, kwargs)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        set_current_user(False)
        set_current_request(False)
        return super().on_failure(exc, task_id, args, kwargs, einfo)

    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        set_current_user(False)
        set_current_request(False)
        return super().after_return(status, retval, task_id, args, kwargs, einfo)

    def update_state(self, task_id=None, state=None, meta=None, **kwargs):
        if self.request.id:
            return super().update_state(task_id=task_id, state=state, meta=meta, **kwargs)
