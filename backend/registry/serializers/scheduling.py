"""The draft-preview contract of the scheduling screen (#1327).

The request serializer validates a *proposed* schedule the way the save
path of each setting family validates it - the five crontab fields the
monitoring and update forms take (`extras.fields.CrontabStringField`) and,
for the harvesting form, the optional timezone suffix it appends
(`system.fields.CrontabStringField`). It answers the very same field error
messages; nothing of it persists: the unsaved `CrontabSchedule` behind the
proposal is only asked for its `schedule` so that Celery's own cron parser
decides whether the fields are usable.

The response serializer answers what the proposal would mean: the coming
occurrences, the wait between them, the end-to-end durations the completed
runs of the same service measured (with their evidence quality), and the
stable warning codes - the machine-readable `EstimateGapEnum` values of the
estimator (#1325) plus `schedule_tighter_than_elapsed` for the #693 rule.
#1332 shows the saved schedules' warnings and must reuse exactly these
codes, severity and evidence semantics. A warning never rejects a save;
`capacity` is null with its reason while the phase-2 worker telemetry of
#1330 does not exist.
"""
from zoneinfo import ZoneInfo

import re

from django.utils.translation import gettext_lazy as _
from django_celery_beat.models import CrontabSchedule
from rest_framework.fields import (BooleanField, CharField, ChoiceField,
                                   DateTimeField, FloatField, IntegerField,
                                   ListField, ReadOnlyField)
from rest_framework.serializers import ValidationError
from rest_framework_json_api.serializers import Serializer
from rest_framework_json_api.utils import format_field_name
from system.fields import CRONTAB_TIME_REGEX, parse_timezone

#: the codes a preview answer may carry besides the estimator's gaps -
#: stable across #1327's preview and #1332's saved-schedule warnings
WARNING_CODE_SCHEDULE_TIGHTER = 'schedule_tighter_than_elapsed'

#: the field error of the monitoring and update save path
#  (`extras.fields.CrontabStringField`), answered word for word
MONITORING_CRONTAB_ERROR = (
    'Invalid crontab format \u2014 expected 5 fields: '
    'minute hour day month weekday')

#: the refusal of a timezone token the parser cannot resolve - answered as
#: this stable message only; what the parser itself said stays in the
#: exception chain and never reaches the caller (#1327, CodeQL)
TIMEZONE_ERROR = _(
    'Invalid timezone - expected an IANA timezone name or a UTC offset '
    'like UTC+2')

#: the refusal of five fields Celery cannot schedule, worded for the
#: screen without the parser's internal message (#1327, CodeQL)
CRONTAB_UNUSABLE_ERROR = _(
    'Invalid crontab - the fields are no schedule Celery can run')


def timezone_name(token):
    """The ZoneInfo name behind a timezone token as the forms write it.

    Accepts the IANA names and the `UTC+2` spelling the harvesting form
    appends, resolving the latter the same way `system.fields` does, so the
    estimator - which asks `ZoneInfo` by name - gets a name it can load.
    """
    try:
        zone = parse_timezone(token)
    except (ValueError, KeyError) as error:
        # the parser's own wording stays in the chain; the caller gets the
        # stable message, so no internal detail flows into a response
        raise ValidationError(TIMEZONE_ERROR) from error
    return getattr(zone, 'key', str(zone))


def split_scheduling(scheduling):
    """The five crontab fields and the resolved timezone name of a string.

    Answers (None, None) for an empty string - an edit which only flips
    `enabled` carries no crontab and keeps the current one. The caller must
    have validated the string before (the request serializer does).
    """
    data = (scheduling or '').strip()
    if not data:
        return None, None
    match = re.fullmatch(CRONTAB_TIME_REGEX, data)
    if match is None:
        return None, None
    groups = match.groupdict()
    fields = [groups['minute'], groups['hour'], groups['day_of_month'],
              groups['month_of_year'], groups['day_of_week']]
    token = groups.get('timezone')
    return fields, (timezone_name(token) if token else None)


