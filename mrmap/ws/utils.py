from celery import states
from django_celery_results.models import TaskResult


def get_initial_app_view_model():
    tasks_count = TaskResult.objects.filter(status__in=[states.STARTED, states.PENDING]).count()
    response = {'pendingTaskCount': tasks_count}
    return response
