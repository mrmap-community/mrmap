from celery import current_task, shared_task, states
from django.conf import settings
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_celery_results.models import TaskResult
from extras.tasks import CurrentUserTaskMixin
from registry.models import MonitoringRun
from registry.models.monitoring import WebMapServiceMonitoringRun
from registry.models.service import WebMapService


@shared_task(bind=True,
             base=CurrentUserTaskMixin)
def run_web_map_service_monitoring(self, service_pk, check_layers: bool = True, *args, **kwargs):
    print('inside task')
    print(self.request.id)
    wms = WebMapService.objects.get(pk=service_pk)
    monitoring_run: WebMapServiceMonitoringRun = WebMapServiceMonitoringRun.objects.create(
        task_result=TaskResult.objects.get(task_id=self.request.id),
        service=wms)

    current_task.update_state(
        state=states.STARTED,
        meta={
            'current': 0,
            'total': 100,
            'phase': f'start monitoring checks for {wms}',
        }
    )
    monitoring_run.check_wms()
    if check_layers:
        for layer in wms.layers:
            monitoring_run.check_layer(layer=layer)

    monitoring_run.save()

    # TODO: return with jsonapi document
    return {'msg': 'Done. Service(s) successfully monitored.',
            'id': str(monitoring_run.pk)}
