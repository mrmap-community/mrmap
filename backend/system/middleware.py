import base64
import gzip
import uuid
from logging import Logger

from django.conf import settings
from django.db import connection
from django.urls import resolve
from django.utils import timezone

logger: Logger = settings.ROOT_LOGGER


def compress_if_needed(sql: str, threshold: int = 500) -> dict:
    """Komprimiere SQL-String, wenn er zu lang ist."""
    if len(sql) <= threshold:
        return {"sql": sql, "compressed": False}

    compressed = gzip.compress(sql.encode("utf-8"))
    b64 = base64.b64encode(compressed).decode("ascii")
    return {"sql": b64, "compressed": True, "original_len": len(sql)}


class SystemLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.threshold_ms = int(
            getattr(settings, "LOG_LONG_RUNNING_REQUEST_THRESHOLD_MS", 100))

    def __call__(self, request):
        self.start = timezone.now()
        collected_queries = []
        request_id = str(uuid.uuid4())

        # execute_wrapper für Production Query Logging
        def query_logger_execute_wrapper(execute, sql, params, many, context):
            start_time = timezone.now()
            try:
                return execute(sql, params, many, context)
            finally:
                duration_ms = int(
                    (timezone.now() - start_time).total_seconds() * 1000)
                qinfo = compress_if_needed(sql)
                qinfo["duration_ms"] = duration_ms
                qinfo["request_id"] = request_id
                collected_queries.append(qinfo)

                # Jede Query sofort loggen
                logger.warning(
                    "SQL Query",
                    extra={
                        "request_id": request_id,
                        "query_sql": qinfo["sql"],
                        "query_compressed": qinfo.get("compressed", False),
                        "query_duration_ms": duration_ms,
                        "query_original_len": qinfo.get("original_len", len(sql)),
                    },
                )

        with connection.execute_wrapper(query_logger_execute_wrapper):
            response = self.get_response(request)

        self._response(request, response, collected_queries, request_id)
        return response

    def _response(self, request, response=None, queries=None, request_id=None):
        end = timezone.now()
        start = self.start
        time_delta = end - start

        # Requestdauer in Millisekunden
        request_duration_ms = int(time_delta.total_seconds() * 1000)

        if request_duration_ms > self.threshold_ms:
            path = "http://" + request.get_host() + request.get_full_path()
            view, args, kwargs = resolve(request.path)

            query_count = len(queries) if queries else 0
            query_duration_ms = sum(q["duration_ms"] for q in queries)

            # Main-Logevent
            logger.warning(
                "Slow Request detected",
                extra={
                    "request_id": request_id,
                    "path": path,
                    "request_duration_ms": request_duration_ms,
                    "status_code": response.status_code if response else "500",
                    "request_method": request.META.get("REQUEST_METHOD", "GET"),
                    "django_view": f"{view.__module__}.{view.__name__}",
                    "queries": query_count,
                    "query_duration_ms": query_duration_ms,
                    "response_started": timezone.now(),
                },
            )
