"""The states of a service which need the attention of an administrator.

Nothing which is described here is stored. Every state which needs attention
already exists somewhere else - the result of the last monitoring run of a
service, the status of its last update job and the records its last harvesting
job left behind - so that the question "what has to be done about this service"
is decided in one place and answered by the same rules to every service, to the
api and to every report which may follow.

The states are answered as annotations of the services themselves, which keeps
them filterable, sortable and countable like every other attribute of a service
on existing service endpoints. The cross-service projection below reuses these
annotations and the scheduling helper behind the settings' `runOverdue` field;
cron occurrences are calculated in Python.

A state is always decided by the newest run or job of a service, because the
attention of a service is the state it is in *now*: a service whose failing run
was followed by a passing one does not need attention any more.
"""
from camel_converter import to_camel
from django.db.models import (BooleanField, Case, Exists, ExpressionWrapper, F,
                              OuterRef, Q, Subquery, Value, When)
from django.db.models.functions import Coalesce
from registry.enums.harvesting import HarvestingPhaseEnum
from registry.enums.update import UpdateJobStatusEnum
from registry.models.harvest import HarvestingJob
from registry.models.monitoring import (CatalogueServiceMonitoringRun,
                                        WebFeatureServiceMonitoringRun,
                                        WebMapServiceMonitoringRun)
from registry.models.service import (CatalogueService, WebFeatureService,
                                     WebMapService)
from registry.models.update import (CatalogueServiceUpdateJob,
                                    WebFeatureServiceUpdateJob,
                                    WebMapServiceUpdateJob)

#: the state of an update job which an administrator has to decide about
REVIEW_STATUS = UpdateJobStatusEnum.REVIEW_REQUIRED.value

#: the state of an update job which came back broken
ERROR_STATUS = UpdateJobStatusEnum.ERROR.value

#: the phase of a harvesting job which ended before it was done
ABORTED_PHASE = HarvestingPhaseEnum.ABORTED.value

#: the attributes which answer the attention of every kind of service
ALERT_ATTRIBUTES = (
    'has_alert',
    'monitoring_failed',
    'monitoring_failed_at',
    'update_review_required',
    'update_review_required_at',
    'update_failed',
    'update_failed_at',
)

#: the attributes which answer the attention of a catalogue in addition
HARVEST_ALERT_ATTRIBUTES = (
    'harvest_aborted',
    'harvest_incomplete',
    'harvest_failed_at',
)


class ServiceKind:
    """Everything which decides about the attention of one kind of service.

    The attention of a service is derived from models which exist per kind of
    service, so the annotations need the models of the kind they look at. They
    are not looked up by name on the way, because a wrong name would only show
    up as an exception while a request is answered.
    """

    def __init__(self, service, monitoring_run, update_job,
                 harvesting_job=None):
        self.service = service
        self.monitoring_run = monitoring_run
        self.update_job = update_job
        self.harvesting_job = harvesting_job

    @property
    def attributes(self) -> tuple:
        """The attributes which answer the attention of this kind of service.

        Returns:
            tuple: the names to annotate and to serialize for this kind
        """
        if self.harvesting_job is None:
            return ALERT_ATTRIBUTES
        return ALERT_ATTRIBUTES + HARVEST_ALERT_ATTRIBUTES


#: the kind of a service by its model
SERVICE_KIND_OF = {
    kind.service: kind for kind in (
        ServiceKind(
            service=WebMapService,
            monitoring_run=WebMapServiceMonitoringRun,
            update_job=WebMapServiceUpdateJob),
        ServiceKind(
            service=WebFeatureService,
            monitoring_run=WebFeatureServiceMonitoringRun,
            update_job=WebFeatureServiceUpdateJob),
        ServiceKind(
            service=CatalogueService,
            monitoring_run=CatalogueServiceMonitoringRun,
            update_job=CatalogueServiceUpdateJob,
            harvesting_job=HarvestingJob),
    )
}


