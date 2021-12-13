from abc import ABC

from celery import Task
from crum import set_current_user
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist


class CurrentUserTaskMixin(Task, ABC):
    """ Set current user and owner for models which uses CommonInfo

    """

    def set_current_user(self, user_pk=None):
        try:
            if user_pk:
                set_current_user(user=get_user_model().objects.get(id=user_pk))
            else:
                print(f'can not find user by id {user_pk}')
                raise ObjectDoesNotExist
        except ObjectDoesNotExist:
            pass

    def common_info_setup(self, **kwargs):
        self.set_current_user(kwargs.get("current_user", None))

    def __call__(self, *args, **kwargs):
        # all task functions uses the same class instance; so we need to reset the stored pending pending task variable
        # to avoid of using the same pending task object for different task/workflow runs.
        self.common_info_setup(**kwargs)
        return super().__call__(*args, **kwargs)

    def on_success(self, retval, task_id, args, kwargs):
        set_current_user()
        return super().on_success(retval, task_id, args, kwargs)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        set_current_user()
        return super().on_failure(exc, task_id, args, kwargs, einfo)

    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        set_current_user()
        return super().after_return(status, retval, task_id, args, kwargs, einfo)
