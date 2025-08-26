import logging
import uuid
from copy import deepcopy
from logging.handlers import SysLogHandler


class OpenObserveSysLogHandler(SysLogHandler):
    """
    Splittet zu lange Syslog-Events so, dass OpenObserve nicht abschneidet.
    Fügt beim Split ein SD-Element [metaSDID@split ...] hinzu.
    """

    append_nul = False
    max_message_length = 1450  # Sicherheitsabstand
    SPLIT_SDID = "metaSDID@split"

    def emit(self, record):
        # Schnellpfad: passt in ein Event
        formatted = self.format(record)
        if len(formatted.encode("utf-8")) <= self.max_message_length:
            return super().emit(record)

        # Zu lang → splitten
        original_message = record.getMessage()  # nur der Textteil
        base_sd = deepcopy(getattr(record, "structured_data", {}) or {})
        related_id = str(uuid.uuid4())

        # In Chunks schneiden, basierend auf tatsächlichem Formatierungs-Overhead
        chunks = self._split_by_formatter_budget(
            original_message, record, base_sd, related_id
        )

        total = len(chunks)
        for idx, chunk in enumerate(chunks, start=1):
            dummy = self._clone_for_chunk(record, chunk)
            sd = deepcopy(base_sd)
            sd[self.SPLIT_SDID] = {
                "related_id": related_id,
                "part": str(idx),
                "total": str(total),
            }
            dummy.structured_data = sd
            super().emit(dummy)

    # -------- internals --------

    def _clone_for_chunk(self, src_record: logging.LogRecord, chunk_msg: str) -> logging.LogRecord:
        """
        Erzeugt einen neuen LogRecord für einen Chunk und überträgt relevante Felder.
        """
        dummy = logging.LogRecord(
            name=src_record.name,
            level=src_record.levelno,
            pathname=src_record.pathname,
            lineno=src_record.lineno,
            msg=chunk_msg,
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

    def _split_by_formatter_budget(self, message: str, record: logging.LogRecord, base_sd: dict, related_id: str):
        """
        Schneidet message in UTF-8-sichere Chunks, deren *formatierte* Länge
        (Header + SD + Message) jeweils <= max_message_length ist.
        """
        remaining = message.encode("utf-8")
        chunks = []
        part_idx = 1

        # Pessimistische Platzhalter-Zahl für 'total' (max. 6 Stellen),
        # damit unsere Budget-Berechnung später nicht zu optimistisch ist.
        total_placeholder = "999999"

        while remaining:
            # Budget für diesen Teil berechnen: formatiere mit leerer Message
            sd = dict(base_sd)
            sd[self.SPLIT_SDID] = {
                "related_id": related_id,
                "part": str(part_idx),
                "total": total_placeholder,
            }
            dummy_empty = self._clone_for_chunk(record, "")
            dummy_empty.structured_data = sd
            base_len = len(self.format(dummy_empty).encode("utf-8"))
            budget = self.max_message_length - base_len
            if budget <= 0:
                # Fallback: mindestens 1 Byte payload erzwingen, damit Fortschritt möglich ist
                budget = 1

            # bis zu 'budget' Bytes nehmen, UTF-8-sicher schneiden
            take = budget if budget < len(remaining) else len(remaining)
            end = take
            while True:
                try:
                    chunk_text = remaining[:end].decode("utf-8")
                    break
                except UnicodeDecodeError:
                    end -= 1
                    if end <= 0:
                        # sollte praktisch nie passieren; notfalls 1 Byte ignorierend
                        end = 1
                        chunk_text = remaining[:end].decode(
                            "utf-8", errors="ignore")
                        break

            chunks.append(chunk_text)
            remaining = remaining[end:]
            part_idx += 1

        return chunks
