import base64
import gzip
import uuid
from logging import Logger

from django.conf import settings
from django.db import connection
from django.urls import resolve
from django.utils import timezone

logger: Logger = settings.ROOT_LOGGER

MAX_LOG_SIZE = 1400  # etwas Puffer unter 1472 Bytes


def chunk_string(s: str, max_length: int):
    """Split string s into chunks of max_length."""
    return [s[i:i + max_length] for i in range(0, len(s), max_length)]


class SystemLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.threshold_ms = int(
            getattr(settings, "LOG_LONG_RUNNING_REQUEST_THRESHOLD_MS", 400))

    def __call__(self, request):
        self.start = timezone.now()
        collected_queries = []
        request_id = str(uuid.uuid4())

        def query_logger_execute_wrapper(execute, sql, params, many, context):
            start_time = timezone.now()
            try:
                return execute(sql, params, many, context)
            finally:
                duration_ms = int(
                    (timezone.now() - start_time).total_seconds() * 1000)

                query_id = str(uuid.uuid4())

                # Falls SQL zu groß: splitten
                sql_chunks = chunk_string(sql, MAX_LOG_SIZE)

                for idx, chunk in enumerate(sql_chunks, start=1):
                    collected_queries.append({
                        "query_id": query_id,
                        "sql_part": chunk,
                        "sql_part_index": idx,
                        "sql_part_total": len(sql_chunks),
                        "duration_ms": duration_ms if idx == 1 else 0,  # Dauer nur im ersten Teil
                    })

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

            log_extra = {
                "request_id": request_id,
                "path": path,
                "request_duration_ms": request_duration_ms,
                "status_code": response.status_code if response else "500",
                "request_method": request.META.get("REQUEST_METHOD", "GET"),
                "django_view": "%s.%s" % (view.__module__, view.__name__),
                "queries": len(queries),
                "query_duration_ms": sum(q["duration_ms"] for q in queries),
                "response_started": timezone.now(),
            }

            # Queries anhängen
            for idx, q in enumerate(queries, start=1):
                log_extra[f"query_{idx}_id"] = q["query_id"]
                log_extra[f"query_{idx}_part"] = q["sql_part"]
                log_extra[f"query_{idx}_part_index"] = q["sql_part_index"]
                log_extra[f"query_{idx}_part_total"] = q["sql_part_total"]
                if q["duration_ms"] > 0:
                    log_extra[f"query_{idx}_duration_ms"] = q["duration_ms"]
            logger.warning(
                msg=f"Slow Request detected: {path}",
                extra=log_extra,
            )
