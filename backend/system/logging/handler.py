import logging
import uuid
from logging.handlers import SysLogHandler


class OpenObserveSysLogHandler(SysLogHandler):
    """
    Syslog Handler, der zu lange Events in Chunks aufteilt, sodass OpenObserve sie nicht abschneidet.
    Fügt ein SD-Element [metaSDID@split ...] hinzu, um die Chunks zu korrelieren.
    """

    append_nul = False
    max_message_length = 1450  # Sicherheitsabstand zur OpenObserve-Grenze

    def emit(self, record):
        msg = self.format(record)
        encoded_msg = msg.encode("utf-8")

        if len(encoded_msg) < self.max_message_length:
            return super().emit(record)

        # Nachricht zu lang → splitten
        related_id = str(uuid.uuid4())
        chunks = self._split_message(record.getMessage())

        for idx, chunk in enumerate(chunks, start=1):
            dummy = logging.LogRecord(
                name=record.name,
                level=record.levelno,
                pathname=record.pathname,
                lineno=record.lineno,
                msg=chunk,
                args=(),
                exc_info=record.exc_info,
            )

            # alle Felder aus dem Original übernehmen
            dummy.__dict__.update(record.__dict__)

            # structured_data übernehmen und erweitern
            sd = getattr(record, "structured_data", {}) or {}
            sd = {**sd}  # Kopie machen
            sd["metaSDID@split"] = {
                "related_id": related_id,
                "part": str(idx),
                "total": str(len(chunks)),
            }
            dummy.structured_data = sd

            super().emit(dummy)

    def _split_message(self, message: str):
        """
        Teilt eine Nachricht in UTF-8 sichere Chunks.
        """
        encoded = message.encode("utf-8")
        chunks = []
        start = 0
        while start < len(encoded):
            end = start + self.max_message_length
            chunk = encoded[start:end]
            # utf-8 safe cut
            while True:
                try:
                    decoded = chunk.decode("utf-8")
                    break
                except UnicodeDecodeError:
                    end -= 1
                    chunk = encoded[start:end]
            chunks.append(decoded)
            start = end
        return chunks
