from celery import states
from django.db.models import Q
from structure.models import PendingTask


def get_app_view_model(user):
    tasks_count = user.get_instances(klass=PendingTask, filter=Q(status__in=[states.STARTED, states.PENDING])).count()
    response = {'pendingTaskCount': tasks_count}
    return response
