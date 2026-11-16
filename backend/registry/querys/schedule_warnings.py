"""The recurrence risk of a *saved* schedule, answered per setting row.

An administrator should see that a saved monitoring, update or harvesting
schedule is too tight, missed its time or simply cannot be judged yet -
without opening the edit form and without saving anything (#1332). This module
is that answer: it decides the warning state of the settings of one page and
keys it by the identifier of the setting, so a list endpoint can hand the
state of its page to the serializers exactly the way the service alerts read
their references (`registry.querys.alerts.alert_records`).

The vocabulary is stable and shared with the draft preview of #1327: a warning
is a `code` out of `SCHEDULE_WARNING_CODES`, a `severity` of `warning` or
`info`, and safe, translatable-by-the-client message parameters - the interval,
the observed duration, the sample count and the moments which decided them.
No message text is decided here, so the same code reads identically in the
list, in the preview and in any later incidents view (#1104 may reference
these derived states without duplicating them).

The codes:

* `schedule_overdue` (warning) - an enabled schedule missed the run its own
  crontab promised (`extras.scheduling.run_overdue`);
* `schedule_too_tight` (warning) - the schedule fires more often than a run
  of it measurably takes (`extras.scheduling.schedule_is_tighter_than`, the
  rule of #693), judged only on a reliable number of finished runs;
* `insufficient_evidence` (info) - a schedule which runs and runs cannot be
  judged against: a muted informational state, never an operational failure;
* `schedule_expired` (info) - an enabled schedule whose validity has passed:
  it will never fire again, which is stale, not broken.

Disabled settings answer nothing - the screen already shows their flag, and a
warning would speak against a state the administrator chose deliberately.
The same rule which quiets them quiets a deleted setting with it: the answer
is computed at the read, from the persisted state alone, so an edited cron, a
freshly completed run, a deactivation or a deletion is reflected by the very
next request and nothing can go stale between two writes. There is no
schedule warning table and no second alert definition: the attention list of
#693 keeps owning its stored `ServiceAlert` rows (the categories
`monitoring_overdue`, `update_overdue`, `harvest_overdue` and
`harvest_schedule_too_tight` are unchanged), while this projection answers the
same conditions on the setting's own row, per row and page-bounded.

Bounded by construction: one aggregate query per page for the duration
evidence of the settings it holds, plus the python crontab decision for at
most the rows of that page - never a full history per row, a global alert
scan or any worker inspection (#1308).
"""
from django.db.models import (Avg, Count, DurationField, ExpressionWrapper,
                              F, Max)
from django.utils import timezone

from extras.scheduling import (format_duration, next_run_expected_at,
                               run_interval, run_overdue)
from registry.models.harvest import PeriodicHarvestingJob
from registry.models.monitoring import (CatalogueServiceMonitoringRun,
                                        CatalogueServiceMonitoringSetting,
                                        WebFeatureServiceMonitoringRun,
                                        WebFeatureServiceMonitoringSetting,
                                        WebMapServiceMonitoringRun,
                                        WebMapServiceMonitoringSetting)
from registry.models.update import (CatalogueServiceUpdateJob,
                                    CatalogueServiceUpdateSetting,
                                    WebFeatureServiceUpdateJob,
                                    WebFeatureServiceUpdateSetting,
                                    WebMapServiceUpdateJob,
                                    WebMapServiceUpdateSetting)
from registry.querys.harvest_history import harvest_durations

#: the warning which an enabled schedule which missed its promised dispatch is
SCHEDULE_OVERDUE = 'schedule_overdue'

#: the warning which a schedule that fires more often than a run takes is
SCHEDULE_TOO_TIGHT = 'schedule_too_tight'

#: the information which answers "no adequate history" - muted, never red
INSUFFICIENT_EVIDENCE = 'insufficient_evidence'

#: the information which answers an enabled schedule past its validity
SCHEDULE_EXPIRED = 'schedule_expired'

#: the severities a warning row may carry
WARNING = 'warning'
INFO = 'info'