def has_alert_annotations(queryset) -> bool:
    """Whether the alerts already are annotated to a queryset of services.

    A viewset answers a request on the queryset it builds, but it checks the
    permissions of the services of that request on the queryset it holds - and
    the filters and the sort of the request are applied to both. So the alerts
    are annotated where both paths meet, see `alerts_requested()`.

    Args:
        queryset: the queryset of one kind of service to look at

    Returns:
        bool: True if every attribute of the attention is annotated
    """
    kind = SERVICE_KIND_OF.get(queryset.model)
    if kind is None:
        return False
    return all(name in queryset.query.annotations for name in kind.attributes)


def is_true(condition) -> ExpressionWrapper:
    """A condition which answers False instead of nothing if it is not met.

    The attention of a service is answered by subqueries which are empty for a
    service without any run or job, and an empty subquery compares to nothing -
    not even to itself. Every flag of the attention is answered through here, so
    that a service without a problem answers False and not nothing.

    Args:
        condition (Q): the condition to answer

    Returns:
        ExpressionWrapper: the condition, answered as the boolean it is
    """
    return Coalesce(
        ExpressionWrapper(condition, output_field=BooleanField()),
        Value(False),
        output_field=BooleanField(),
    )


def newest_row(queryset, service_field: str):
    """Rows of the service an outer query names, newest first.

    Args:
        queryset: the rows to narrow down, of one model
        service_field (str): path which names the service of a row

    Returns:
        QuerySet: the rows of the outer service, the newest one first
    """
    return queryset.filter(
        **{service_field: OuterRef('pk')}).order_by('-date_created')


def newest_run(run_model, failing: bool = False):
    """Runs of the service an outer query names, newest first.

    Whether a run reports a failure is decided by the probes it dispatched, so
    the success state which `with_is_successful()` annotates is the only rule
    which is asked here - a second definition of a failing run would drift away
    from the one which decides about the result of a monitoring run.

    Args:
        run_model: the model of the runs of one kind of service
        failing (bool): only answer the runs which did not pass, optional

    Returns:
        QuerySet: the runs of the outer service, the newest one first
    """
    runs = run_model.objects.all()
    if failing:
        runs = runs.with_is_successful().filter(success=False)
    return newest_row(runs, 'setting__service_id')


def newest_job(job_model, **conditions):
    """Jobs of the service an outer query names, newest first.

    Args:
        job_model: the model of the jobs of one kind of service
        **conditions: the state the jobs have to be in, optional

    Returns:
        QuerySet: the jobs of the outer service, the newest one first
    """
    return newest_row(job_model.objects.filter(**conditions), 'service_id')


def moment(queryset, field: str = 'done_at'):
    """Subquery of the point in time the newest row of a queryset happened at.

    A job which is still running has no point in time it is done at, so the
    moment it was created answers the alert until it is finished.

    Args:
        queryset: the rows to look at, newest first
        field (str): the field which names the point in time, optional

    Returns:
        Subquery: the point in time of the newest row of the queryset
    """
    return Subquery(queryset.annotate(
        alert_moment=Coalesce(F(field), F('date_created'))
    ).values('alert_moment')[:1])


