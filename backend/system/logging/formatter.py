import logging
import socket
from datetime import datetime

MAX_EVENT_BYTES = 1472  # Gleiche Grenze wie Middleware


class RFC5424Formatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created).astimezone()
        return dt.replace(microsecond=0).isoformat()

    def format(self, record):
        record.message = record.getMessage()
        record.asctime = self.formatTime(record)

        file_sd = ""
        if hasattr(record, "disable_python_meta") and not record.disable_python_meta:
            file_sd = (
                f'[metaSDID@python module="{record.module}" '
                f'pathname="{record.pathname}" lineno="{record.lineno}" '
                f'funcName="{record.funcName}"]'
            )

        exc_sd = ""
        if record.exc_info:
            exc_info = self.formatException(
                record.exc_info).replace("\n", "\\n")
            exc_sd = f'[metaSDID@exception info="{exc_info}"]'

        # Extra-Felder als SD-Elemente
        extra_sd_elements = []
        if hasattr(record, "structured_data"):
            for sdid, key_value_pairs in record.structured_data.items():
                sd = f"[{sdid}"
                for key, value in key_value_pairs.items():
                    sd += f" {key}={value}"
                sd += "]"
                extra_sd_elements.append(sd)

        structured_data = f"{file_sd}{exc_sd}{''.join(extra_sd_elements)}"

        log = (
            f'1 {record.asctime} {socket.gethostname()} mrmap {record.process} - '
            f'{structured_data} {record.message}'
        )
        return log
