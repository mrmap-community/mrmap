import logging
import socket
from datetime import datetime

from system.logging.util import escape_sd_value, format_structured_data


class RFC5424Formatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created).astimezone()
        return dt.replace(microsecond=0).isoformat()

    def format(self, record):
        record.message = record.getMessage()
        record.asctime = self.formatTime(record)

        file_sd = ""
        if not getattr(record, "disable_python_meta", True):
            file_sd = (
                f'[metaSDID@python module="{escape_sd_value(record.module)}" '
                f'pathname="{escape_sd_value(record.pathname)}" '
                f'lineno="{escape_sd_value(record.lineno)}" '
                f'funcName="{escape_sd_value(record.funcName)}"]'
            )

        exc_sd = ""
        if record.exc_info:
            exc_info = self.formatException(
                record.exc_info).replace("\n", "\\n")
            exc_sd = f'[metaSDID@exception info="{escape_sd_value(exc_info)}"]'

        # Extra-Felder als SD-Elemente
        structured_data = f"{file_sd}{exc_sd}{format_structured_data(getattr(record, "structured_data", {}))}"

        log = (
            f'1 {record.asctime} {socket.gethostname()} mrmap {record.process} - '
            f'{structured_data} {record.message}'
        )
        return log
