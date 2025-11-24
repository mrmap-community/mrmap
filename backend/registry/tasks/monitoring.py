from typing import List

from celery import chain, group, shared_task
from django.utils import timezone
from registry.models.monitoring import (GetCapabilitiesProbe, GetMapProbe,
                                        WebMapServiceMonitoringRun,
                                        WebMapServiceMonitoringSetting)


@shared_task(bind=True)
def run_get_capabilitites_probe_check(self, probe_pk, run_pk, *args, **kwargs):
    probe: GetCapabilitiesProbe = GetCapabilitiesProbe.objects.get(
        pk=probe_pk)
    return probe.run_checks(
        run=WebMapServiceMonitoringRun.objects.get(pk=run_pk),
    ).pk


@shared_task(bind=True)
def run_get_map_probe_check(self, probe_pk, run_pk, *args, **kwargs):
    probe: GetMapProbe = GetMapProbe.objects.get(pk=probe_pk)
    return probe.run_checks(
        run=WebMapServiceMonitoringRun.objects.get(pk=run_pk),
    ).pk


@shared_task(bind=True)
def finish_run(self, _group_result, run_pk, *args, **kwargs):
    run = WebMapServiceMonitoringRun.objects.get(pk=run_pk)
    run.date_done = timezone.now()
    run.save()
    return run.pk


@shared_task(bind=True)
def run_wms_monitoring(self, run_pk=None, *args, **kwargs):
    run = WebMapServiceMonitoringRun.objects.select_related(
        "setting").get(pk=run_pk)
    get_capabilitites_probes: List[GetCapabilitiesProbe] = run.setting.registry_getcapabilitiesprobes.all(
    )
    get_map_probes: List[GetMapProbe] = run.setting.registry_getcapabilitiesprobes.all(
    )

    tasks = []
    for probe in get_capabilitites_probes:
        tasks.append(run_get_capabilitites_probe_check.s(
            probe_pk=probe.pk, run_pk=run.pk))

    for probe in get_map_probes:
        tasks.append(run_get_map_probe_check.s(
            probe_pk=probe.pk, run_pk=run.pk))

    # starting checks in parallel mode
    chain(group(tasks), finish_run.s(run_pk=run.pk)).apply_async()
    return run.pk


@shared_task(bind=True)
def create_wms_monitoring_run(self, setting_pk, *args, **kwargs):
    setting: WebMapServiceMonitoringSetting = WebMapServiceMonitoringSetting.objects.get(
        pk=setting_pk)
    run = WebMapServiceMonitoringRun(setting=setting)
    run.save()
