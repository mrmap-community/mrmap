from abc import ABC
from jobs.enums import TaskStatusEnum
from celery import Task
from crum import set_current_user
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from extras.models import set_current_owner
from users.models.groups import Organization
from django_celery_results.models import TaskResult
from django.utils import timezone
from jobs.models import Task as DbTask


# todo: deprecated; use classes below
def default_task_handler(**kwargs):
    if 'created_by_user_pk' in kwargs:
        try:
            user = get_user_model().objects.get(id=kwargs['created_by_user_pk'])
            set_current_user(user)
        except ObjectDoesNotExist:
            return


class DefaultBehaviourTask(Task, ABC):
    """ Set current user and owner for models which uses CommonInfo

    """
    user = None
    owner = None
    pending_task = None

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

    def default_behaviour(self, **kwargs):
        self.set_current_user(kwargs.get("created_by_user_pk", None))
        self.set_current_owner(kwargs.get("owned_by_org_pk", None))
        if "pending_task_pk" in kwargs:
            try:
                self.pending_task = DbTask.objects.get(id=kwargs["pending_task_pk"])
            except ObjectDoesNotExist:
                pass

    def __call__(self, *args, **kwargs):
        # all task functions uses the same class instance; so we need to reset the stored pending pending task variable
        # to avoid of using the same pending task object for different task/workflow runs.
        self.pending_task = None
        self.default_behaviour(**kwargs)
        return super().__call__(*args, **kwargs)

    def on_success(self, retval, task_id, args, kwargs):
        if self.pending_task:
            self.pending_task.sub_tasks.add(*TaskResult.objects.filter(task_id=task_id))

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        if self.pending_task:
            self.pending_task.status = TaskStatusEnum.FAILURE.value
            self.pending_task.done_at = timezone.now()
            self.pending_task.traceback = einfo
            self.pending_task.save()


class MonitoringTask(DefaultBehaviourTask, ABC):
    """ Abstract class to implement default behaviour for `extras` tasks which starts a complex set of subtasks.

        It creates a new PendingTask instance if it is None.
    """

    def __call__(self, *args, **kwargs):
        # all task functions uses the same class instance; so we need to reset the stored pending pending task variable
        # to avoid of using the same pending task object for different task/workflow runs.
        self.pending_task = None
        self.default_behaviour(**kwargs)
        if not self.pending_task:
            try:
                self.pending_task = DbTask.objects.create()
                kwargs.update({"pending_task_pk": self.pending_task.pk})
            except Exception:
                # TODO: log instead of print
                import traceback
                traceback.print_exc()
        return super().__call__(*args, **kwargs)