def alert_annotations(queryset):
    """Annotate the states of the services which need attention.

    The rows which decide about the attention are annotated once and compared to
    each other: a service answers its newest run and its newest failing run, and
    it needs attention in monitoring as soon as these are the same row. This
    keeps the decision which run is the newest one in the database, where a
    service answers it with its other attributes.

    Args:
        queryset: the queryset of one kind of service to annotate

    Returns:
        QuerySet: the queryset with the attention of every service annotated

    Raises:
        KeyError: if the model of the queryset is no kind of service
    """
    kind = SERVICE_KIND_OF[queryset.model]

    newest = newest_run(kind.monitoring_run)
    newest_failing = newest_run(kind.monitoring_run, failing=True)
    newest_update_job = newest_job(kind.update_job)
    newest_review_job = newest_job(kind.update_job, status=REVIEW_STATUS)

    queryset = queryset.annotate(
        alert_newest_run=Subquery(newest.values('pk')[:1]),
        alert_newest_failing_run=Subquery(newest_failing.values('pk')[:1]),
        # a run names the point in time it was done with `date_done`, while a
        # job names it `done_at` - see the models of the runs and the jobs
        alert_newest_run_moment=moment(newest, field='date_done'),
        alert_newest_job_status=Subquery(
            newest_update_job.values('status')[:1]),
        alert_newest_job_moment=moment(newest_update_job),
        alert_review_job_moment=moment(newest_review_job),
        alert_review_job_id=Subquery(newest_review_job.values('pk')[:1]),
        update_review_required=(Exists(kind.update_job.objects.filter(
            service_id=OuterRef('pk'), status=REVIEW_STATUS)) | Exists(
                kind.service.objects.filter(update_candidate_of_id=OuterRef('pk')))),
    )

    failing_run = Q(alert_newest_run=F('alert_newest_failing_run'))
    failed_job = Q(alert_newest_job_status=ERROR_STATUS)

    queryset = queryset.annotate(
        monitoring_failed=is_true(failing_run),
        monitoring_failed_at=Case(
            When(failing_run, then=F('alert_newest_run_moment'))),
        update_failed=is_true(failed_job),
        update_failed_at=Case(
            When(failed_job, then=F('alert_newest_job_moment'))),
        update_review_required_at=F('alert_review_job_moment'),
    )

    if kind.harvesting_job is not None:
        queryset = annotate_harvest_alerts(queryset, kind)
        needs_attention = (
            Q(monitoring_failed=True) |
            Q(update_review_required=True) |
            Q(update_failed=True) |
            Q(harvest_aborted=True) |
            Q(harvest_incomplete=True)
        )
    else:
        needs_attention = (
            Q(monitoring_failed=True) |
            Q(update_review_required=True) |
            Q(update_failed=True)
        )

    return queryset.annotate(has_alert=is_true(needs_attention))


def annotate_harvest_alerts(queryset, kind: ServiceKind):
    """Annotate the records a harvesting job of a catalogue left behind.

    Only the records of a catalogue are pulled by a harvesting job, so these
    annotations exist for that kind of service only. A job which was aborted and
    a job which could not import records are answered apart, because the first
    is a run which broke while the second is a run which is not done with.

    Args:
        queryset: the queryset of catalogues to annotate
        kind (ServiceKind): the kind of service which is annotated

    Returns:
        QuerySet: the queryset with the harvest state of every catalogue
    """
    newest_harvest = newest_job(kind.harvesting_job)
    aborted_harvest = newest_job(kind.harvesting_job, phase=ABORTED_PHASE)
    # the name of the query is the one of the reverse relation which stores a
    # record which the job could not import into the registry
    incomplete_harvest = newest_job(
        kind.harvesting_job,
        temporary_md_metadata_file__has_import_error=True)

    queryset = queryset.annotate(
        alert_newest_harvest=Subquery(newest_harvest.values('pk')[:1]),
        alert_aborted_harvest=Subquery(aborted_harvest.values('pk')[:1]),
        alert_incomplete_harvest=Subquery(
            incomplete_harvest.values('pk')[:1]),
        alert_newest_harvest_moment=moment(newest_harvest),
    )

    aborted = Q(alert_newest_harvest=F('alert_aborted_harvest'))
    incomplete = Q(alert_newest_harvest=F('alert_incomplete_harvest'))

    return queryset.annotate(
        harvest_aborted=is_true(aborted),
        harvest_incomplete=is_true(incomplete),
        harvest_failed_at=Case(
            When(aborted | incomplete,
                 then=F('alert_newest_harvest_moment'))),
    )


