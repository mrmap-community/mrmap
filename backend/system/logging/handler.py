import logging
import uuid
from logging.handlers import SysLogHandler

from system.logging.util import (format_structured_data, get_string_length,
                                 parse_rfc5424_message)


class OpenObserveSysLogHandler(SysLogHandler):
    """
    Syslog Handler, der zu lange Events in Chunks aufteilt, sodass OpenObserve sie nicht abschneidet.
    Fügt ein SD-Element [metaSDID@split ...] hinzu, um die Chunks zu korrelieren.
    """

    append_nul = False
    max_message_length = 1300  # Sicherheitsabstand zur OpenObserve-Grenze

    def _clone_for_chunk(self, src_record: logging.LogRecord) -> logging.LogRecord:
        """
        Erzeugt einen neuen LogRecord für einen Chunk und überträgt relevante Felder.
        """
        dummy = logging.LogRecord(
            name=src_record.name,
            level=src_record.levelno,
            pathname=src_record.pathname,
            lineno=src_record.lineno,
            msg=src_record.msg,
            args=(),
            exc_info=src_record.exc_info,
        )
        # häufig genutzte Felder sauber übernehmen
        for attr in (
            "process", "processName", "thread", "threadName", "stack_info",
            "funcName", "module", "filename", "pathname", "lineno",
            "created", "msecs", "relativeCreated"
        ):
            if hasattr(src_record, attr):
                setattr(dummy, attr, getattr(src_record, attr))
        if hasattr(src_record, "disable_python_meta"):
            dummy.disable_python_meta = src_record.disable_python_meta
        return dummy

    def emit(self, record):
        msg = self.format(record)
        encoded_msg = msg.encode("utf-8")

        if len(encoded_msg) < self.max_message_length:
            super().emit(record)
            return

        parsed = parse_rfc5424_message(msg)
        base_length = get_string_length(
            f"<11>{parsed["version"]} {parsed["timestamp"]} {parsed["host"]} {parsed["app"]} {parsed["procid"]} {parsed["msgid"]} - {parsed["message"]}")
        sd_formatted = format_structured_data(
            getattr(record, "structured_data", {}) or {})
        chunk_structured_data = {
            "metaSDID@split": {
                "related_id": str(uuid.uuid4()),
                "part": str(1),
                "chunk": " "
            }
        }
        chunk_structured_data_formatted = format_structured_data(
            chunk_structured_data)
        chunk_structured_data_length = get_string_length(
            chunk_structured_data_formatted)

        chunk_size = self.max_message_length - \
            base_length + chunk_structured_data_length
        dummy = self._clone_for_chunk(record)

        for idx, chunk in enumerate([sd_formatted[i:i+chunk_size]
                                     for i in range(0, len(sd_formatted), chunk_size)], start=1):
            dummy.structured_data = {**chunk_structured_data}
            dummy.structured_data["metaSDID@split"]["chunk"] = chunk
            dummy.structured_data["metaSDID@split"]["part"] = str(idx)
            super().emit(dummy)
