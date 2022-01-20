from celery import current_task, shared_task, states
from django.utils.translation import gettext_lazy as _
from django_celery_results.models import TaskResult
from extras.tasks import CurrentUserTaskMixin
from registry.models.monitoring import (LayerGetMapMonitoringResult,
                                        WebMapServiceMonitoringResult)
from registry.models.service import Layer, WebMapService


@shared_task(bind=True,
             base=CurrentUserTaskMixin)
def check_web_map_service(self, service_pk, *args, **kwargs):

    wms: WebMapService = WebMapService.objects.get(pk=service_pk)

    current_task.update_state(
        state=states.STARTED,
        meta={
            'current': 0,
            'total': 100,
            'phase': f'start monitoring checks for {wms}',
        }
    )
    wms_monitoring_result: WebMapServiceMonitoringResult = WebMapServiceMonitoringResult(
        task_result=TaskResult.objects.get(task_id=self.request.id),
        service=wms)
    wms_monitoring_result.run_checks()
    wms_monitoring_result.save()

    # TODO: return with jsonapi document
    return "success"


@shared_task(bind=True,
             base=CurrentUserTaskMixin)
def check_get_map_layer(self, layer_pk, *args, **kwargs):

    layer: Layer = Layer.objects.get(pk=layer_pk)

    current_task.update_state(
        state=states.STARTED,
        meta={
            'current': 0,
            'total': 100,
            'phase': f'start monitoring checks for {layer}',
        }
    )
    layer_get_map_monitoring_result: LayerGetMapMonitoringResult = LayerGetMapMonitoringResult(
        task_result=TaskResult.objects.get(task_id=self.request.id),
        layer=layer)
    layer_get_map_monitoring_result.run_checks()
    layer_get_map_monitoring_result.save()

    # TODO: return with jsonapi document
    return "success"
