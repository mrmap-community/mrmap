from celery import chain, group, shared_task
from django.utils import timezone


@shared_task(bind=True)
def run_get_capabilitites_probe_check(self, probe_pk, run_pk, *args, **kwargs):
    from registry.models.monitoring import (GetCapabilitiesProbe,
                                            WebMapServiceMonitoringRun)

    probe: GetCapabilitiesProbe = GetCapabilitiesProbe.objects.get(
        pk=probe_pk)
    return probe.run_checks(
        run=WebMapServiceMonitoringRun.objects.get(pk=run_pk),
    ).pk


@shared_task(bind=True)
def run_get_map_probe_check(self, probe_pk, run_pk, *args, **kwargs):
    from registry.models.monitoring import (GetMapProbe,
                                            WebMapServiceMonitoringRun)
    probe: GetMapProbe = GetMapProbe.objects.get(pk=probe_pk)
    return probe.run_checks(
        run=WebMapServiceMonitoringRun.objects.get(pk=run_pk),
    ).pk


@shared_task(bind=True)
def finish_run(self, _group_result, run_pk, *args, **kwargs):
    from registry.models.monitoring import WebMapServiceMonitoringRun
    run = WebMapServiceMonitoringRun.objects.get(pk=run_pk)
    run.date_done = timezone.now()
    run.save()
    return run.pk


@shared_task(bind=True)
def run_wms_monitoring(self, run_pk=None, *args, **kwargs):
    from registry.models.monitoring import (GetCapabilitiesProbe, GetMapProbe,
                                            WebMapServiceMonitoringRun)
    run = WebMapServiceMonitoringRun.objects.select_related(
        "setting").get(pk=run_pk)
    get_capabilitites_probes: list[GetCapabilitiesProbe] = run.setting.registry_getcapabilitiesprobes.all(
    )
    get_map_probes: list[GetMapProbe] = run.setting.registry_getcapabilitiesprobes.all(
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
def create_wms_monitoring_run(self, name, *args, **kwargs):
    from registry.models.monitoring import (WebMapServiceMonitoringRun,
                                            WebMapServiceMonitoringSetting)
    setting: WebMapServiceMonitoringSetting = WebMapServiceMonitoringSetting.objects.get(
        name=name)
    run = WebMapServiceMonitoringRun(setting=setting)
    run.save()
