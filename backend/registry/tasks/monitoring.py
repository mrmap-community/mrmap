from celery import chain, group, shared_task
from django.apps import apps
from django.conf import settings
from django.utils import timezone
from extras.tasks import SingletonTask
from logging import Logger
from MrMap import celery_queues
from notify.enums import ProcessStatusEnum
from notify.utils import invalidate_service_alerts

logger: Logger = settings.ROOT_LOGGER

WMS_RUN_MODEL = "registry.webmapservicemonitoringrun"


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
    """Start the checks of all probes of a monitoring run in parallel mode.

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
    chain(group(tasks), finish_run.s(
        run_pk=run.pk, run_model=run._meta.label_lower)).apply_async()
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


@shared_task(queue=celery_queues.DB_ROUTINES, bind=True, base=SingletonTask)
def delete_expired_probe_response_artifacts(self, *args, **kwargs):
    """Takes back the stored probe responses whose retention has passed (#682).

    Runs as a singleton on the ``db-routines`` queue like the other
    housekeeping: two sweeps over the same artifacts have nothing to add to
    each other. Only the bodies leave; the rows of the probe results and their
    check answers stay, so the monitoring history keeps answering what ran and
    when, while an expired body is refused as gone by the artifact endpoint
    from its retention moment on and not from the moment this sweep ran.
    """
    from registry.models.monitoring import \
        purge_expired_probe_response_artifacts

    summary = purge_expired_probe_response_artifacts()
    logger.info(
        "Monitoring probe response artifacts: %s bodies purged "
        "(retention %s days).", summary["purged"], summary["retention_days"])
    return summary
