"""The states of a service which need the attention of an administrator.

Nothing which is described here is stored. Every state which needs attention
already exists somewhere else - the result of the last monitoring run of a
service, the status of its last update job and the records its last harvesting
job left behind - so that the question "what has to be done about this service"
is decided in one place and answered by the same rules to every service, to the
api and to every report which may follow.

The states are answered as annotations of the services themselves, which keeps
them filterable, sortable and countable like every other attribute of a service
on existing service endpoints. The cross-service projection is answered by the
union which `service_alert_rows()` builds from these annotations and which
creates the view of the alerts in `registry/models/alerts.py`. Only the states
of the schedules stay calculated in python, because a crontab occurrence is not
answered by the database - the schedule which missed its time and the schedule
which is tighter than the run it schedules - see `extras/scheduling.py`.

A state is always decided by the newest run or job of a service, because the
attention of a service is the state it is in *now*: a service whose failing run
was followed by a passing one does not need attention any more.
"""
from camel_converter import to_camel
from django.db.models import (BooleanField, Case, CharField, Exists,
                              ExpressionWrapper, F, IntegerField, OuterRef, Q,
                              Subquery, Value, When)
from django.db.models.functions import Cast, Coalesce, Concat
from django.utils.translation import gettext_lazy as _
from registry.enums.harvesting import HarvestingPhaseEnum, LogKindEnum
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

#: the kind of a harvesting log which names records a page did not deliver
SHORT_PAGE_KIND = LogKindEnum.COUNT_MISSMATCH.value

#: the attributes which answer the attention of every kind of service. The
#: attributes which end in `_run` and `_job` answer *which* run or job decided
#: an alert as the identifier of that row - they are answered by the very
#: subqueries which decide the alert next to them, so that a state and its
#: reference can never disagree, and the serializers of the services expose
#: them as relationships to the records behind them, which `alert_records()`
#: loads for a whole page of services at once.
ALERT_ATTRIBUTES = (
    'has_alert',
    'monitoring_failed',
    'monitoring_failed_at',
    'monitoring_failed_run',
    'update_review_required',
    'update_review_required_at',
    'update_review_job',
    'update_failed',
    'update_failed_at',
    'update_failed_job',
)

