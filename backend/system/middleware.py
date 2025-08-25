from logging import Logger

from django.conf import settings
from django.db import connection
from django.urls import resolve
from django.utils import timezone

logger: Logger = settings.ROOT_LOGGER
MAX_EVENT_BYTES = 1472


class SystemLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.threshold_ms = int(
            getattr(settings, "LOG_LONG_RUNNING_REQUEST_THRESHOLD_MS", 100))

    def __call__(self, request):
        self.start = timezone.now()
        collected_queries = []

        def query_logger_execute_wrapper(execute, sql, params, many, context):
            start_time = timezone.now()
            try:
                return execute(sql, params, many, context)
            finally:
                duration_ms = int(
                    (timezone.now() - start_time).total_seconds() * 1000)
                collected_queries.append(
                    {"sql": sql, "duration_ms": duration_ms})

        with connection.execute_wrapper(query_logger_execute_wrapper):
            response = self.get_response(request)

        self._response(request, response, collected_queries)
        return response

    def _response(self, request, response=None, queries=None, exception=None):
        end = timezone.now()
        request_duration_ms = int((end - self.start).total_seconds() * 1000)
        if request_duration_ms <= self.threshold_ms:
            return

        path = 'http://' + request.get_host() + request.get_full_path()
        view, _, _ = resolve(request.path)
        request_id = f"{int(self.start.timestamp())}.{self.start.microsecond}_{id(request)}"

        # Basisdaten
        log_base = {
            "path": path,
            "request_duration_ms": request_duration_ms,
            "status_code": response.status_code if response else 500,
            "request_method": request.META.get("REQUEST_METHOD", "GET"),
            "django_view": f"{view.__module__}.{view.__name__}",
            "queries": len(queries) if queries else 0,
            "query_duration_ms": sum(q["duration_ms"] for q in queries) if queries else 0,
            "response_started": timezone.now(),
            "request_id": request_id
        }

        # Logge normale Basisdaten
        logger.warning(msg=f"Slow Request detected: {path}", extra=log_base)

        # Logge SQL-Chunks separat
        if queries:
            for idx, q in enumerate(queries, start=1):
                sql = q["sql"]
                duration = q["duration_ms"]
                base_extra = {"request_id": request_id,
                              "query_idx": idx, "query_duration_ms": duration}

                # SQL in Chunks aufteilen
                chunk_size = MAX_EVENT_BYTES - 200  # Puffer für Header & SD
                for i in range(0, len(sql), chunk_size):
                    chunk_sql = sql[i:i+chunk_size]
                    logger.warning(msg=f"SQL Chunk for query {idx}", extra={
                                   **base_extra, "query_sql_part": chunk_sql})
