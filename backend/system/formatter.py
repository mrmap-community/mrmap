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

        # Standard SD-Elemente
        file_sd = (
            f'[fileSDID@python module="{record.module}" '
            f'pathname="{record.pathname}" lineno="{record.lineno}"]'
        )

        exc_sd = ""
        if record.exc_info:
            exc_info = self.formatException(record.exc_info)
            exc_sd = f'[exceptionSDID@python exc_info="{exc_info}"]'

        # Reserved-Attribute nicht ins extra SD übernehmen
        reserved = set(logging.LogRecord(
            None, None, "", 0, "", (), None).__dict__.keys())

        # Extra-Felder als eigene SD-Elemente
        extra_sd_elements = []

        for key, value in record.__dict__.items():
            if key in reserved or value is None:
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
                # SD-ID aus Key generieren, z.B. query_1 → query1SDID
                sd_id = f"{sd_key}SDID@python"
                extra_sd_elements.append(f'[{sd_id} {sd_key}="{val}"]')

        structured_data = f"{file_sd}{exc_sd}{''.join(extra_sd_elements)}"

        log = (
            f'1 {record.asctime} {socket.gethostname()} mrmap {record.process} - '
            f'{structured_data} {record.message}'
        )
        return log
