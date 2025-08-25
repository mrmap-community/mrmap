import json
from logging import Logger

from django.conf import settings
from django.db import connection
from django.urls import resolve
from django.utils import timezone

logger: Logger = settings.ROOT_LOGGER
MAX_EVENT_BYTES = 1472  # Maximalgröße pro Event


class SystemLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.threshold_ms = int(
            getattr(settings, "LOG_LONG_RUNNING_REQUEST_THRESHOLD_MS", 100)
        )

    def __call__(self, request):
        self.start = timezone.now()
        collected_queries = []

        # Query-Logging Wrapper
        def query_logger_execute_wrapper(execute, sql, params, many, context):
            start_time = timezone.now()
            try:
                return execute(sql, params, many, context)
            finally:
                duration_ms = int(
                    (timezone.now() - start_time).total_seconds() * 1000
                )
                collected_queries.append(
                    {"sql": sql, "duration_ms": duration_ms})

        with connection.execute_wrapper(query_logger_execute_wrapper):
            response = self.get_response(request)

        self._response(request, response, collected_queries)
        return response

    def _response(self, request, response=None, queries=None, exception=None):
        end = timezone.now()
        time_delta = end - self.start
        request_duration_ms = int(time_delta.total_seconds() * 1000)

        if request_duration_ms <= self.threshold_ms:
            return

        path = "http://" + request.get_host() + request.get_full_path()
        view, _, _ = resolve(request.path)
        query_count = len(queries) if queries else 0
        query_duration_ms = sum(q["duration_ms"]
                                for q in queries) if queries else 0

        request_id = f"{timezone.now().timestamp()}_{id(request)}"

        # Basisdaten ohne SQL
        base_extra = {
            "request_id": request_id,
            "path": path,
            "request_duration_ms": request_duration_ms,
            "status_code": response.status_code if response else "500",
            "request_method": request.META.get("REQUEST_METHOD", "GET"),
            "django_view": "%s.%s" % (view.__module__, view.__name__),
            "queries": query_count,
            "query_duration_ms": query_duration_ms,
            "response_started": timezone.now().isoformat(),
        }

        # SQL-Chunks vorbereiten
        if queries:
            for idx, q in enumerate(queries, start=1):
                sql_text = q["sql"]
                # duration = q["duration_ms"]
                key = f"query_{idx}"

                # Chunking nach Event-Größe
                chunk = ""
                part_idx = 1
                chunks = []
                for char in sql_text:
                    chunk_candidate = chunk + char
                    test_event = dict(base_extra)
                    test_event[key] = chunk_candidate
                    test_event["msg"] = f"Slow Request detected: {path}"
                    event_size = len(
                        json.dumps(test_event, ensure_ascii=False).encode(
                            "utf-8")
                    )
                    if event_size > MAX_EVENT_BYTES:
                        # Chunk voll, speichern
                        chunks.append(chunk)
                        part_idx += 1
                        chunk = char
                    else:
                        chunk = chunk_candidate
                if chunk:
                    chunks.append(chunk)

                # Logge alle Chunks
                for i, part in enumerate(chunks, start=1):
                    chunk_extra = dict(base_extra)
                    chunk_extra[f"{key}_part"] = part
                    chunk_extra[f"{key}_part_index"] = i
                    chunk_extra[f"{key}_part_total"] = len(chunks)
                    logger.warning(msg=f"Slow Request SQL Chunk",
                                   extra=chunk_extra)

        else:
            # Kein SQL, normales Event loggen
            logger.warning(
                msg=f"Slow Request detected: {path}",
                extra=base_extra,
            )
