from celery import Task, current_task, shared_task, states
from django.utils.translation import gettext_lazy as _
from django_celery_results.models import TaskResult
from extras.tasks import CurrentUserTaskMixin
from registry.exceptions.service import OperationNotSupported
from registry.models.monitoring import (LayerGetFeatureInfoResult,
                                        LayerGetMapResult,
                                        WMSGetCapabilitiesResult)
from registry.models.service import Layer, WebMapService
from rest_framework.reverse import reverse


@shared_task(bind=True,
             base=CurrentUserTaskMixin)
def check_wms_get_capabilities_operation(self, service_pk, *args, **kwargs):
    print(current_task)
    print(self.request)
    print(self.request.id)
    wms: WebMapService = WebMapService.objects.get(pk=service_pk)

    current_task.update_state(
        state=states.STARTED,
        meta={
            'current': 0,
            'total': 100,
            'phase': f'start monitoring checks for {wms}',
        }
    )
    task_result, created = TaskResult.objects.get_or_create(
        task_id=self.request.id,
        task_name=current_task.name)
    wms_monitoring_result: WMSGetCapabilitiesResult = WMSGetCapabilitiesResult(
        task_result=task_result,
        service=wms)
    wms_monitoring_result.run_checks()
    wms_monitoring_result.save()

    return {
        "data": {
            "type": "WMSGetCapabilitiesResult",
            "id": f"{wms_monitoring_result.pk}",
            "links": {
                    "self": f"{reverse(viewname='registry:wmsgetcapabilitiesresult-detail', args=[wms_monitoring_result.pk])}"
            }
        }
    }


@shared_task(bind=True,
             base=CurrentUserTaskMixin)
def check_get_map_operation(self, layer_pk, *args, **kwargs):

    layer: Layer = Layer.objects.get(pk=layer_pk)

    current_task.update_state(
        state=states.STARTED,
        meta={
            'current': 0,
            'total': 100,
            'phase': f'start monitoring checks for {layer}',
        }
    )
    task_result, created = TaskResult.objects.get_or_create(
        task_id=self.request.id,
        task_name=current_task.name)
    monitoring_result: LayerGetMapResult = LayerGetMapResult(
        task_result=task_result,
        layer=layer)
    monitoring_result.run_checks()
    monitoring_result.save()

    return {
        "data": {
            "type": "LayerGetMapResult",
            "id": f"{monitoring_result.pk}",
            "links": {
                    "self": f"{reverse(viewname='registry:layergetmapresult-detail', args=[monitoring_result.pk])}"
            }
        }
    }


@shared_task(bind=True,
             base=CurrentUserTaskMixin)
def check_get_feature_info_operation(self, layer_pk, *args, **kwargs):
    layer: Layer = Layer.objects.get(pk=layer_pk)

    current_task.update_state(
        state=states.STARTED,
        meta={
            'current': 0,
            'total': 100,
            'phase': f'start monitoring checks for {layer}',
        }
    )
    task_result, created = TaskResult.objects.get_or_create(
        task_id=self.request.id,
        task_name=current_task.name)
    monitoring_result: LayerGetFeatureInfoResult = LayerGetFeatureInfoResult(
        task_result=task_result,
        layer=layer)
    try:
        monitoring_result.run_checks()
        monitoring_result.save()
    except OperationNotSupported as exception:
        return {
            "data": {
                "type": "OperationNotSupported",
                "id": f"{exception.__str__}",
            }
        }
    return {
        "data": {
            "type": "LayerGetFeatureInfoResult",
            "id": f"{monitoring_result.pk}",
            "links": {
                    "self": f"{reverse(viewname='registry:layergetfeatureinforesult-detail', args=[monitoring_result.pk])}"
            }
        }
    }
