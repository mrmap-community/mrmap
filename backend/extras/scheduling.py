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
    return _next_run_after(setting, baseline)


def _next_run_after(setting, baseline):
    """The next occurrence of the crontab of a setting after a moment."""
    baseline = baseline.astimezone(setting.crontab.timezone)
    schedule = setting.crontab.schedule
    # Anchor both sides of Celery's calculation to the baseline. Using the
    # current date here can skip an already missed minute in the first hour.
    schedule.nowfun = lambda: baseline
    start, delta, _ = schedule.remaining_delta(baseline)
    return start + delta


def run_interval(setting):
    """How long the schedule of a setting waits between two of its runs.

    A crontab promises no equal distance: "0 8 * * *" is 23 hours across the
    spring change of time and 25 across the autumn one. The distance of the run
    which is still to come to the one after it is the wait a dispatch really
    lands in, so that is the distance to compare a duration with.

    Args:
        setting: the setting which schedules the run

    Returns:
        timedelta: the distance of the next run of the setting to the one after
            it, or None if the setting answers no next run
    """
    expected_at = next_run_expected_at(setting)
    if expected_at is None:
        return None
    return _next_run_after(setting, expected_at) - expected_at


def schedule_is_tighter_than(setting, duration):
    """Report whether the schedule of a setting fires more often than a run takes.

    This is the rule which decides that an administrator has to be told that a
    schedule is a no-op on paper, so it is answered from here and not
    recalculated by whoever asks for it. Nothing of it blocks a save: durations
    drift with the remote service, so the schedule stays a decision of the
    administrator and is only answered as a warning (#693).

    Args:
        setting: the setting which schedules the run
        duration: how long a run of it takes, or None when nothing measured it

    Returns:
        bool: True if the setting waits less between its runs than a run takes
    """
    if duration is None:
        return False
    interval = run_interval(setting)
    return interval is not None and interval < duration


def format_duration(duration):
    """Name the length of a duration without a word.

    The hours of a run which took days are not folded into days: the answer is a
    measurement and not a date. And it carries no word on purpose, so that a
    message which names it is not mixed by the language it is answered in (#693).

    Args:
        duration: the timedelta to name

    Returns:
        str: the duration as "H:MM:SS", with more than 24 hours in the hours
    """
    seconds = int(duration.total_seconds())
    return f'{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}'


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
