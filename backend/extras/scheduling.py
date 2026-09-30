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

