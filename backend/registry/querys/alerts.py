"""The states of a service which need the attention of an administrator.

Nothing which is described here is stored. An alert is the projection of a state
which already exists - the result of the last monitoring run of a service, the
status of the last update job of a service, the schedule a service did not keep
and the records a harvesting job left behind - so that the question "what has to
be done about this service" is decided in one place and answered by the same
rules to the alerts of a service and to every report which may follow.

Every collector reads one of those states and answers its rows as a dict of the
fields which `registry/serializers/alerts.py` serialises. The id of such a dict
names the category and the row it was derived from, so that a client can
recognise and dedupe an alert while the state behind it changes.
"""
from datetime import datetime, timezone

from django.db.models import Count, F, OuterRef, Q, Subquery
from django.utils.translation import gettext_lazy as _
from extras.scheduling import run_overdue
from guardian.shortcuts import get_objects_for_user
from registry.enums.alerts import ServiceAlertCategory, ServiceAlertSeverity
from registry.enums.harvesting import HarvestingPhaseEnum
from registry.enums.update import UpdateJobStatusEnum
from registry.models.harvest import HarvestingJob
from registry.models.monitoring import (CatalogueServiceMonitoringRun,
                                        CatalogueServiceMonitoringSetting,
                                        WebFeatureServiceMonitoringRun,
                                        WebFeatureServiceMonitoringSetting,
                                        WebMapServiceMonitoringRun,
                                        WebMapServiceMonitoringSetting)
from registry.models.service import (CatalogueService, WebFeatureService,
                                     WebMapService)
from registry.models.update import (CatalogueServiceUpdateJob,
                                    CatalogueServiceUpdateSetting,
                                    WebFeatureServiceUpdateJob,
                                    WebFeatureServiceUpdateSetting,
                                    WebMapServiceUpdateJob,
                                    WebMapServiceUpdateSetting)

#: the datetime an alert without a point in time is sorted at, which is the
#: earliest of all and therefore the last of a list which is sorted newest first
NO_OCCURRED_AT = datetime.min.replace(tzinfo=timezone.utc)

#: the state of an update job which an administrator has to decide about
REVIEW_STATUS = UpdateJobStatusEnum.REVIEW_REQUIRED.value

#: the state of an update job which came back broken
ERROR_STATUS = UpdateJobStatusEnum.ERROR.value

#: the phase of a harvesting job which ended before it was done
ABORTED_PHASE = HarvestingPhaseEnum.ABORTED.value


class ServiceKind:
    """Everything which decides about the attention of one kind of service.

    The attention of a service is derived from models which exist per kind of
    service, so a collector needs the models of the kind it looks at. They are
    not looked up by name on the way, because a collector answers the kind of a
    service as the type of its resource.
    """

    def __init__(self, service, monitoring_setting, monitoring_run,
                 update_setting, update_job):
        self.service = service
        self.monitoring_setting = monitoring_setting
        self.monitoring_run = monitoring_run
        self.update_setting = update_setting
        self.update_job = update_job


#: the kinds of service which the registry monitors and updates
SERVICE_KINDS = (
    ServiceKind(
        service=WebMapService,
        monitoring_setting=WebMapServiceMonitoringSetting,
        monitoring_run=WebMapServiceMonitoringRun,
        update_setting=WebMapServiceUpdateSetting,
        update_job=WebMapServiceUpdateJob),
    ServiceKind(
        service=WebFeatureService,
        monitoring_setting=WebFeatureServiceMonitoringSetting,
        monitoring_run=WebFeatureServiceMonitoringRun,
        update_setting=WebFeatureServiceUpdateSetting,
        update_job=WebFeatureServiceUpdateJob),
    ServiceKind(
        service=CatalogueService,
        monitoring_setting=CatalogueServiceMonitoringSetting,
        monitoring_run=CatalogueServiceMonitoringRun,
        update_setting=CatalogueServiceUpdateSetting,
        update_job=CatalogueServiceUpdateJob),
)


#: the kind of a service by its model, so that the alerts of a service know the
#: models which decide about them
SERVICE_KIND_OF = {kind.service: kind for kind in SERVICE_KINDS}

#: the kind of service whose records are pulled by a harvesting job
HARVESTED_KIND = CatalogueService


