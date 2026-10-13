from django.utils import timezone


def next_run_expected_at(setting):
    """Calculate the next cron occurrence after the last scheduled dispatch."""
    if not setting.enabled or not setting.crontab_id:
        return None
    if setting.one_off and setting.total_run_count > 0:
        return None
    # Match Beat's baseline for settings that have never been dispatched.
    baseline = setting.last_run_at or setting.date_changed
    if baseline is None:
        return None
    if setting.start_time is not None:
        baseline = max(baseline, setting.start_time)
    baseline = baseline.astimezone(setting.crontab.timezone)
    schedule = setting.crontab.schedule
    # Anchor both sides of Celery's calculation to the baseline. Using the
    # current date here can skip an already missed minute in the first hour.
    schedule.nowfun = lambda: baseline
    start, delta, _ = schedule.remaining_delta(baseline)
    return start + delta


def run_overdue(setting):
    """Report whether a scheduled run missed the time it was expected at.

    This is the rule which decides that a service needs attention because a run
    it promised did not happen, so it is answered from here and not recalculated
    by whoever asks for it.

    Args:
        setting: the setting which schedules the run

    Returns:
        bool: True if the setting is enabled, did not expire and its next run
            was expected before now
    """
    current_time = timezone.now()
    if setting.expires is not None and setting.expires <= current_time:
        return False
    expected_at = next_run_expected_at(setting)
    return expected_at is not None and expected_at < current_time
