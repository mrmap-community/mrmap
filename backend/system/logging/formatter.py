import logging
import socket
from datetime import datetime


def escape_sd_value(value: str) -> str:
    """
    Escaped einen SD-PARAM-Wert nach RFC5424.
    """
    if not isinstance(value, str):
        value = str(value)

    return (
        value.replace("\\", "\\\\")
             .replace("\"", "\\\"")
             .replace("]", "\\]")
             .replace("\n", "\\n")
             .replace("\r", "\\r")
    )


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
        extra_sd_elements = []
        if hasattr(record, "structured_data"):
            for sdid, key_value_pairs in record.structured_data.items():
                sd = f"[{sdid}"
                for key, value in key_value_pairs.items():
                    sd += f' {key}="{escape_sd_value(value)}"'
                sd += "]"
                extra_sd_elements.append(sd)

        structured_data = f"{file_sd}{exc_sd}{''.join(extra_sd_elements)}"

        log = (
            f'1 {record.asctime} {socket.gethostname()} mrmap {record.process} - '
            f'{structured_data} {record.message}'
        )
        return log
