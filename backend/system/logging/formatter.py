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


class RFC5424Formatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created).astimezone()
        return dt.replace(microsecond=0).isoformat()

    def format(self, record):
        record.message = record.getMessage()
        record.asctime = self.formatTime(record)

        log_id = uuid.uuid4()
        short_structured_data = {
            "metaSDID@Details": {
                "json": f"{settings.MEDIA_URL}{SLOW_REQUEST_DUMP_SUBDIR}/{log_id}.json",
            }
        }
        structured_data = getattr(record, "structured_data", {})

        if not getattr(record, "disable_python_meta", False):
            structured_data["metaSDID@python"] = {
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

        try:
            path = Path(settings.MEDIA_ROOT) / SLOW_REQUEST_DUMP_SUBDIR
            path.mkdir(parents=True, exist_ok=True)

            with open(path / f"{log_id}.json", "w+") as fp:
                # cause some syslog server implementations are limiting message size, we store verbose details as simple media files
                # the dump carries complete sql statements and the request metadata, so
                # the media route does not serve it (see MrMap.urls) and the sweep in
                # system.tasks takes it back after its retention (#888)
                json.dump(structured_data, fp)
        except Exception:
            pass

        log = (
            f'1 {record.asctime or "-"} {socket.gethostname() or "-"} mrmap {record.process or "-"} - '
            f'{format_structured_data(short_structured_data) or "-"} {record.message or "-"}'
        )

        return log