#: the codes a client may be answered, with the severity each of them has -
#: the stable half of the vocabulary which the draft preview of #1327 shares
SCHEDULE_WARNING_CODES = {
    SCHEDULE_OVERDUE: WARNING,
    SCHEDULE_TOO_TIGHT: WARNING,
    INSUFFICIENT_EVIDENCE: INFO,
    SCHEDULE_EXPIRED: INFO,
}

#: the reasons why the evidence of a schedule answers nothing, as stable
#: parameters next to `insufficient_evidence`
NO_COMPLETED_RUNS = 'no_completed_runs'
TOO_FEW_SAMPLES = 'too_few_samples'

#: how many finished runs the duration of a kind of run needs before its
#: average is treated as a reliable basis for the tight-schedule warning.
#: Below it the answer is `insufficient_evidence` - an information, because
#: "not yet measurable" is no operational failure (#1332).
MIN_RELIABLE_SAMPLES = 3


def _durations_by_key(rows_queryset, key: str, done_field: str) -> dict:
    """The measured durations of finished runs, aggregated by one key.

    The duration of a run is the time from the moment it was made to the
    moment it ended - the same measure `harvest_durations` answers for a
    harvest and the runs of #1079 answer for themselves. Only runs which
    ended answer one; a catalogue-like "never finished anything" simply
    answers no row, so an invented estimate cannot be mistaken for a measured
    one.

    Args:
        rows_queryset: finished runs to aggregate, already narrowed down
        key (str): the value-name the rows are keyed by (`setting_id` or
            `service_id`)
        done_field (str): the name of the moment the run ended - the
            monitoring runs name it `date_done`, the update jobs `done_at`

    Returns:
        dict: the row of every key which finished runs, naming its average
            duration, the end of its newest run and the amount of runs
    """
    return {
        row[key]: row
        for row in rows_queryset.values(key).annotate(
            average=Avg(ExpressionWrapper(
                F(done_field) - F('date_created'),
                output_field=DurationField())),
            last_done=Max(done_field),
            samples=Count('pk'))
    }


#: how the duration evidence of every kind of scheduled setting is measured:
#: monitoring runs belong to their setting, update jobs and harvest runs to
#: the service - which is how the alerts of #1030 reach them as well
_MONITORING_RUN_OF = {
    WebMapServiceMonitoringSetting: WebMapServiceMonitoringRun,
    WebFeatureServiceMonitoringSetting: WebFeatureServiceMonitoringRun,
    CatalogueServiceMonitoringSetting: CatalogueServiceMonitoringRun,
}

_UPDATE_JOB_OF = {
    WebMapServiceUpdateSetting: WebMapServiceUpdateJob,
    WebFeatureServiceUpdateSetting: WebFeatureServiceUpdateJob,
    CatalogueServiceUpdateSetting: CatalogueServiceUpdateJob,
}


def duration_estimates(settings: list) -> dict:
    """The measured duration evidence of a page of settings, keyed per row.

    One aggregate query per kind of setting in the page - never one per row.
    Evidence which hangs on the service (update jobs, harvest runs) is read
    by the services of the page and handed back keyed by the setting, so the
    caller never has to care which side of the service a kind of run belongs
    to.

    Args:
        settings: the settings whose evidence is asked (one kind per call)

    Returns:
        dict: the estimate row of every setting with finished runs, keyed by
            the settings identifier, naming average, last_done and samples
    """
    if not settings:
        return {}
    model = type(settings[0])

    if model in _MONITORING_RUN_OF:
        measured = _durations_by_key(
            _MONITORING_RUN_OF[model].objects.filter(
                setting_id__in=[row.pk for row in settings],
                date_done__isnull=False,
                date_created__isnull=False,
            ), 'setting_id', 'date_done')
        return {row.pk: measured[row.pk]
                for row in settings if row.pk in measured}

    service_ids = {row.service_id for row in settings}
    if model in _UPDATE_JOB_OF:
        measured = _durations_by_key(
            _UPDATE_JOB_OF[model].objects.filter(
                service_id__in=service_ids,
                done_at__isnull=False,
                date_created__isnull=False,
            ), 'service_id', 'done_at')
    elif model is PeriodicHarvestingJob:
        measured = harvest_durations(service_ids)
    else:
        return {}
    return {row.pk: measured[row.service_id]
            for row in settings if row.service_id in measured}