def build_alert(category, service, resource, message, occurred_at=None,
                severity=ServiceAlertSeverity.WARNING):
    """Build the alert of one problem of one service.

    Args:
        category (ServiceAlertCategory): the state which needs attention
        service: the registered service the problem belongs to
        resource: the row which carries the problem, the point a client links to
        message (str): why this is a problem, translated
        occurred_at: when the problem appeared, optional
        severity (ServiceAlertSeverity): how much attention the state needs

    Returns:
        dict: the alert in the shape the serializer of an alert answers it
    """
    return {
        "id": f"{category.value}:{resource.pk}",
        "severity": severity.value,
        "category": category.value,
        "message": message,
        # the service and the row which carries the problem are addressed by
        # their type and their id, because they may belong to any kind of
        # service and a client has to know which resource to ask for either
        "service_type": service.__class__.__name__,
        "service": str(service.pk),
        "service_title": service.title,
        "resource_type": resource.__class__.__name__,
        "resource_id": str(resource.pk),
        "occurred_at": occurred_at,
    }


def registered_services(model):
    """QuerySet of the services of a model which are registered services.

    A service which is the candidate of an update is not a registered service
    but the copy an update job works with, so it is never answered as a service
    of its own - which also keeps the candidate of an update job out of the
    alerts which already report the job that produced it.

    Args:
        model: the model of the kind of service to look at

    Returns:
        QuerySet: the services which are registered
    """
    return model.objects.exclude(update_candidate_of__isnull=False)


def is_visible(service, user):
    """Whether the attention of a service may be answered to a user.

    Permission scoping is a requirement of the attention of a service: a user
    must not learn about a service which is not visible to them.

    Args:
        service: the registered service the alerts belong to
        user: the user which looks at the service

    Returns:
        bool: True if the alerts of the service may be answered to the user
    """
    if user is None or not user.is_authenticated or user.is_superuser:
        # attention is answered by a read only endpoint of the registry api,
        # which is open like every other read of the api is, and a superuser
        # may see every service of a deployment anyway
        return True
    return get_objects_for_user(
        user,
        f"registry.view_{service._meta.model_name}",
        klass=type(service),
        accept_global_perms=True).filter(pk=service.pk).exists()


def last_per_service(queryset, service_field):
    """Rows of a queryset which are the last row of their service.

    The attention of a service is decided by the state it is in *now*, which is
    the state its last run reports. The query is correlated per row instead of
    being windowed, because a service has few runs while a deployment may have
    many services.

    Args:
        queryset (QuerySet): the rows to narrow down, of one model
        service_field (str): path of the field which names the service

    Returns:
        QuerySet: the newest row of every service of this queryset
    """
    newest = queryset.model.objects.filter(
        **{service_field: OuterRef(service_field)}).order_by(
            "-date_created").values("pk")[:1]
    return queryset.annotate(
        newest_per_service=Subquery(newest)).filter(pk=F("newest_per_service"))


def monitoring_alerts(kind, service_ids):
    """Alerts of the services which their last monitoring run did not pass.

    Args:
        kind (ServiceKind): the kind of service to look at
        service_ids (QuerySet): the ids of the services to report about

    Returns:
        list: the alerts of the services with a failing last monitoring run
    """
    runs = last_per_service(
        kind.monitoring_run.objects.with_is_successful().select_related(
            "setting__service").filter(setting__service_id__in=service_ids),
        "setting__service")
    return [
        build_alert(
            ServiceAlertCategory.MONITORING_FAILED,
            run.setting.service,
            run,
            _("The last monitoring run of the service did not pass."),
            run.date_done or run.date_created,
            ServiceAlertSeverity.ERROR)
        for run in runs.filter(success=False)
    ]


def schedule_alerts(kind, service_ids):
    """Alerts of the services whose enabled schedules did not run.

    Whether a schedule is overdue is decided by extras.scheduling.run_overdue,
    which reads the crontab of the setting - the same rule a service answers its
    settings with. The schedules are decided in python because the time a run
    was expected at is calculated from a crontab expression.

    Args:
        kind (ServiceKind): the kind of service to look at
        service_ids (QuerySet): the ids of the services to report about

    Returns:
        list: the alerts of the services with an overdue schedule
    """
    schedulers = (
        (ServiceAlertCategory.MONITORING_OVERDUE, kind.monitoring_setting,
         _("The scheduled monitoring of the service did not run at the "
           "expected time.")),
        (ServiceAlertCategory.UPDATE_OVERDUE, kind.update_setting,
         _("The scheduled update of the service did not run at the expected "
           "time.")),
    )
    alerts = []
    for category, setting_model, message in schedulers:
        settings = setting_model.objects.select_related(
            "service", "crontab").filter(
                service_id__in=service_ids).exclude(enabled=False)
        for setting in settings.iterator():
            if not run_overdue(setting):
                continue
            alerts.append(build_alert(
                category, setting.service, setting, message,
                setting.next_run_expected_at))
    return alerts


