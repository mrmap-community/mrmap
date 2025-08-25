from logging import Logger

from django.conf import settings
from django.db import connection
from django.urls import resolve
from django.utils import timezone

logger: Logger = settings.ROOT_LOGGER


class SystemLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        # One-time configuration and initialization.

        # Threshold bestimmen
        self.threshold_ms = int(
            getattr(settings, "LOG_LONG_RUNNING_REQUEST_THRESHOLD_MS", 100))

    def __call__(self, request):
        self.start = timezone.now()
        collected_queries = []

        # execute_wrapper für Production Query Logging
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
        start = self.start
        time_delta = end - start

        # Requestdauer in Millisekunden
        request_duration_ms = int(time_delta.total_seconds() * 1000)

        if request_duration_ms > self.threshold_ms:
            path = 'http://' + request.get_host() + request.get_full_path()
            view, args, kwargs = resolve(request.path)

            # Query Count und Detail
            query_count = len(queries) if queries else 0
            query_duration_ms = sum(q["duration_ms"]
                                    for q in queries) if queries else 0

            queries_extra = {}
            if queries:
                for idx, q in enumerate(queries, start=1):
                    queries_extra[f"query_{idx}"] = q

            # Basisdaten
            log_extra = {
                "path": path,
                "request_duration_ms": request_duration_ms,
                "status_code": response.status_code if response else "500",
                "request_method": request.META.get("REQUEST_METHOD", "GET"),
                "django_view": "%s.%s" % (view.__module__, view.__name__),
                "queries": query_count,
                "query_duration_ms": query_duration_ms,
                "response_started": timezone.now(),
            }

            # Queries anhängen
            log_extra.update(queries_extra)

            logger.warning(
                msg=f"Slow Request detected: {path}",
                extra=log_extra,
            )
