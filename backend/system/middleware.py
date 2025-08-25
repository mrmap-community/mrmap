import json
from logging import Logger

from django.conf import settings
from django.db import connection
from django.urls import resolve
from django.utils import timezone

logger: Logger = settings.ROOT_LOGGER


class SystemLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        # Threshold bestimmen
        self.threshold_ms = int(
            getattr(settings, "LOG_LONG_RUNNING_REQUEST_THRESHOLD_MS", 400)
        )
        # Maximalgröße pro SQL Chunk (unter OpenObserve Limit)
        self.max_chunk_size = 1000

    def __call__(self, request):
        self.start = timezone.now()
        collected_queries = []

        # execute_wrapper für Query Logging
        def query_logger_execute_wrapper(execute, sql, params, many, context):
            start_time = timezone.now()
            try:
                return execute(sql, params, many, context)
            finally:
                duration_ms = int(
                    (timezone.now() - start_time).total_seconds() * 1000
                )
                collected_queries.append(
                    {"sql": sql, "duration_ms": duration_ms}
                )

        with connection.execute_wrapper(query_logger_execute_wrapper):
            response = self.get_response(request)

        self._response(request, response, collected_queries)
        return response

    def _response(self, request, response=None, queries=None, exception=None):
        end = timezone.now()
        start = self.start
        time_delta = end - start
        request_duration_ms = int(time_delta.total_seconds() * 1000)

        if request_duration_ms <= self.threshold_ms:
            return  # nur langsame Requests loggen

        path = f'http://{request.get_host()}{request.get_full_path()}'
        view, _, _ = resolve(request.path)

        query_count = len(queries) if queries else 0
        query_duration_ms = sum(q["duration_ms"]
                                for q in queries) if queries else 0

        # einfache ID pro Request
        request_id = f"{timezone.now().timestamp()}_{request.META.get('REMOTE_ADDR', '')}"

        # Basisdaten Event
        log_extra = {
            "request_id": request_id,
            "path": path,
            "request_duration_ms": request_duration_ms,
            "status_code": response.status_code if response else "500",
            "request_method": request.META.get("REQUEST_METHOD", "GET"),
            "django_view": f"{view.__module__}.{view.__name__}",
            "queries": query_count,
            "query_duration_ms": query_duration_ms,
            "response_started": timezone.now(),
        }

        logger.warning(msg=f"Slow Request detected: {path}", extra=log_extra)

        # SQL-Chunks loggen
        if queries:
            for idx, q in enumerate(queries, start=1):
                sql_text = q["sql"]
                duration = q["duration_ms"]

                query_id = f"{request_id}_query{idx}"

                # Berechne Basisgröße für das Event (ohne SQL)
                chunk_extra_base = {
                    "request_id": request_id,
                    "query_id": query_id,
                    "duration_ms": duration,
                }
                base_size = len(json.dumps(chunk_extra_base).encode("utf-8"))

                # Maximalgröße für SQL-Chunk
                max_chunk_bytes = self.max_event_bytes - base_size - 50  # Sicherheits-Puffer

                # Splitte SQL nach Bytes
                chunks = []
                current_chunk = ""
                for char in sql_text:
                    if len((current_chunk + char).encode("utf-8")) > max_chunk_bytes:
                        chunks.append(current_chunk)
                        current_chunk = char
                    else:
                        current_chunk += char
                if current_chunk:
                    chunks.append(current_chunk)

                # Logge jeden Chunk als eigenes Event
                for part_idx, part in enumerate(chunks, start=1):
                    chunk_extra = {
                        **chunk_extra_base,
                        "sql_part": part,
                        "sql_part_index": part_idx,
                        "sql_part_total": len(chunks),
                    }
                    logger.warning(msg="Slow Request SQL Chunk",
                                   extra=chunk_extra)
