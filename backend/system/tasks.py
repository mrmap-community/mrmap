"""Periodic housekeeping of what a running MrMap accumulates on its own.

The per request json dumps which the rfc5424 formatter leaves below the media root
are the only artifact of a deployment that nothing ever took back: every record the
syslog handler formatted added one, so a demo which ran for a few weeks at the
default threshold held 333,193 files and 1.3 GB under ``<MEDIA_ROOT>/logs`` (#888).
Beat sweeps them with the task below; the schedule is created on migrate, see
``system/apps.py``.
"""

from datetime import datetime, timedelta, timezone
from logging import Logger
from pathlib import Path

from celery import shared_task
from django.conf import settings

from extras.tasks import SingletonTask
from system.logging.formatter import SLOW_REQUEST_DUMP_SUBDIR

logger: Logger = settings.ROOT_LOGGER


def slow_request_dumps_dir():
    """The directory the dumps of the rfc5424 formatter are written to.

    Read from ``MEDIA_ROOT`` on every call, like the formatter which writes them,
    so a deployment which moves its media root moves the sweep with it.
    """
    return Path(settings.MEDIA_ROOT) / SLOW_REQUEST_DUMP_SUBDIR


def _dumps_by_age(directory):
    """The dumps of ``directory`` with their modification time, oldest first.

    Only the ``.json`` files of that very directory and nothing below it: the media
    root keeps the request and response bodies of the security proxy in a subtree of
    its own and those belong to the rows of ``HttpRequestLog``, which are deleted
    with their records and not by age.
    """
    dumps = []
    for entry in directory.glob("*.json"):
        if not entry.is_file():
            continue
        try:
            modified = datetime.fromtimestamp(
                entry.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue  # taken away between the listing and the stat
        dumps.append((modified, entry))
    dumps.sort(key=lambda dump: dump[0])
    return dumps


def delete_dumps(directory, retention_days, max_files):
    """Takes back the dumps of ``directory`` which are of no use anymore.

    A dump goes when it was written before ``retention_days`` days, or when more
    than ``max_files`` of them are left and it is one of the oldest; a bound of 0
    answers that bound disabled. The count bounds the directory itself, which a
    chatty deployment pays for on every listing, while the age bound is the one
    which aligns with the retention of the log store.

    Returns what was done, which is what the log line and the beat result say.
    """
    dumps = _dumps_by_age(directory)

    expired = []
    if retention_days > 0:
        allowed_since = datetime.now(timezone.utc) - timedelta(
            days=retention_days)
        expired = [entry for modified,
                   entry in dumps if modified < allowed_since]
        # what the age bound took away is gone, so it is not left to the cap
        dumps = [(modified, entry) for modified,
                 entry in dumps if modified >= allowed_since]

    excess = []
    if max_files > 0 and len(dumps) > max_files:
        excess = [entry for _, entry in dumps[:len(dumps) - max_files]]

    for entry in expired + excess:
        entry.unlink(missing_ok=True)

    return {
        "directory": str(directory),
        "retention_days": retention_days,
        "max_files": max_files,
        "expired": len(expired),
        "excess": len(excess),
        "remaining": len(dumps) - len(excess),
    }


@shared_task(queue="db-routines", bind=True, base=SingletonTask)
def delete_old_slow_request_dumps(self, *args, **kwargs):
    """Sweeps the slow request dumps out of the media root (#888).

    Runs as a singleton on the ``db-routines`` queue, because two sweeps over the
    same directory have nothing to add to each other, and beat hands it over
    hourly. A dump which is gone only costs the per request sql detail: the syslog
    line which pointed at it stays in the log store for its own retention.
    """
    summary = delete_dumps(
        slow_request_dumps_dir(),
        retention_days=settings.SLOW_REQUEST_DUMP_RETENTION_DAYS,
        max_files=settings.SLOW_REQUEST_DUMP_MAX_FILES)
    logger.info(
        "Slow request dumps of %s: %s expired and %s exceeding the cap deleted, "
        "%s left (retention %s days, cap %s).",
        summary["directory"], summary["expired"], summary["excess"],
        summary["remaining"], summary["retention_days"], summary["max_files"])
    return summary
