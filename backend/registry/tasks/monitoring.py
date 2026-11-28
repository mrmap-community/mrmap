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

#: the phase a run which had nothing to check reports itself with. The step
#: count of such a run is 0, which the background activity reads as "does not
#: know its steps" - so the phase is the only answer why the run has no probe
#: results at all, and it names the reason the way `fail_process` names a
#: failure (#1806)
NOTHING_TO_CHECK_PHASE = "Completed without checks: the setting has no probes"


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

    probe = apps.get_model(probe_model).objects.for_probe_execution().get(
        pk=probe_pk)
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
def finish_run(self, _group_result, run_pk, run_model=WMS_RUN_MODEL,
               *args, **kwargs):
    """Report a monitoring run as ended.

    Args:
        _group_result: the return value of the group of probe checks which
            precedes this task in the chain
        run_pk (int): primary key of the run to end
        run_model (str): label of the monitoring run model of the run
    """
    run = apps.get_model(run_model).objects.get(pk=run_pk)
    run.date_done = timezone.now()
    # only date_done changes here; a narrower update_fields keeps the terminal
    # save from rewriting the whole row (#1393)
    run.save(update_fields=["date_done"])
    run.report_process(ProcessStatusEnum.COMPLETED)
    invalidate_service_alerts()
    return run.pk


def complete_run_without_checks(run):
    """End a run whose setting has no probe, right here.

    A setting is created together with its service and its probes are a
    resource of their own, so every monitoring starts out without a single
    probe. Such a run has nothing to check, and dispatching it as the chain of
    an empty group and the finishing task never reaches that task at all:
    celery applies the second step of a chain with the return value of the
    first, which an empty group does not deliver, so applying `finish_run`
    raised a `TypeError`. The run and its process were already created by then
    and no task was left to close them, so the process stayed as running with
    "Running 0 checks" while the api answered a setting which ran on schedule
    and checked nothing (#1806). Completing the run directly answers the truth
    instead: a run which had nothing to check is a completed run.

    Args:
        run (MonitoringRun): the run which has no probe to run
    """
    logger.info(
        "Monitoring run %s of setting %s has no probes; it completes without "
        "any check.", run.pk, run.setting_id)
    # the running report is what plans the steps and writes the phase; the
    # completion which follows keeps both, as in the normal path
    run.report_process(
        ProcessStatusEnum.RUNNING,
        phase=NOTHING_TO_CHECK_PHASE,
        total_steps=0)
    finish_run(None, run_pk=run.pk, run_model=run._meta.label_lower)


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
    if not tasks:
        complete_run_without_checks(run)
        return run.pk
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

    run = WebMapServiceMonitoringRun.objects.for_monitoring_task().get(
        pk=run_pk)
    probes = list(run.setting.registry_getcapabilitiesprobes.all()) + \
        list(run.setting.registry_getmapprobes.all())

    return start_run(run=run, probes=probes, task=run_probe_check)


# the create_* tasks are what beat fires: the monitoring settings write the
# "monitoring" queue into their PeriodicTask rows, and since #1455 the task
# declarations carry the same queue - a beat row and an api-triggered run
# of one task must not ride two different queues (the tasks of the run
# itself keep their declarations as they are)
@shared_task(queue=celery_queues.MONITORING, bind=True)
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

    run = WebFeatureServiceMonitoringRun.objects.for_monitoring_task().get(
        pk=run_pk)
    probes = list(run.setting.registry_webfeatureservicegetcapabilitiesprobes.all()) + \
        list(run.setting.registry_webfeatureservicegetfeatureprobes.all())

    return start_run(run=run, probes=probes, task=run_probe_check)


@shared_task(queue=celery_queues.MONITORING, bind=True)
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

    run = CatalogueServiceMonitoringRun.objects.for_monitoring_task().get(
        pk=run_pk)
    probes = list(run.setting.registry_catalogueservicegetcapabilitiesprobes.all()) + \
        list(run.setting.registry_catalogueservicegetrecordsprobes.all())

    return start_run(run=run, probes=probes, task=run_probe_check)


@shared_task(queue=celery_queues.MONITORING, bind=True)
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
