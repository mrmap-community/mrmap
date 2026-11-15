"""The read representation of the schedule warnings of a saved setting.

`registry.querys.schedule_warnings` decides the recurrence risk of a persisted
schedule; this module is how the settings endpoints answer it: a
`scheduleWarnings` attribute next to the schedule itself, so the lists of
monitoring, update and harvesting settings - and the detail panels which reuse
them - show the state of a saved schedule without opening an edit form
(#1332).

The attribute carries the codes and the safe message parameters which the
draft preview of #1327 shares; it is answered only for persisted settings,
never for a draft, and it blocks nothing: a valid schedule stays saveable
however tight its schedule is.

The answer of a list is batched: the viewset reads the whole page at once
(`registry.views.schedule_warnings.ScheduleWarningsViewsetMixin`) and hands it to the
serializers through the serializer context; a single read answers its own row
alone. Like the other python-decided answers of the schedules, the attribute
is gated by the sparse fieldset of the request where the endpoint knows one:
a screen which shows no warning pays for no evidence query (#1082 pattern).
"""
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema_field
from registry.querys.schedule_warnings import schedule_warnings_by_id
from rest_framework_json_api.serializers import (ModelSerializer,
                                                 SerializerMethodField)

#: the attribute every scheduled setting answers, for their Meta.fields
SCHEDULE_WARNING_ATTRIBUTES = ('schedule_warnings',)


@extend_schema_field({
    'type': 'array',
    'nullable': True,
    'description': (
        'the schedule warnings of this persisted setting, empty if it needs '
        'no attention; nothing only while the request did not ask the answer '
        'of a screen which shows none'),
    'items': {
        'type': 'object',
        'properties': {
            'code': {
                'type': 'string',
                'enum': [
                    'schedule_overdue', 'schedule_too_tight',
                    'insufficient_evidence', 'schedule_expired'],
                'description': (
                    'the stable state which decided this warning, shared '
                    'with the draft preview of #1327'),
            },
            'severity': {
                'type': 'string',
                'enum': ['warning', 'info'],
                'description': (
                    'warning for a schedule which cannot keep its promise, '
                    'info for a muted state like an inadequate evidence base'),
            },
            'interval': {
                'type': 'string',
                'nullable': True,
                'description': (
                    'the wait between two runs as "H:MM:SS", or nothing '
                    'while the schedule answers no next run'),
            },
            'observedDuration': {
                'type': 'string',
                'nullable': True,
                'description': (
                    'the measured average duration of the finished runs as '
                    '"H:MM:SS", nothing without a reliable measurement'),
            },
            'sampleCount': {
                'type': 'integer',
                'nullable': True,
                'description': (
                    'how many finished runs the evidence counts, nothing '
                    'where the state is decided without evidence'),
            },
            'lastDoneAt': {
                'type': 'string',
                'format': 'date-time',
                'nullable': True,
                'description': (
                    'the end of the newest run which measured the evidence'),
            },
            'expectedAt': {
                'type': 'string',
                'format': 'date-time',
                'nullable': True,
                'description': (
                    'the moment an overdue schedule was expected at'),
            },
            'expiredAt': {
                'type': 'string',
                'format': 'date-time',
                'nullable': True,
                'description': (
                    'the moment an expired schedule passed its validity'),
            },
            'unknownReason': {
                'type': 'string',
                'nullable': True,
                'enum': ['no_completed_runs', 'too_few_samples', None],
                'description': (
                    'why an "insufficient_evidence" answer cannot be decided '
                    'against measured runs'),
            },
            'computedAt': {
                'type': 'string',
                'format': 'date-time',
                'description': (
                    'the moment this answer was decided at - the answer is '
                    'computed at the read, so a relevant change is reflected '
                    'by the next request'),
            },
        },
        'required': ['code', 'severity', 'computedAt'],
    },
})
class ScheduleWarningsField(SerializerMethodField):
    """The warning rows of a schedule, typed for the OpenAPI schema."""


class ScheduleWarningsSerializerMixin(ModelSerializer):
    """Answers the schedule warnings of a persisted setting.

    The rows are read per page by `registry.querys.schedule_warnings` and
    handed over by the viewset through the context; a serializer without that
    context - a single read - answers its own row alone. Concrete settings
    serializers inherit the declaration and name `schedule_warnings` in their
    Meta.fields, like `ServiceAlertSerializerMixin` does for the services.
    """

    schedule_warnings = ScheduleWarningsField(
        label=_("schedule warnings"),
        help_text=_(
            "the recurrence-risk states of this saved schedule: a tighter "
            "interval than the runs it schedules measurably take, a run "
            "which missed its time, an expired validity or an evidence base "
            "too small to judge - answered as stable codes with safe "
            "parameters, empty if the schedule needs no attention. A "
            "warning never blocks a save."),
        read_only=True)

    def _answers_schedule_warnings(self) -> bool:
        """Whether the request of this answer wants the warnings at all.

        The evidence query and the crontab decision are only paid for a
        request which asks the answer - the same sparse-field gate which
        decides the next-run answers of the schedules (#1082). An endpoint
        which knows no sparse fieldset always answers.
        """
        view = self.context.get("view")
        check = getattr(view, "check_sparse_fields_contains", None)
        return True if check is None else check("scheduleWarnings")

    def get_schedule_warnings(self, obj):
        if not self._answers_schedule_warnings():
            return None
        batch = self.context.get("schedule_warnings")
        if batch is not None:
            return batch.get(obj.pk, [])
        return schedule_warnings_by_id([obj]).get(obj.pk, [])

    class Meta:
        abstract = True