def update_alerts(kind, service_ids):
    """Alerts of the services which their updates did not resolve.

    A job which waits for a review is a decision of an administrator, a job
    which errored is the fault of the remote service - they are answered as
    different categories of different severity, so that a client can separate
    the ones which need a click from the ones which need a fix.

    A service which never ran an update is not reported here: whether it was
    already expected to run is decided by its schedule, which `schedule_alerts`
    answers.

    Args:
        kind (ServiceKind): the kind of service to look at
        service_ids (QuerySet): the ids of the services to report about

    Returns:
        list: the alerts of the services with an unresolved last update job
    """
    jobs = last_per_service(
        kind.update_job.objects.select_related("service").filter(
            service_id__in=service_ids),
        "service")
    unresolved = {
        REVIEW_STATUS: (
            ServiceAlertCategory.UPDATE_REVIEW_REQUIRED,
            _("The update of the service waits for the confirmation of its "
              "mappings."),
            ServiceAlertSeverity.WARNING),
        ERROR_STATUS: (
            ServiceAlertCategory.UPDATE_FAILED,
            _("The last update of the service failed."),
            ServiceAlertSeverity.ERROR),
    }
    alerts = []
    for job in jobs:
        unresolved_job = unresolved.get(job.status)
        if unresolved_job is None:
            continue
        category, message, severity = unresolved_job
        alerts.append(build_alert(
            category, job.service, job, message,
            job.done_at or job.date_created, severity))
    return alerts


def harvesting_alerts(service_ids):
    """Alerts of the catalogues whose last harvesting run left work behind.

    A harvesting job which aborted and a job which imported records with an
    error both mean that the records of a catalogue are not up to date, while
    the reason to fix them differs - the phase of the job and the amount of
    records it could not import answer it.

    Args:
        service_ids (QuerySet): the ids of the catalogues to report about

    Returns:
        list: the alerts of the catalogues with an unfinished last harvest
    """
    jobs = last_per_service(
        HarvestingJob.objects.select_related("service").annotate(
            import_errors=Count(
                "temporary_md_metadata_file",
                filter=Q(
                    temporary_md_metadata_file__has_import_error=True)),
        ).filter(service_id__in=service_ids, service__isnull=False),
        "service")
    alerts = []
    for job in jobs:
        if job.phase == ABORTED_PHASE:
            message = _(
                "The last harvesting run of the service was aborted.")
        elif job.import_errors:
            message = _(
                "The last harvesting run of the service left %(count)s "
                "records behind which could not be imported.") % {
                    "count": job.import_errors}
        else:
            continue
        alerts.append(build_alert(
            ServiceAlertCategory.HARVESTING_INCOMPLETE,
            job.service,
            job,
            message,
            job.done_at or job.date_created,
            ServiceAlertSeverity.ERROR))
    return alerts


class ServiceAlertList(list):
    """The alerts of a service, answered like a queryset is answered.

    The alerts are derived in python and therefore a list, but the pagination of
    the api counts the object it paginates through a `count()` which a list only
    answers for a given value. This list answers the amount of its alerts, so
    that the alerts of a service are counted and answered like every other list
    of the api.
    """

    def count(self, *args, **kwargs) -> int:
        """The amount of alerts of this list.

        Returns:
            int: the amount of alerts, no matter what the list is asked to count
        """
        return len(self)


def service_alerts(service):
    """All alerts of one registered service, worst first.

    Every collector of this module is asked for the service, so an alert
    disappears by itself as soon as the state behind it is fixed and a service
    without a problem is answered with an empty list.

    Args:
        service: the registered service to look at

    Returns:
        list: the alerts to attend to, errors before warnings and newest first
    """
    kind = SERVICE_KIND_OF[type(service)]
    service_ids = [service.pk]
    alerts = []
    alerts.extend(monitoring_alerts(kind, service_ids))
    alerts.extend(schedule_alerts(kind, service_ids))
    alerts.extend(update_alerts(kind, service_ids))
    if kind.service is HARVESTED_KIND:
        # only the records of a catalogue are pulled by a harvesting job
        alerts.extend(harvesting_alerts(service_ids))
    return worst_first(alerts)


def worst_first(alerts):
    """Order alerts by their severity and by the point in time they appeared.

    Sorting twice keeps the order stable: an error stays before a warning even
    when the warning appeared earlier, and the alerts of one severity are
    answered with the newest problem first.

    Args:
        alerts (list): the alerts to order

    Returns:
        ServiceAlertList: the alerts, errors first and newest first
    """
    ordered = sorted(
        alerts,
        key=lambda alert: alert["occurred_at"] or NO_OCCURRED_AT,
        reverse=True)
    return ServiceAlertList(sorted(
        ordered, key=lambda alert: alert["severity"]))
