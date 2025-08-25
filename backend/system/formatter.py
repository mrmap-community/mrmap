import logging
import socket
from datetime import datetime

# Konstant für reservierte LogRecord-Felder
RESERVED_KEYS = set(logging.LogRecord(
    None, None, "", 0, "", (), None).__dict__.keys())


class RFC5424Formatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created).astimezone()
        return dt.replace(microsecond=0).isoformat()

    def format(self, record):
        record.message = record.getMessage()
        record.asctime = self.formatTime(record)

        # Standard SD-Elemente
        file_sd = (
            f'[fileSDID@python module="{record.module}" '
            f'pathname="{record.pathname}" lineno="{record.lineno}" '
            f'funcName="{record.funcName}"]'
        )

        # Level SD
        level_sd = f'[levelSDID@python level="{record.levelname}"]'

        # Exception SD
        exc_sd = ""
        if record.exc_info:
            exc_info = self.formatException(
                record.exc_info).replace("\n", "\\n")
            exc_sd = f'[exceptionSDID@python exc_info="{exc_info}"]'

        # Extra-Felder als eigene SD-Elemente
        extra_sd_elements = []

        for key, value in record.__dict__.items():
            if key in RESERVED_KEYS or value is None:
                continue

            # Verschachtelte Dicts flachlegen
            if isinstance(value, dict):
                flat_fields = {}
                for subk, subv in value.items():
                    flat_fields[f"{key}_{subk}"] = subv
            else:
                flat_fields = {key: value}

            # Jedes Key/Value als eigenes SD-Element
            for sd_key, sd_value in flat_fields.items():
                val = str(sd_value).replace("\\", "\\\\").replace(
                    '"', '\\"').replace("]", "\\]")
                sd_id = f"{sd_key}SDID@python"
                extra_sd_elements.append(f'[{sd_id} {sd_key}="{val}"]')

        structured_data = f"{file_sd}{level_sd}{exc_sd}{''.join(extra_sd_elements)}"

        log = (
            f'1 {record.asctime} {socket.gethostname()} mrmap {record.process} - '
            f'{structured_data} {record.message}'
        )
        return log
