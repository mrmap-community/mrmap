import logging
import socket
from datetime import datetime

RESERVED_KEYS = set(logging.LogRecord(
    None, None, "", 0, "", (), None).__dict__.keys())
MAX_EVENT_BYTES = 1472  # Gleiche Grenze wie Middleware


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
        level_sd = f'[levelSDID@python level="{record.levelname}"]'
        exc_sd = ""
        if record.exc_info:
            exc_info = self.formatException(
                record.exc_info).replace("\n", "\\n")
            exc_sd = f'[exceptionSDID@python exc_info="{exc_info}"]'

        # Extra-Felder als SD-Elemente
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

            # Prüfe Größe und splitte bei Bedarf
            for sd_key, sd_value in flat_fields.items():
                val_str = str(sd_value).replace("\\", "\\\\").replace(
                    '"', '\\"').replace("]", "\\]")
                sd_id = f"{sd_key}SDID@python"

                # Eventgröße prüfen
                base_log = f'1 {record.asctime} {socket.gethostname()} mrmap {record.process} - {file_sd}{level_sd}{exc_sd}'
                test_log = f'{base_log}[{sd_id} {sd_key}="{val_str}"] {record.message}'
                if len(test_log.encode("utf-8")) <= MAX_EVENT_BYTES:
                    extra_sd_elements.append(f'[{sd_id} {sd_key}="{val_str}"]')
                else:
                    # Chunking für zu lange Werte
                    chunk_size = MAX_EVENT_BYTES - \
                        len(base_log.encode("utf-8")) - 50  # Puffer
                    for i in range(0, len(val_str), chunk_size):
                        part = val_str[i:i+chunk_size]
                        extra_sd_elements.append(
                            f'[{sd_id}_part{i//chunk_size+1} {sd_key}="{part}"]')

        structured_data = f"{file_sd}{level_sd}{exc_sd}{''.join(extra_sd_elements)}"

        log = (
            f'1 {record.asctime} {socket.gethostname()} mrmap {record.process} - '
            f'{structured_data} {record.message}'
        )
        return log
