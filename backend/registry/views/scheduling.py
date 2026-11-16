"""The side-effect-free draft preview of the schedule screens (#1327).

One POST, no persistence anywhere: the view reads the proposal, decides
permissions over the referenced service and setting, and asks the #1325
estimator what the proposal would mean. It never persists, starts a job,
registers or refreshes capabilities, executes probes, creates a
`MonitoringRun` or `UpdateJob` or `HarvestingJob`, sets a `PeriodicTask` or
touches the queue - the crontab of a proposal is an *unsaved*
`CrontabSchedule` whose Celery `schedule` property answers without a row,
which is the same path `registry.querys.capacity` takes for drafts. A
warning never rejects a save: validation errors stay with the save path,
this answer only informs.

The permission mirror of the actual CRUD path:

- previewing an existing setting requires `change` on that setting and
  `view` on its service (the run history of the service answers the
  elapsed part, so it must be visible to the caller);
- previewing a new setting requires the `add` permission on the setting
  kind and `view` on the target service - the pair that lets the caller
  save it through the nested route;
- the setting must be the setting of the answered service and operation,
  which keeps the endpoint from probing the runs of another organisation's
  service through a foreign setting.
"""
from datetime import timedelta
from uuid import uuid4

from camel_converter import to_snake
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema
from registry.enums.capacity import EstimateGapEnum, RunOperationEnum
from registry.models.service import (CatalogueService, WebFeatureService,
                                     WebMapService)
from registry.querys.capacity import (OVERLAP_QUALIFIER, SETTING_MODEL_OF,
                                      WORKER_TELEMETRY_GAP,
                                      ScheduleProposal,
                                      periodic_capacity_estimate)
from registry.serializers.scheduling import (
    WARNING_CODE_SCHEDULE_TIGHTER, SchedulePreviewRequestSerializer,
    SchedulePreviewSerializer, split_scheduling)
from rest_framework.exceptions import NotFound, PermissionDenied, \
    ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

#: the moment until which a preview answer may be trusted by the screen;
#: after it the answer is stale and the screen should ask again (#1327)
PREVIEW_VALIDITY = timedelta(seconds=120)

#: the service kinds a schedule can be previewed for
SERVICE_MODELS = {
    model.__name__: model
    for model in (WebMapService, WebFeatureService, CatalogueService)}


def _attributes(request):
    """The validated vocabulary of the draft, in python spelling.

    The JSON:API parser of the project hands on the *unwrapped* attributes
    of the document, already snake_cased; a body which arrived through a
    plain JSON parser still carries the document envelope. Both spellings
    end here as one flat dictionary.
    """
    data = request.data if isinstance(request.data, dict) else {}
    document = data.get('data')
    if isinstance(document, dict):
        # an unprocessed json:api document
        attributes = document.get('attributes')
        if not isinstance(attributes, dict):
            attributes = {key: value for key, value in document.items()
                          if key not in ('type', 'id', 'relationships')}
    else:
        attributes = {key: value for key, value in data.items()
                      if key not in ('type', 'id', 'relationships')
                      and not key.startswith('_')}
    return {to_snake(key): value for key, value in attributes.items()}


