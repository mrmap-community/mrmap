from abc import ABC
from celery import Task
from crum import set_current_user, get_current_user
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist

from main.models import set_current_owner, get_current_owner
from structure.models import PendingTask, Organization


class PickleSerializer(Task, ABC):
    serializer = 'pickle'


class DefaultBehaviourTask(Task, ABC):
    create_pending_task = True

    def __call__(self, *args, **kwargs):
        if 'created_by_user_pk' in kwargs:
            try:
                user = get_user_model().objects.get(id=kwargs['created_by_user_pk'])
                set_current_user(user)
            except ObjectDoesNotExist:
                # cause celery worker starts n threads to schedule tasks with and the threads are `endless` we need
                # to `reset` the current user. Otherwise the last set user for this thread will be used.
                set_current_user(None)
        if 'owned_by_org_pk' in kwargs:
            try:
                owner = Organization.objects.get(id=kwargs["owned_by_org_pk"])
                set_current_owner(owner)
            except ObjectDoesNotExist:
                # cause celery worker starts n threads to schedule tasks with and the threads are `endless` we need
                # to `reset` the current organization. Otherwise the last set organization for this thread will be used.
                set_current_owner(None)
        if self.create_pending_task:
            try:
                PendingTask.objects.create(task_id=self.request.id,
                                           task_name=self.name,
                                           created_by_user=get_current_user(),
                                           owned_by_org=get_current_owner(),
                                           meta={
                                               "phase": "Pending..."
                                           })
            except Exception as e:
                import traceback
                traceback.print_exc()

        super().__call__(*args, **kwargs)
