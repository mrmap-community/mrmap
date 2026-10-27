"""Expose successful Beat loop iterations to Docker's local healthcheck."""
import os
from pathlib import Path

from django_celery_beat.schedulers import DatabaseScheduler

# The heartbeat used to sit in /tmp. That directory is world-writable and the
# file name is predictable, so any local identity could pre-create the path as
# a symlink or race the writer. Beat runs as mrmapuser, which owns /var/mrmap,
# so the heartbeat gets a private, owner-only directory instead. A deployment
# may relocate it, but its Docker healthcheck (docker-compose.yml) must then
# watch the very same file.
HEARTBEAT_DIR = Path(os.environ.get('MRMAP_BEAT_HEARTBEAT_DIR', '/var/mrmap/run'))
HEARTBEAT = HEARTBEAT_DIR / 'beat-heartbeat'


def prepare_heartbeat(lazy=False):
    """Provide the private directory the heartbeat file is touched in.

    Creating it with 0o700 keeps every other identity out of the symlink and
    race game before it starts. A non-lazy start also drops a stale heartbeat
    via ``unlink``, which removes a planted symlink itself instead of following
    it, so Beat can never touch the symlink's target.
    """
    HEARTBEAT_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not lazy:
        HEARTBEAT.unlink(missing_ok=True)


class HealthcheckScheduler(DatabaseScheduler):
    def __init__(self, *args, **kwargs):
        prepare_heartbeat(lazy=bool(kwargs.get('lazy', False)))
        super().__init__(*args, **kwargs)

    def tick(self, *args, **kwargs):
        interval = super().tick(*args, **kwargs)
        HEARTBEAT.touch()
        return interval