class SchedulePreviewRequestSerializer(Serializer):
    """The unsaved draft a schedule screen proposes, validated not persisted.

    `scheduling` is the five-field crontab as the form writes it; the
    harvesting family may carry the timezone inside the string as its save
    path accepts, the other families take a timezone only through the
    separate `timezone` attribute. Without `scheduling` the current crontab
    of `setting_id` answers, so an edit which only flips `enabled` can be
    previewed too.
    """

    operation = ChoiceField(
        choices=('monitoring', 'update', 'harvest'),
        label=_('operation'),
        help_text=_("the periodic operation the setting schedules."),
    )
    service_kind = ChoiceField(
        choices=('WebMapService', 'WebFeatureService', 'CatalogueService'),
        label=_('service kind'),
        help_text=_("the kind of the service the setting belongs to."),
    )
    service_id = CharField(
        label=_('service id'),
        help_text=_("the service the proposed setting would schedule."),
    )
    setting_id = IntegerField(
        required=False, allow_null=True,
        label=_('setting id'),
        help_text=_("the setting being edited; absent previews a new one."),
    )
    scheduling = CharField(
        required=False, allow_blank=True,
        label=_('scheduling'),
        help_text=_(
            "the proposed crontab: five fields \"minute hour day-of-month "
            "month day-of-week\", with the timezone suffix the harvesting "
            "form writes."),
    )
    timezone = CharField(
        required=False, allow_blank=True,
        label=_('timezone'),
        help_text=_(
            "the timezone the crontab runs in; the current schedule's by "
            "default, UTC without one."),
    )
    enabled = BooleanField(
        required=False, default=True,
        label=_('enabled'),
        help_text=_("whether the proposed schedule dispatches."),
    )
    one_off = BooleanField(
        required=False, default=False,
        label=_('one off'),
        help_text=_("whether the setting fires only once."),
    )
    start_time = DateTimeField(
        required=False, allow_null=True,
        label=_('start time'),
        help_text=_("the earliest moment the schedule may dispatch."),
    )
    expires = DateTimeField(
        required=False, allow_null=True,
        label=_('expires'),
        help_text=_("the moment after which the schedule stops dispatching."),
    )

    def validate(self, attrs):
        """Decide the proposed crontab with the canonical Celery parser.

        The five-field rule and the error wording belong to the save path
        of the answered family; what is added here is that an unsaved
        `CrontabSchedule` must hand out a usable Celery `schedule`, which
        is exactly what the preview asks of it later - so fields Celery
        rejects answer as field errors here instead of as a degraded
        estimate there. Nothing of it touches the database.
        """
        scheduling = (attrs.get('scheduling') or '').strip()
        timezone = (attrs.get('timezone') or '').strip()
        if not scheduling:
            return self._validate_answered_setting(attrs, timezone)
        return self._validate_proposal(attrs, scheduling, timezone)

    def _validate_answered_setting(self, attrs, timezone):
        """The answer for a request without a crontab: only the setting that
        already exists may be previewed without one."""
        if timezone:
            attrs['timezone'] = timezone_name(timezone)
        if not attrs.get('setting_id'):
            raise ValidationError({'scheduling': _(
                'A new schedule needs the crontab it proposes; only '
                'an existing setting may be previewed without one.')})
        return attrs

    def _validate_proposal(self, attrs, scheduling, timezone):
        """The answer for a proposed crontab, by the operation's own grammar."""
        harvest = attrs.get('operation') == 'harvest'
        match = re.fullmatch(CRONTAB_TIME_REGEX, scheduling)
        parts = scheduling.split()
        if match is None or (not harvest and len(parts) != 5):
            # answered word for word as the save path of the family answers
            raise ValidationError({'scheduling': (
                f'Invalid crontab string format: {scheduling}'
                if harvest else MONITORING_CRONTAB_ERROR)})
        embedded = self._embedded_timezone(
            match.groupdict().get('timezone'), harvest)
        resolved = timezone_name(timezone) if timezone else embedded
        crontab = CrontabSchedule(
            minute=match.groupdict()['minute'],
            hour=match.groupdict()['hour'],
            day_of_month=match.groupdict()['day_of_month'],
            month_of_year=match.groupdict()['month_of_year'],
            day_of_week=match.groupdict()['day_of_week'],
            timezone=ZoneInfo(resolved or 'UTC'))
        try:
            # Celery's own parser decides whether the fields are usable
            crontab.schedule
        except Exception as error:
            # its message may name internals; the screen gets the stable
            # wording on the field it asked about instead
            raise ValidationError(
                {'scheduling': CRONTAB_UNUSABLE_ERROR}) from error
        if resolved:
            attrs['timezone'] = resolved
        attrs['scheduling'] = scheduling
        return attrs

    def _embedded_timezone(self, embedded, harvest):
        """The timezone a crontab string names itself: the harvest form may
        write it and asks it of the string, the monitoring and update forms
        write five fields only, so one there is the format error."""
        if not embedded:
            return None
        if not harvest:
            raise ValidationError({'scheduling': MONITORING_CRONTAB_ERROR})
        return timezone_name(embedded)


class CamelNestedSerializer(Serializer):
    """A nested object answered in the camel case of the resource.

    The json:api renderer names the attributes of the resource in camel
    case but leaves the value of a nested object untouched; the screen
    reads these ones by camel case keys, so they are answered in the very
    spelling the renderer would have used (`format_field_name` is the
    renderer's own formatter).
    """

    def to_representation(self, instance):
        """Answer the nested object in the camel case of the resource."""
        answered = super().to_representation(instance)
        return {format_field_name(name): value
                for name, value in answered.items()}