#: the attributes which answer the attention of a catalogue in addition
HARVEST_ALERT_ATTRIBUTES = (
    'harvest_aborted',
    'harvest_incomplete',
    'harvest_failed_at',
    'harvest_job',
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


def newest_job(job_model, *conditions, **kwargs):
    """Jobs of the service an outer query names, newest first.

    Args:
        job_model: the model of the jobs of one kind of service
        *conditions: the states the jobs have to be in as Q objects, optional
        **kwargs: the state the jobs have to be in, optional

    Returns:
        QuerySet: the jobs of the outer service, the newest one first
    """
    return newest_row(job_model.objects.filter(*conditions, **kwargs), 'service_id')


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
        alert_newest_job=Subquery(newest_update_job.values('pk')[:1]),
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
        # a failing monitoring is decided by two rows which are the same row -
        # the newest run of the service answers the failing one, so the newest
        # run is the record behind the alert
        monitoring_failed_run=Case(
            When(failing_run, then=F('alert_newest_run')),
            output_field=IntegerField()),
        update_failed=is_true(failed_job),
        update_failed_at=Case(
            When(failed_job, then=F('alert_newest_job_moment'))),
        update_failed_job=Case(
            When(failed_job, then=F('alert_newest_job')),
            output_field=IntegerField()),
        update_review_required_at=F('alert_review_job_moment'),
        # an update can wait for a decision without a job which waits for it,
        # because only a candidate of an update dangles - nothing to decide
        # about at a job answers no job then
        update_review_job=F('alert_review_job_id'),
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
    a job which is not done with are answered apart: the first is a run which
    broke, the second is a run which left records behind - records it could not
    import into the registry or records its pages never received.

    Args:
        queryset: the queryset of catalogues to annotate
        kind (ServiceKind): the kind of service which is annotated

    Returns:
        QuerySet: the queryset with the harvest state of every catalogue
    """
    newest_harvest = newest_job(kind.harvesting_job)
    aborted_harvest = newest_job(kind.harvesting_job, phase=ABORTED_PHASE)
    # the name of the first query is the one of the reverse relation which stores
    # a record which the job could not import into the registry, the second one
    # asks the logs of the job which records its pages did not deliver; a run
    # which never got all its pages is as little a complete snapshot as a run
    # whose records broke on import (#690)
    incomplete_harvest = newest_job(
        kind.harvesting_job,
        Q(temporary_md_metadata_file__has_import_error=True) |
        Q(log__kind=SHORT_PAGE_KIND))

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
        harvest_job=Case(
            When(aborted | incomplete, then=F('alert_newest_harvest')),
            output_field=IntegerField()),
    )


def alert_records(services: list) -> dict:
    """Load the rows which decided the alerts of some services.

    The annotations of the alerts answer the deciding rows as identifiers,
    while a serializer which answers them as relationships needs the rows
    themselves. Fetching a row per service would ask the database once per
    alert of a page, so the identifiers of a page are collected and read in
    one query per kind of row instead - a page of services pays three queries
    at most, no matter how many services it holds.

    Args:
        services (list): the services of a page, annotated by `alert_annotations`

    Returns:
        dict: the rows behind the alerts, by the model of the row and its
            identifier
    """
    ids_by_model = {}

    def collect(model, identifier):
        if identifier is not None:
            ids_by_model.setdefault(model, set()).add(identifier)

    for service in services:
        kind = SERVICE_KIND_OF.get(type(service))
        if kind is None:
            continue
        collect(kind.monitoring_run,
                getattr(service, 'monitoring_failed_run', None))
        collect(kind.update_job, getattr(service, 'update_failed_job', None))
        collect(kind.update_job, getattr(service, 'update_review_job', None))
        if kind.harvesting_job is not None:
            collect(kind.harvesting_job,
                    getattr(service, 'harvest_job', None))

    return {
        model: {row.pk: row for row in model.objects.filter(pk__in=ids)}
        for model, ids in ids_by_model.items()
    }


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
    """Project visible published services and enabled schedules into alerts.

    The alerts which the states of the services answer are projected by the
    view of the alerts - one query which unions the annotations that the
    services themselves answer, see `registry/models/alerts.py`. The states of
    the schedules are not answered by that view, because a crontab is calculated
    in python and not by the database: the schedule which did not keep its time
    and the schedule which is tighter than the harvest it schedules are both
    projected from the settings here.
    """
    from extras.scheduling import (next_run_expected_at, run_overdue,
                                   schedule_is_tighter_than)
    from guardian.shortcuts import get_objects_for_user
    from registry.models import monitoring, update
    from registry.models.alerts import ServiceAlertView
    from registry.models.harvest import PeriodicHarvestingJob
    from registry.querys.harvest_history import harvest_durations

    scope = Q()
    visible = {}
    for model in SERVICE_KIND_OF:
        services = get_objects_for_user(
            user, f'registry.view_{model._meta.model_name}',
            klass=model.objects.filter(update_candidate_of__isnull=True))
        if not user.is_superuser:
            # the view of the alerts and the settings below both ask the
            # visible services: answer the visibility once, so that the
            # permission subqueries of get_objects_for_user are part of one
            # query instead of repeated by every query which uses the
            # queryset - the superuser needs none of it, guardian answers
            # without them
            ids = list(services.values_list('pk', flat=True))
            services = model.objects.filter(pk__in=ids)
            scope |= Q(service_type=model.__name__,
                       service__in=[str(pk) for pk in ids])
        visible[model] = services
    if user.is_superuser:
        alerts = list(ServiceAlertView.objects.all().values())
    else:
        alerts = list(ServiceAlertView.objects.filter(scope).values())
    for model in SERVICE_KIND_OF:
        resource = model.__name__
        settings = [
            (getattr(monitoring, resource + 'MonitoringSetting'), 'monitoring_overdue'),
            (getattr(update, resource + 'UpdateSetting'), 'update_overdue'),
        ]
        durations = {}
        if model is CatalogueService:
            settings.append((PeriodicHarvestingJob, 'harvest_overdue'))
            durations = harvest_durations(PeriodicHarvestingJob.objects.filter(
                enabled=True, service__in=visible[model]).values_list(
                    'service_id', flat=True))
        for setting_model, category in settings:
            for setting in setting_model.objects.filter(
                    enabled=True, service__in=visible[model]).select_related('crontab', 'service'):
                if run_overdue(setting):
                    alerts.append(service_alert(
                        setting.service, category, 'warning',
                        next_run_expected_at(setting), setting_model.__name__,
                        source=setting.pk))
                if setting_model is PeriodicHarvestingJob:
                    # a schedule which fires more often than a harvest takes is
                    # answered here and not by the view of the alerts, because
                    # its estimate is measured over the runs of a catalogue and
                    # a crontab is calculated in python - neither is answerable
                    # by the database (#693)
                    estimate = durations.get(setting.service_id) or {}
                    if schedule_is_tighter_than(setting, estimate.get('average')):
                        alerts.append(harvest_schedule_alert(setting, estimate))
    return alerts


def harvest_schedule_alert(setting, estimate):
    """The alert of a harvesting schedule which fires more often than a harvest takes.

    The warning names both numbers the state is decided by: the schedule as the
    administrator wrote it and the duration the harvests of its catalogue really
    took. It is a warning and never a rejected save, because the duration of a
    harvest drifts with the remote catalogue and the schedule stays the decision
    of the administrator (#693).

    Args:
        setting: the harvesting schedule which is tighter than the harvest
        estimate: the row which measured the harvests of its catalogue

    Returns:
        dict: the alert of that schedule
    """
    from extras.fields import CrontabStringField
    from extras.scheduling import format_duration
    return service_alert(
        setting.service, 'harvest_schedule_too_tight', 'warning',
        estimate['last_done'], type(setting).__name__, source=setting.pk,
        # the schedule is named by the same answer the api of a schedule gives
        # for it, so that the warning and the screen of the schedule cannot
        # name two different things
        message=_(
            'The schedule "%(schedule)s" harvests this catalogue more often '
            'than a harvest of it takes: the harvests which finished measured '
            '%(duration)s on average.') % {
                'schedule': CrontabStringField().to_representation(
                    setting.crontab),
                'duration': format_duration(estimate['average'])})


def service_alert(service, category, severity, occurred_at, target, source=None,
                  message=None):
    """One stable problem identity and its existing service workflow target.

    Args:
        service: the service the alert is about
        category (str): the state which answers the alert
        severity (str): the severity of the alert
        occurred_at: the moment the state is decided by
        target (str): the resource which owns the workflow of the alert
        source: the record which decided the state, to keep the identity of the
            alert of one record apart from the alert of another
        message: what the alert has to tell beyond the name of its state, when
            the state is more than the categories a service answers itself
    """
    resource = type(service).__name__
    # CSW updates have no dedicated settings tab; its overview owns that action.
    tab = '' if target == 'CatalogueServiceUpdateSetting' else target
    return {
        'id': f'{category}:{resource}:{source or service.pk}',
        'severity': severity, 'category': category,
        'message': message or category,
        'service_type': resource, 'service': str(service.pk),
        'service_title': service.title, 'resource_type': resource,
        'resource_id': str(service.pk), 'occurred_at': occurred_at,
        'target_path': f'/{resource}/{service.pk}/show/{tab}',
    }


def alert_branch(model, category: str, severity: str, at: str, target: str):
    """One category of alerts of one kind of service as alert rows.

    The rows of a branch are the services of its kind which answer this
    category - decided by the very annotations which the services themselves
    answer - projected into the identity, the message and the workflow target
    which `service_alert()` answers for a single alert, so that the union of
    the branches and the services cannot drift apart.

    Args:
        model: the model of the kind of service to project
        category (str): the name of the state which answers the alert
        severity (str): the severity which the alert of it has
        at (str): the attribute which names the moment of the alert
        target (str): the resource which owns the workflow of the alert

    Returns:
        QuerySet: the rows of this category, shaped as the view of the alerts
    """
    resource = model.__name__
    if target == 'HarvestingJob':
        tab = 'HarvestingJob'
    else:
        # CSW updates have no dedicated settings tab; its overview owns that
        # action - the same rule which service_alert() answers
        tab = '' if resource + target == 'CatalogueServiceUpdateSetting' \
            else resource + target
    # every column is answered as an `alert_` annotation: the services answer
    # their own fields, and the view maps its fields onto these columns
    rows = model.objects.filter(
        update_candidate_of__isnull=True
    ).with_alert_information().filter(**{category: True}).annotate(
        alert_id=Concat(Value(f'{category}:{resource}:'),
                        Cast('pk', CharField()), output_field=CharField()),
        alert_severity=Value(severity, output_field=CharField()),
        alert_category=Value(category, output_field=CharField()),
        alert_message=Value(category, output_field=CharField()),
        alert_service_type=Value(resource, output_field=CharField()),
        alert_service=Cast('pk', CharField()),
        alert_service_title=F('title'),
        alert_occurred_at=F(at),
        alert_service_path=Concat(
            Value(f'/{resource}/'), Cast('pk', CharField()),
            Value(f'/show/{tab}'), output_field=CharField()))
    if category == 'update_review_required' and model is not CatalogueService:
        # a review is decided about at the job which waits for it - unless
        # only a candidate is dangling, which asks about the service itself
        waiting = Q(alert_review_job_id__isnull=False)
        rows = rows.annotate(
            alert_resource_type=Case(
                When(waiting, then=Value(resource + 'UpdateJob')),
                default=Value(resource), output_field=CharField()),
            alert_resource_id=Case(
                When(waiting, then=Cast('alert_review_job_id', CharField())),
                default=Cast('pk', CharField()), output_field=CharField()),
            alert_target_path=Case(
                When(waiting, then=Concat(
                    Value(f'/{resource}UpdateJob/'),
                    Cast('alert_review_job_id', CharField()),
                    Value('/show'), output_field=CharField())),
                default='alert_service_path', output_field=CharField()))
    else:
        rows = rows.annotate(
            alert_resource_type=Value(resource, output_field=CharField()),
            alert_resource_id=Cast('pk', CharField()),
            alert_target_path=F('alert_service_path'))
    return rows.order_by().values(
        'alert_id', 'alert_severity', 'alert_category', 'alert_message',
        'alert_service_type', 'alert_service', 'alert_service_title',
        'alert_resource_type', 'alert_resource_id', 'alert_occurred_at',
        'alert_target_path')


def service_alert_rows():
    """The alerts of every kind of service as the rows of one relation.

    One branch per kind of service and category of alerts, answered by the
    annotations which the services themselves answer, united into the rows
    which the view of the alerts is created from - see
    `registry/models/alerts.py`.

    Returns:
        QuerySet: the rows of every alert a service of a deployment answers
    """
    branches = []
    for model in SERVICE_KIND_OF:
        for category, (severity, at, target) in ALERT_CATEGORIES.items():
            if target == 'HarvestingJob' \
                    and SERVICE_KIND_OF[model].harvesting_job is None:
                # only the records of a catalogue are pulled by a harvesting
                # job, so only a catalogue answers the state it leaves behind
                continue
            branches.append(
                alert_branch(model, category, severity, at, target))
    return branches[0].union(*branches[1:], all=True)