def alerts_requested(request, resource: str, attributes: tuple) -> bool:
    """Whether a request wants, filters or sorts the alerts of a service.

    The alerts of a service are answered by a subquery per attribute, so they are
    only added to a query which asks for them: a request which answers the
    attributes of a service, narrows the services by them or orders the services
    by them.

    Args:
        request: the request which is answered
        resource (str): name of the resource the request answers
        attributes (tuple): the names of the attributes which answer the alerts

    Returns:
        bool: True if the alerts have to be annotated to answer the request
    """
    names = set()
    for attribute in attributes:
        # a client names an attribute as the api names it, but the sparse fields
        # of a request are answered as the database names them
        names.add(attribute)
        names.add(to_camel(attribute))

    for name in names:
        if f'filter[{name}]' in request.GET or name in request.GET.get('sort', ''):
            return True

    sparse_fields = [
        field.strip() for field in request.GET.get(
            f'fields[{resource}]', '').split(',') if field.strip()]
    return not sparse_fields or any(name in sparse_fields for name in names)


# Cross-service projections deliberately reuse the annotations above. No alert
# state is persisted, and candidates are never counted as separate services.
ALERT_CATEGORIES = {
    'monitoring_failed': ('error', 'monitoring_failed_at', 'MonitoringSetting'),
    'update_failed': ('error', 'update_failed_at', 'UpdateSetting'),
    'update_review_required': ('warning', 'update_review_required_at', 'UpdateSetting'),
    'harvest_aborted': ('error', 'harvest_failed_at', 'HarvestingJob'),
    'harvest_incomplete': ('warning', 'harvest_failed_at', 'HarvestingJob'),
}


def collect_service_alerts(user):
    """Project visible published services and enabled schedules into alerts."""
    from extras.scheduling import next_run_expected_at, run_overdue
    from guardian.shortcuts import get_objects_for_user
    from registry.models import monitoring, update
    from registry.models.harvest import PeriodicHarvestingJob

    alerts = []
    for model in SERVICE_KIND_OF:
        resource = model.__name__
        visible = get_objects_for_user(
            user, f'registry.view_{model._meta.model_name}',
            klass=model.objects.filter(update_candidate_of__isnull=True))
        services = visible.with_alert_information().filter(has_alert=True)
        for service in services:
            for category, (severity, at, target) in ALERT_CATEGORIES.items():
                if getattr(service, category, False):
                    alert = service_alert(
                        service, category, severity, getattr(service, at),
                        target if target == 'HarvestingJob' else resource + target)
                    if category == 'update_review_required' and service.alert_review_job_id \
                            and model is not CatalogueService:
                        alert['resource_type'] = resource + 'UpdateJob'
                        alert['resource_id'] = str(service.alert_review_job_id)
                        alert['target_path'] = (
                            f"/{alert['resource_type']}/{alert['resource_id']}/show")
                    alerts.append(alert)
        settings = [
            (getattr(monitoring, resource + 'MonitoringSetting'), 'monitoring_overdue'),
            (getattr(update, resource + 'UpdateSetting'), 'update_overdue'),
        ]
        if model is CatalogueService:
            settings.append((PeriodicHarvestingJob, 'harvest_overdue'))
        for setting_model, category in settings:
            for setting in setting_model.objects.filter(
                    enabled=True, service__in=visible).select_related('crontab', 'service'):
                if run_overdue(setting):
                    alerts.append(service_alert(
                        setting.service, category, 'warning',
                        next_run_expected_at(setting), setting_model.__name__,
                        source=setting.pk))
    return alerts


def service_alert(service, category, severity, occurred_at, target, source=None):
    """One stable problem identity and its existing service workflow target."""
    resource = type(service).__name__
    # CSW updates have no dedicated settings tab; its overview owns that action.
    tab = '' if target == 'CatalogueServiceUpdateSetting' else target
    return {
        'id': f'{category}:{resource}:{source or service.pk}',
        'severity': severity, 'category': category, 'message': category,
        'service_type': resource, 'service': str(service.pk),
        'service_title': service.title, 'resource_type': resource,
        'resource_id': str(service.pk), 'occurred_at': occurred_at,
        'target_path': f'/{resource}/{service.pk}/show/{tab}',
    }
