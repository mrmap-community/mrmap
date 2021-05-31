from abc import ABC
from celery import Task
from crum import set_current_user
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist

from main.models import set_current_owner, get_current_owner
from structure.models import PendingTask, Organization


class DefaultBehaviourTask(Task, ABC):
    """ Set current user and owner for models which uses CommonInfo

    """
    user = None
    owner = None
    pending_task = None

    def set_current_user(self, user_pk):
        try:
            self.user = get_user_model().objects.get(id=user_pk)
        except ObjectDoesNotExist:
            pass
        finally:
            # cause celery worker starts n threads to schedule tasks with and the threads are `endless` we need
            # to `reset` the current user. Otherwise the last set user for this thread will be used.
            set_current_user(self.user)

    def set_current_owner(self, owner_pk):
        try:
            self.owner = Organization.objects.get(id=owner_pk)
        except ObjectDoesNotExist:
            pass
        finally:
            # cause celery worker starts n threads to schedule tasks with and the threads are `endless` we need
            # to `reset` the current organization. Otherwise the last set organization for this thread will be used.
            set_current_owner(self.owner)

    def default_behaviour(self, **kwargs):
        if 'created_by_user_pk' in kwargs:
            self.set_current_user(kwargs["created_by_user_pk"])
        if 'owned_by_org_pk' in kwargs:
            self.set_current_owner(kwargs["owned_by_org_pk"])
        if "pending_task_pk" in kwargs and not self.pending_task:
            try:
                self.pending_task = PendingTask.objects.get(id=kwargs["pending_task_pk"])
            except ObjectDoesNotExist:
                pass

    def __call__(self, *args, **kwargs):
        self.default_behaviour(**kwargs)
        return super().__call__(*args, **kwargs)


class MonitoringTask(DefaultBehaviourTask, ABC):
    """ Abstract class to implement default behaviour for `main` tasks which starts a complex set of subtasks.

        It creates a new PendingTask instance if it is None.
    """

    def __call__(self, *args, **kwargs):
        self.default_behaviour(**kwargs)
        if not self.pending_task:
            try:
                self.pending_task = PendingTask.objects.create()
                kwargs.update({"pending_task_pk": self.pending_task.pk})
            except Exception as e:
                # todo: log instead of print
                import traceback
                traceback.print_exc()
        return super().__call__(*args, **kwargs)
