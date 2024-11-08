from datetime import datetime
from typing import List

from celery import current_task, group, shared_task, states
from django_celery_results.models import TaskResult
from registry.exceptions.service import OperationNotSupported
from registry.models.monitoring import (GetCapabilititesProbe, GetMapProbe,
                                        LayerGetFeatureInfoResult,
                                        LayerGetMapResult,
                                        WebMapServiceMonitoringRun,
                                        WebMapServiceMonitoringSetting,
                                        WMSGetCapabilitiesResult)
from registry.models.service import Layer, WebMapService
from rest_framework.reverse import reverse


@shared_task(bind=True)
def check_wms_get_capabilities_operation(self, service_pk, *args, **kwargs):
    wms: WebMapService = WebMapService.objects.get(pk=service_pk)

    current_task.update_state(
        state=states.STARTED,
        meta={
            'current': 0,
            'total': 100,
            'phase': f'start monitoring checks for {wms}',
        }
    )
    task_result: TaskResult
    task_result, created = TaskResult.objects.get_or_create(
        task_id=self.request.id)
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


@shared_task(bind=True)
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
        task_id=self.request.id)
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


@shared_task(bind=True)
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
        task_id=self.request.id)
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


@shared_task(bind=True)
def run_get_capabilitites_probe_check(self, probe_pk, run_pk, *args, **kwargs):
    run = WebMapServiceMonitoringRun.objects.get(pk=run_pk)
    probe: GetCapabilititesProbe = GetCapabilititesProbe.objects.get(
        pk=probe_pk)
    probe.run_check(run=run)


@shared_task(bind=True)
def run_get_map_probe_check(self, probe_pk, run_pk, *args, **kwargs):
    run = WebMapServiceMonitoringRun.objects.get(pk=run_pk)
    probe: GetMapProbe = GetMapProbe.objects.get(pk=probe_pk)
    probe.run_check(run=run)


@shared_task(bind=True)
def finish_run(self, run_pk, *args, **kwargs):
    run = WebMapServiceMonitoringRun.objects.get(pk=run_pk)
    run.date_done = datetime.now()
    run.save()


@shared_task(bind=True)
def run_wms_monitoring(self, setting_pk, run_pk=None, *args, **kwargs):
    setting: WebMapServiceMonitoringSetting = WebMapServiceMonitoringSetting.objects.prefetch_related(
        "registry_getcapabilititesprobe", "registry_getmapprobe").get(pk=setting_pk)
    get_capabilitites_probes: List[GetCapabilititesProbe] = setting.registry_getcapabilititesprobe.all(
    )
    get_map_probes: List[GetMapProbe] = setting.registry_getcapabilititesprobe.all(
    )

    if run_pk:
        run = WebMapServiceMonitoringRun.objects.get(pk=run_pk)
    else:
        run = WebMapServiceMonitoringRun.objects.create(
            trigger_run_wms_monitoring=False)
    tasks = []
    for probe in get_capabilitites_probes:
        tasks.append(run_get_capabilitites_probe_check.s(
            probe_pk=probe.pk, run_pk=run.pk))

    for probe in get_map_probes:
        tasks.append(run_get_map_probe_check.s(
            probe_pk=probe.pk, run_pk=run.pk))

    # starting checks in parallel mode
    group(tasks).apply_async()

    run.save()
