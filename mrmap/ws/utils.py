from celery import states
from django.db.models import Q
from job.models import Task


def get_app_view_model(user):
    tasks_count = user.get_instances(klass=Task, filter=Q(status__in=[states.STARTED, states.PENDING])).count()
    response = {'taskCount': tasks_count}
    return response