class ElapsedEvidenceSerializer(CamelNestedSerializer):
    """The end-to-end durations the completed comparable runs measured.

    Every number answers only while its evidence allows it (#1325): the
    median and p95 are measured inside the lookback window, the average is
    the #693-compatible average over comparable runs of any age and is
    never presented as a p95.
    """

    evidence = CharField(read_only=True)
    p50_seconds = FloatField(read_only=True, allow_null=True)
    p95_seconds = FloatField(read_only=True, allow_null=True)
    average_seconds = FloatField(read_only=True, allow_null=True)
    sample_count = IntegerField(read_only=True)
    p95_minimum_samples = IntegerField(read_only=True)
    failed_count = IntegerField(read_only=True)
    incomplete_count = IntegerField(read_only=True)
    lookback_days = IntegerField(read_only=True)
    last_measurement_at = DateTimeField(read_only=True, allow_null=True)


class ScheduleSuggestionSerializer(CamelNestedSerializer):
    """One entire alternative crontab which keeps the answered cadence.

    The cadence fields are the verified ones (#1328): the firing count was
    decided for original and alternative over the very same dated horizon
    by the canonical occurrence walk, and the worker-second numbers come
    from the measured costs of the deployment snapshot of #1326 - with
    their sample count, never as a claim of a free slot.
    """

    #: the five fields "minute hour day-of-month month day-of-week"
    crontab = CharField(read_only=True)
    #: the answered schedule's own zone - a suggestion never moves it
    timezone = CharField(read_only=True)
    horizon_days = IntegerField(read_only=True)
    horizon_start = DateTimeField(read_only=True)
    horizon_end = DateTimeField(read_only=True)
    #: firings both schedules count inside the horizon - verified equal
    firing_count = IntegerField(read_only=True)
    queue = CharField(read_only=True)
    original_worker_seconds = FloatField(read_only=True)
    expected_worker_seconds = FloatField(read_only=True)
    sample_count = IntegerField(read_only=True)
    cost_coverage = FloatField(read_only=True)
    snapshot_at = DateTimeField(read_only=True)
    reason = CharField(read_only=True)


class WarningSerializer(Serializer):
    """One informational warning: its stable code and its readable reason."""

    code = CharField(read_only=True)
    message = CharField(read_only=True)


class SchedulePreviewSerializer(Serializer):
    """What a proposed schedule would mean, answered without saving it.

    The answer is a projection, not a stored resource: it carries no url,
    and none of its warnings rejects a save. The `as_of` moment and the
    `setting_revision` let the screen notice that the draft or the setting
    moved on since the answer and ask again.
    """

    id = CharField(read_only=True)
    operation = CharField(read_only=True)
    service_kind = CharField(read_only=True)
    service_id = CharField(read_only=True)
    setting_id = IntegerField(read_only=True, allow_null=True)
    #: the crontab the answer was decided from, timezone suffix included
    scheduling = CharField(read_only=True, allow_null=True)
    enabled = BooleanField(read_only=True)
    next_occurrences = ListField(
        child=DateTimeField(), read_only=True)
    interval_seconds = FloatField(read_only=True, allow_null=True)
    potential_overlap = BooleanField(read_only=True, allow_null=True)
    overlap_basis = CharField(read_only=True, allow_null=True)
    elapsed = ElapsedEvidenceSerializer(read_only=True)
    warning_codes = ListField(child=CharField(), read_only=True)
    warnings = ListField(child=WarningSerializer(), read_only=True)
    #: entire alternative crontabs which keep the cadence of the proposal
    #: - answered from the verified capacity data of #1326, empty with its
    #: reason whenever that data or the cadence check does not underpin it
    suggestions = ListField(
        child=ScheduleSuggestionSerializer(), read_only=True)
    suggestions_reason = CharField(read_only=True, allow_null=True)
    suggestions_reason_code = CharField(read_only=True, allow_null=True)
    #: the whole local days the cadence was evaluated over - the documented
    #: horizon, traveling with suggestions and refusals alike
    suggestions_horizon_days = IntegerField(read_only=True, allow_null=True)
    #: phase-2 only: null while no reliable capacity telemetry exists
    capacity = ReadOnlyField(allow_null=True)
    capacity_reason = CharField(read_only=True)
    #: the change moment of the setting the preview was decided against,
    #: null for a new one - the screen uses it to notice a concurrent edit
    setting_revision = DateTimeField(read_only=True, allow_null=True)
    as_of = DateTimeField(read_only=True)
    expires_at = DateTimeField(read_only=True)

    class Meta:
        resource_name = 'SchedulingPreview'
