from typing import List

from celery import chain, group, shared_task
from django.utils import timezone
from django_celery_results.models import GroupResult, TaskResult
from registry.models.monitoring import (GetCapabilitiesProbe, GetMapProbe,
                                        WebMapServiceMonitoringRun,
                                        WebMapServiceMonitoringSetting)


@shared_task(bind=True)
def run_get_capabilitites_probe_check(self, probe_pk, run_pk, *args, **kwargs):
    task_result, _ = TaskResult.objects.get_or_create(
        task_id=self.request.id)
    probe: GetCapabilitiesProbe = GetCapabilitiesProbe.objects.get(
        pk=probe_pk)
    return probe.run_checks(
        run=WebMapServiceMonitoringRun.objects.get(pk=run_pk),
        celery_task_result=task_result
    ).pk


@shared_task(bind=True)
def run_get_map_probe_check(self, probe_pk, run_pk, *args, **kwargs):
    task_result, _ = TaskResult.objects.get_or_create(
        task_id=self.request.id)
    probe: GetMapProbe = GetMapProbe.objects.get(pk=probe_pk)
    return probe.run_checks(
        run=WebMapServiceMonitoringRun.objects.get(pk=run_pk),
        celery_task_result=task_result
    ).pk


@shared_task(bind=True)
def finish_run(self, task_results, run_pk, *args, **kwargs):
    run = WebMapServiceMonitoringRun.objects.get(pk=run_pk)
    run.date_done = timezone.now()
    if self.request.group:
        group_result, _ = GroupResult.objects.get_or_create(
            group_id=self.request.group)
        run.group_result = group_result
    run.save()
    return run.pk


@shared_task(bind=True)
def run_wms_monitoring(self, setting_pk, run_pk=None, *args, **kwargs):
    setting: WebMapServiceMonitoringSetting = WebMapServiceMonitoringSetting.objects.prefetch_related(
        "registry_getcapabilitiesprobe", "registry_getmapprobe").get(pk=setting_pk)
    get_capabilitites_probes: List[GetCapabilitiesProbe] = setting.registry_getcapabilitiesprobe.all(
    )
    get_map_probes: List[GetMapProbe] = setting.registry_getcapabilitiesprobe.all(
    )

    if run_pk:
        run = WebMapServiceMonitoringRun.objects.get(pk=run_pk)
    else:
        run = WebMapServiceMonitoringRun(setting=setting)
        run.save(trigger_run_wms_monitoring=False)
    tasks = []
    for probe in get_capabilitites_probes:
        tasks.append(run_get_capabilitites_probe_check.s(
            probe_pk=probe.pk, run_pk=run.pk))

    for probe in get_map_probes:
        tasks.append(run_get_map_probe_check.s(
            probe_pk=probe.pk, run_pk=run.pk))

    # starting checks in parallel mode
    chain(group(tasks), finish_run.s(run_pk=run.pk)).apply_async()
    # saving GroupResult with configured backends
    # result.save()
    # publish the celery group id to the run
    # run.group_result = GroupResult.objects.get(pk=result.id)
    run.save()
    return run.pk
