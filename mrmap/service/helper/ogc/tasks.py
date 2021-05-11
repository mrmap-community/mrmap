from abc import ABC
from celery import Task
from crum import set_current_user, get_current_user
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from structure.models import PendingTask


class PickleSerializer(Task, ABC):
    serializer = 'pickle'


class DefaultBehaviourTask(Task, ABC):

    def __call__(self, owned_by_org_pk, *args, **kwargs):
        if 'created_by_user_pk' in kwargs:
            try:
                user = get_user_model().objects.get(id=kwargs['created_by_user_pk'])
                set_current_user(user)
            except ObjectDoesNotExist:
                return

        try:
            PendingTask.objects.create(task_id=self.request.id,
                                       task_name=self.name,
                                       created_by_user=get_current_user(),
                                       owned_by_org_id=owned_by_org_pk,
                                       meta={
                                           "phase": "Pending..."
                                       })
        except Exception as e:
            import traceback
            traceback.print_exc()

        super().__call__(owned_by_org_pk, *args, **kwargs)
