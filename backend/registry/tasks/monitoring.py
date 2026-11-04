from celery import chain, group, shared_task
from django.apps import apps
from django.utils import timezone
from notify.enums import ProcessStatusEnum
from notify.utils import invalidate_service_alerts

WMS_RUN_MODEL = "registry.webmapservicemonitoringrun"

#: upper bound of probe requests one monitoring run has in flight against
#: the monitored service; the checks of a run are dispatched in batches of
#: this size, chained so that the next batch starts when the previous one
#: is done. A generated probe set (#743) may hold far more probes than a
#: manual setting ever had and a plain group would fan all of them out at
#: once against one external service.
MAX_CONCURRENT_PROBE_REQUESTS = 10


@shared_task(bind=True)
def run_probe_check(self, probe_model, run_model, probe_pk, run_pk, *args, **kwargs):
    """Execute the checks of one probe within a monitoring run.

    Args:
        probe_model (str): label of the probe model to run
        run_model (str): label of the monitoring run model of the probe
        probe_pk (int): primary key of the probe to run
        run_pk (int): primary key of the monitoring run to store the result in

    Returns:
        int: primary key of the created probe result
    """

    probe = apps.get_model(probe_model).objects.get(pk=probe_pk)
    run = apps.get_model(run_model).objects.get(pk=run_pk)
    try:
        result = probe.run_checks(run=run).pk
    except Exception as error:
        # the task which finishes a run is never reached when a probe raises:
        # report the failure of the run, otherwise it stays as running in the
        # overview of the background activity
        run.fail_process(error)
        raise
    run.report_process(ProcessStatusEnum.RUNNING, step_done=True)
    return result


@shared_task(bind=True)
def finish_run(self, _group_result, run_pk, run_model=WMS_RUN_MODEL, *args, **kwargs):
    run = apps.get_model(run_model).objects.get(pk=run_pk)
    run.date_done = timezone.now()
    run.save()
    run.report_process(ProcessStatusEnum.COMPLETED)
    invalidate_service_alerts()
    return run.pk


def start_run(run, probes, task):
    """Start the checks of all probes of a monitoring run, in bounded batches.

    The probe tasks are dispatched as groups of at most
    `MAX_CONCURRENT_PROBE_REQUESTS` checks, chained one after another: no
    run ever puts more than that amount of requests against the monitored
    service at the same time, while the per-probe result and the
    `BackgroundProcess` reporting of `finish_run` stay exactly the same.

    Args:
        run (MonitoringRun): the run to store the probe results in
        probes (Iterable[Probe]): the probes which belong to the setting of the run
        task (Callable): the task which executes one probe

    Returns:
        int: primary key of the run
    """

    tasks = [
        task.s(
            probe_model=probe._meta.label_lower,
            run_model=run._meta.label_lower,
            probe_pk=probe.pk,
            run_pk=run.pk)
        for probe in probes
    ]
    run.report_process(
        ProcessStatusEnum.RUNNING,
        phase=f"Running {len(tasks)} checks",
        total_steps=len(tasks))
    # a run without probes keeps its (empty) group: `finish_run` expects a
    # preceding result in the chain
    batches = [tasks[i:i + MAX_CONCURRENT_PROBE_REQUESTS]
               for i in range(0, len(tasks), MAX_CONCURRENT_PROBE_REQUESTS)] or [[]]
    chain(
        *(group(batch) for batch in batches),
        finish_run.s(run_pk=run.pk, run_model=run._meta.label_lower),
    ).apply_async()
    return run.pk


@shared_task(bind=True)
def run_wms_monitoring(self, run_pk=None, *args, **kwargs):
    from registry.models.monitoring import WebMapServiceMonitoringRun

    run = WebMapServiceMonitoringRun.objects.select_related(
        "setting").get(pk=run_pk)
    probes = list(run.setting.registry_getcapabilitiesprobes.all()) + \
        list(run.setting.registry_getmapprobes.all())

    return start_run(run=run, probes=probes, task=run_probe_check)


@shared_task(bind=True)
def create_wms_monitoring_run(self, name, *args, **kwargs):
    from registry.models.monitoring import (WebMapServiceMonitoringRun,
                                            WebMapServiceMonitoringSetting)
    setting: WebMapServiceMonitoringSetting = WebMapServiceMonitoringSetting.objects.get(
        name=name)
    run = WebMapServiceMonitoringRun(setting=setting)
    run.save()


@shared_task(bind=True)
def run_wfs_monitoring(self, run_pk=None, *args, **kwargs):
    from registry.models.monitoring import WebFeatureServiceMonitoringRun

    run = WebFeatureServiceMonitoringRun.objects.select_related(
        "setting").get(pk=run_pk)
    probes = list(run.setting.registry_webfeatureservicegetcapabilitiesprobes.all()) + \
        list(run.setting.registry_webfeatureservicegetfeatureprobes.all())

    return start_run(run=run, probes=probes, task=run_probe_check)


@shared_task(bind=True)
def create_wfs_monitoring_run(self, name, *args, **kwargs):
    from registry.models.monitoring import (WebFeatureServiceMonitoringRun,
                                            WebFeatureServiceMonitoringSetting)
    setting: WebFeatureServiceMonitoringSetting = WebFeatureServiceMonitoringSetting.objects.get(
        name=name)
    run = WebFeatureServiceMonitoringRun(setting=setting)
    run.save()


@shared_task(bind=True)
def run_csw_monitoring(self, run_pk=None, *args, **kwargs):
    from registry.models.monitoring import CatalogueServiceMonitoringRun

    run = CatalogueServiceMonitoringRun.objects.select_related(
        "setting").get(pk=run_pk)
    probes = list(run.setting.registry_catalogueservicegetcapabilitiesprobes.all()) + \
        list(run.setting.registry_catalogueservicegetrecordsprobes.all())

    return start_run(run=run, probes=probes, task=run_probe_check)


@shared_task(bind=True)
def create_csw_monitoring_run(self, name, *args, **kwargs):
    from registry.models.monitoring import (CatalogueServiceMonitoringRun,
                                            CatalogueServiceMonitoringSetting)
    setting: CatalogueServiceMonitoringSetting = CatalogueServiceMonitoringSetting.objects.get(
        name=name)
    run = CatalogueServiceMonitoringRun(setting=setting)
    run.save()