class SchedulingPreviewView(APIView):
    """What a proposed schedule would mean, answered without saving it."""

    http_method_names = ['post']
    permission_classes = [IsAuthenticated]
    #: The json:api type of the answer, named once for both directions: the
    #: JSON:API parser insists that the `type` of the request document is
    #: the resource name of the endpoint, and without this attribute it
    #: inflects the view class name and answers 409 before the draft is
    #: ever read. One proposal, one projection - request and answer share
    #: the type.
    resource_name = SchedulePreviewSerializer.Meta.resource_name

    def get_serializer(self, *args, **kwargs):
        """The serializer the view validates its draft with.

        The json:api error format names the offending field through the
        view's serializer; without this the field errors of the request
        serializer would answer as a detail without a pointer.
        """
        return SchedulePreviewRequestSerializer(*args, **kwargs)

    @extend_schema(
        operation_id='preview_scheduling',
        summary=_('Preview a proposed schedule without saving it'),
        description=_(
            'Read-only in effect: never persists, queues or dispatches '
            'anything. Answers the coming occurrences, the wait between '
            'them, the measured end-to-end durations of the service\'s '
            'completed runs and stable warning codes for the proposal.'),
        request=SchedulePreviewRequestSerializer,
        responses={200: SchedulePreviewSerializer})
    def post(self, request, *args, **kwargs):
        attributes = _attributes(request)
        serializer = SchedulePreviewRequestSerializer(data=attributes)
        serializer.is_valid(raise_exception=True)
        draft = serializer.validated_data
        user = request.user

        model = SERVICE_MODELS[draft['service_kind']]
        operation = RunOperationEnum(draft['operation'])
        setting_model = SETTING_MODEL_OF.get((model, operation))
        if setting_model is None:
            raise ValidationError({'operation': _(
                'This kind of service has no runs of this periodic '
                'operation.')})

        service = self._service_of(draft['service_id'], model, user)
        setting = self._setting_of(draft, setting_model, service, user)
        proposal = self._proposal_of(draft, attributes, setting)

        as_of = now()
        estimate = periodic_capacity_estimate(
            model.__name__, service.pk, operation,
            setting=setting, proposal=proposal, at=as_of)

        return Response(
            SchedulePreviewSerializer(_answer(
                estimate, draft, setting, as_of)).data,
            headers={'Cache-Control': 'no-store'})

    def _service_of(self, service_id, model, user):
        """The service of the preview, with its view permission decided."""
        service = model.objects.filter(pk=service_id).first()
        if service is None:
            raise NotFound(_(
                'No service of this kind answers under this id.'))
        if not user.has_perm(f'view_{model._meta.model_name}', service):
            raise PermissionDenied(_(
                'The view permission on the service is required to '
                'preview its schedules.'))
        return service

    def _setting_of(self, draft, setting_model, service, user):
        """The setting an edit previews, or None when the proposal does not
        exist yet - each answer with the permission the save path of the
        same family would ask."""
        if draft.get('setting_id') is None:
            # the full codename, as DRF's own permission classes ask the
            # global add permission on the save path of this serializer's
            # families
            if not user.has_perm('registry.add_'
                                 f'{setting_model._meta.model_name}'):
                raise PermissionDenied(_(
                    'The add permission on the setting kind is required '
                    'to preview a schedule which does not exist yet.'))
            return None
        setting = setting_model.objects.select_related(
            'crontab').filter(
                pk=draft['setting_id'], service_id=service.pk).first()
        if setting is None:
            raise ValidationError({'setting_id': _(
                'The answered setting is not the setting of this '
                'service and operation.')})
        if not user.has_perm(
                f'change_{setting_model._meta.model_name}', setting):
            raise PermissionDenied(_(
                'The change permission on the setting is required to '
                'preview an edit of it.'))
        return setting

    def _proposal_of(self, draft, attributes, setting):
        """The proposal the request states.

        Only attributes the request actually carries propose a change; the
        answered setting's values survive an omitted attribute.
        """
        fields, _embedded = split_scheduling(draft.get('scheduling') or '')
        enabled = (draft['enabled'] if 'enabled' in attributes
                   or setting is None else bool(setting.enabled))
        return ScheduleProposal(
            enabled=enabled,
            crontab=' '.join(fields) if fields else None,
            timezone=draft.get('timezone') or None,
            one_off=draft['one_off'] if 'one_off' in attributes else None,
            start_time=draft['start_time']
            if 'start_time' in attributes else None,
            expires=draft['expires'] if 'expires' in attributes else None)


def _answer(estimate, draft, setting, as_of):
    """The typed estimate as the vocabulary of the preview resource."""
    schedule = estimate.schedule
    elapsed = estimate.elapsed
    overlap = estimate.overlap

    codes = list(dict.fromkeys(tuple(schedule.gaps) + tuple(elapsed.gaps)))
    warnings = []
    for code in codes:
        if code not in ('queue_pair_missing', 'worker_telemetry_missing'):
            try:
                message = str(EstimateGapEnum(code).label)
            except ValueError:
                message = code
            warnings.append({'code': code, 'message': message})
    if overlap.potential_overlap:
        codes.append(WARNING_CODE_SCHEDULE_TIGHTER)
        warnings.append({
            'code': WARNING_CODE_SCHEDULE_TIGHTER,
            'message': str(OVERLAP_QUALIFIER)})

    scheduling = _scheduling_echo(draft, setting)
    return {
        'id': str(uuid4()),
        'operation': str(estimate.operation),
        'service_kind': str(estimate.service_kind),
        'service_id': str(estimate.service_id),
        'setting_id': getattr(setting, 'pk', None),
        'scheduling': scheduling,
        'enabled': schedule.enabled,
        'next_occurrences': list(schedule.next_occurrences),
        'interval_seconds': schedule.run_interval_seconds,
        'potential_overlap': overlap.potential_overlap,
        'overlap_basis': overlap.basis,
        'elapsed': {
            'evidence': elapsed.evidence,
            'p50_seconds': elapsed.median_seconds,
            'p95_seconds': elapsed.p95_seconds,
            'average_seconds': elapsed.average_seconds,
            'sample_count': elapsed.sample_count,
            'p95_minimum_samples': elapsed.p95_minimum_samples,
            'failed_count': elapsed.failed_count,
            'incomplete_count': elapsed.incomplete_count,
            'lookback_days': elapsed.lookback_days,
            'last_measurement_at': elapsed.last_measurement_at,
        },
        'warning_codes': codes,
        'warnings': warnings,
        'capacity': None,
        'capacity_reason': str(WORKER_TELEMETRY_GAP),
        'setting_revision': (getattr(setting, 'date_changed', None)
                             if setting is not None and setting.pk
                             else None),
        'as_of': as_of,
        'expires_at': as_of + PREVIEW_VALIDITY,
    }


def _scheduling_echo(draft, setting):
    """The crontab the answer was decided from, spelled as the form writes it."""
    fields, _ = split_scheduling(draft.get('scheduling') or '')
    timezone = draft.get('timezone')
    if fields is None:
        crontab = getattr(setting, 'crontab', None)
        if crontab is None:
            return None
        fields = [crontab.minute, crontab.hour, crontab.day_of_month,
                  crontab.month_of_year, crontab.day_of_week]
        timezone = timezone or (
            str(crontab.timezone) if crontab.timezone else None)
    echo = ' '.join(fields)
    return f'{echo} {timezone}' if timezone else echo
