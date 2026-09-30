"""Expose successful Beat loop iterations to Docker's local healthcheck."""
from pathlib import Path

from django_celery_beat.schedulers import DatabaseScheduler

HEARTBEAT = Path('/tmp/mrmap-beat-heartbeat')


class HealthcheckScheduler(DatabaseScheduler):
    def __init__(self, *args, **kwargs):
        if not kwargs.get('lazy', False):
            HEARTBEAT.unlink(missing_ok=True)
        super().__init__(*args, **kwargs)

    def tick(self, *args, **kwargs):
        interval = super().tick(*args, **kwargs)
        HEARTBEAT.touch()
        return interval
