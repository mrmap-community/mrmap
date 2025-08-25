
import logging
import socket
from datetime import datetime


class RFC5424Formatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created).astimezone()
        return dt.replace(microsecond=0).isoformat()

    def format(self, record):
        record.message = record.getMessage()
        record.asctime = self.formatTime(record)

        # Standard-SD-Elemente
        file_sd = (
            f'[fileSDID@python module="{record.module}" '
            f'pathname="{record.pathname}" lineno="{record.lineno}"]'
        )

        exception_info = None
        exc_sd = ""
        if record.exc_info:
            exception_info = self.formatException(record.exc_info)
            exc_sd = f'[exceptionSDID@python exc_info="{exception_info}"]'

        # Basis-Attribute, die wir NICHT als extra loggen wollen
        reserved = set(logging.LogRecord(
            None, None, "", 0, "", (), None).__dict__.keys())

        # Extra-SD-Element
        sd_params = []
        for key, value in record.__dict__.items():
            if key in reserved:
                continue
            if value is None:
                continue

            # Wenn Value ein Dict → flatten in key_subkey
            if isinstance(value, dict):
                for subk, subv in value.items():
                    val = str(subv).replace("\\", "\\\\").replace(
                        '"', '\\"').replace("]", "\\]")
                    sd_params.append(f'{key}_{subk}="{val}"')
            else:
                val = str(value).replace("\\", "\\\\").replace(
                    '"', '\\"').replace("]", "\\]")
                sd_params.append(f'{key}="{val}"')

        extra_sd = f'[extraSDID@python {" ".join(sd_params)}]' if sd_params else "-"

        structured_data = f"{file_sd}{exc_sd}{extra_sd}"

        # Syslog Nachricht
        log = (
            f'1 {record.asctime} {socket.gethostname()} mrmap {record.process} - '
            f'{structured_data} \ufeff{record.message}'
        )
        return log
