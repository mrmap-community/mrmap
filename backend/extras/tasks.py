from abc import ABC

from celery import Task
from crum import set_current_user
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from users.models.groups import Organization

from extras.models import set_current_owner


class CommonInfoSetupMixin(Task, ABC):
    """ Set current user and owner for models which uses CommonInfo

    """
    user = None
    owner = None

    def set_current_user(self, user_pk=None):
        try:
            if user_pk:
                self.user = get_user_model().objects.get(id=user_pk)
            else:
                raise ObjectDoesNotExist
        except ObjectDoesNotExist:
            pass
        finally:
            # cause celery worker starts n threads to schedule tasks with and the threads are `endless` we need
            # to `reset` the current user. Otherwise the last set user for this thread will be used.
            set_current_user(self.user)

    def set_current_owner(self, owner_pk=None):
        try:
            if owner_pk:
                self.owner = Organization.objects.get(id=owner_pk)
            else:
                raise ObjectDoesNotExist
        except ObjectDoesNotExist:
            pass
        finally:
            # cause celery worker starts n threads to schedule tasks with and the threads are `endless` we need
            # to `reset` the current organization. Otherwise the last set organization for this thread will be used.
            set_current_owner(self.owner)

    def common_info_setup(self, **kwargs):
        self.set_current_user(kwargs.get("created_by_user_pk", None))
        self.set_current_owner(kwargs.get("owned_by_org_pk", None))

    def __call__(self, *args, **kwargs):
        # all task functions uses the same class instance; so we need to reset the stored pending pending task variable
        # to avoid of using the same pending task object for different task/workflow runs.
        self.common_info_setup(**kwargs)
        return super().__call__(*args, **kwargs)
