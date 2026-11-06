import json
import logging
import socket
import uuid
from datetime import datetime
from pathlib import Path

from django.conf import settings
from system.logging.util import format_structured_data

#: The name of the directory below ``MEDIA_ROOT`` the per request dumps are
#: written to. The media route which refuses them (``MrMap.urls``) and the sweep
#: which takes them back (``system.tasks``) look them up by this name, so it is
#: stated exactly once (#888).
SLOW_REQUEST_DUMP_SUBDIR = "logs"

#: The structured data id the formatter itself fills with the position in the
#: code which emitted the record. A dump is written for a record which carries
#: anything beyond it (#1033).
PYTHON_META_SDID = "metaSDID@python"


class RFC5424Formatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created).astimezone()
        return dt.replace(microsecond=0).isoformat()

    def _write_dump(self, structured_data):
        """Write the dump of one record and answer its url, None without a file.

        Cause some syslog server implementations are limiting message size, we
        store verbose details as simple media files. The dump carries complete
        sql statements and the request metadata, so the media route does not
        serve it (see MrMap.urls) and the sweep in system.tasks takes it back
        after its retention (#888). The url is answered only for a file which
        was actually written, so a syslog line never points at a missing dump.
        """
        try:
            path = Path(settings.MEDIA_ROOT) / SLOW_REQUEST_DUMP_SUBDIR
            path.mkdir(parents=True, exist_ok=True)

            log_id = uuid.uuid4()
            with open(path / f"{log_id}.json", "w+") as fp:
                json.dump(structured_data, fp)
        except Exception:
            return None
        return f"{settings.MEDIA_URL}{SLOW_REQUEST_DUMP_SUBDIR}/{log_id}.json"

    def format(self, record):
        record.message = record.getMessage()
        record.asctime = self.formatTime(record)

        structured_data = getattr(record, "structured_data", {})

        if not getattr(record, "disable_python_meta", False):
            structured_data[PYTHON_META_SDID] = {
                "module": record.module,
                "pathname": record.pathname,
                "lineno": record.lineno,
                "funcName": record.funcName,
            }

        if record.exc_info:

            exc_info = self.formatException(
                record.exc_info).replace("\n", "\\n")
            structured_data["metaSDID@exception"] = {
                "traceback": exc_info
            }

        # A dump is worth its file only where the record carries more than the
        # code position the formatter adds itself: it used to write one for
        # every record the syslog handler formatted, so on a running
        # deployment the pile below the media root was dominated by Celery's
        # per task INFO and repeating warnings instead of the slow request
        # diagnostics it is there for (#1033). An ordinary record is answered
        # by its syslog line alone.
        short_structured_data = {}
        if any(sdid != PYTHON_META_SDID for sdid in structured_data):
            details_json = self._write_dump(structured_data)
            if details_json:
                short_structured_data = {
                    "metaSDID@Details": {"json": details_json}
                }

        log = (
            f'1 {record.asctime or "-"} {socket.gethostname() or "-"} mrmap {record.process or "-"} - '
            f'{format_structured_data(short_structured_data) or "-"} {record.message or "-"}'
        )

        return log