def warnings_for_setting(setting, estimate, computed_at) -> list:
    """The warning rows which decide the recurrence risk of one setting.

    The rules are the ones of the attention list, answered from the shared
    helpers of `extras.scheduling` and not re-decided here: whether the
    schedule kept its time (`run_overdue`), how long it waits between its
    runs (`run_interval`) and whether a measured run fits into that wait. The
    estimate is what the finished runs of the settings service or setting
    measured - None, or fewer than `MIN_RELIABLE_SAMPLES` of them, is no
    basis for a warning, only for the muted `insufficient_evidence`.

    Args:
        setting: the persisted scheduled setting to answer
        estimate: the measured duration row of its runs, optional
        computed_at: the moment the whole answer was decided at

    Returns:
        list: the warning rows, warnings before informations, possibly empty
    """
    if not setting.enabled:
        # a deactivated schedule says itself on the screen; nothing to add
        return []
    current_time = computed_at
    expired = (setting.expires is not None and setting.expires <= current_time)

    interval = run_interval(setting)
    expected_at = next_run_expected_at(setting)

    rows = []
    if not expired and run_overdue(setting):
        rows.append({
            'code': SCHEDULE_OVERDUE,
            'severity': WARNING,
            'interval': format_duration(interval)
            if interval is not None else None,
            'observedDuration': None,
            'sampleCount': None,
            'lastDoneAt': None,
            'expectedAt': expected_at,
            'expiredAt': None,
            'unknownReason': None,
            'computedAt': current_time,
        })
    if expired:
        rows.append({
            'code': SCHEDULE_EXPIRED,
            'severity': INFO,
            'interval': None,
            'observedDuration': None,
            'sampleCount': None,
            'lastDoneAt': None,
            'expectedAt': None,
            'expiredAt': setting.expires,
            'unknownReason': None,
            'computedAt': current_time,
        })
        # an expired schedule answers no next run, so there is no recurrence
        # left to judge against measured durations
        return rows
    if interval is None:
        # nothing scheduled after itself: no recurrence risk to speak about
        return rows

    samples = (estimate or {}).get('samples') or 0
    average = (estimate or {}).get('average')
    if average is not None and samples >= MIN_RELIABLE_SAMPLES:
        if interval < average:
            rows.append({
                'code': SCHEDULE_TOO_TIGHT,
                'severity': WARNING,
                'interval': format_duration(interval),
                'observedDuration': format_duration(average),
                'sampleCount': samples,
                'lastDoneAt': (estimate or {}).get('last_done'),
                'expectedAt': None,
                'expiredAt': None,
                'unknownReason': None,
                'computedAt': current_time,
            })
    else:
        rows.append({
            'code': INSUFFICIENT_EVIDENCE,
            'severity': INFO,
            'interval': format_duration(interval),
            'observedDuration': None,
            'sampleCount': samples,
            'lastDoneAt': (estimate or {}).get('last_done'),
            'expectedAt': None,
            'expiredAt': None,
            'unknownReason': NO_COMPLETED_RUNS
            if samples == 0 else TOO_FEW_SAMPLES,
            'computedAt': current_time,
        })
    return rows


def schedule_warnings_by_id(settings: list) -> dict:
    """The schedule warnings of a page of settings, keyed by setting id.

    The entry point of the list endpoints: one batch of duration evidence for
    the whole page and the crontab decision for the rows of that page - so a
    paginated fetch pays no aggregation per row, no global alert scan and no
    worker inspection, whatever history the deployment accumulated behind it
    (#1308, #1332).

    Args:
        settings: the settings of one answer, crontab loaded by the caller

    Returns:
        dict: the warning rows of every settings identifier
    """
    if not settings:
        return {}
    computed_at = timezone.now()
    estimates = duration_estimates(settings)
    return {
        setting.pk: warnings_for_setting(
            setting, estimates.get(setting.pk), computed_at)
        for setting in settings
    }
