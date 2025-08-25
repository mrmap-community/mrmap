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
            getattr(settings, "LOG_LONG_RUNNING_REQUEST_THRESHOLD_MS", 500))

    def __call__(self, request):
        self.start = timezone.now()

        response = self.get_response(request)

        self._response(request, response)

        return response

    def _response(self, request, response=None, exception=None):
        end = timezone.now()
        start = self.start
        time_delta = end - start

        # Requestdauer in Millisekunden
        request_duration_ms = int(time_delta.total_seconds() * 1000)

        if request_duration_ms > self.threshold_ms:
            path = 'http://' + request.get_host() + request.get_full_path()
            view, args, kwargs = resolve(request.path)

            # Query Count
            if hasattr(connection, 'query_count'):
                query_count = connection.query_count
            else:
                query_count = len(connection.queries) or None

            # Query Dauer summieren + Detail-Felder bauen
            query_duration_ms = None
            queries_extra = {}
            if connection.queries:
                try:
                    query_duration_ms = int(
                        sum(float(q.get("time", 0))
                            for q in connection.queries) * 1000
                    )
                    for idx, q in enumerate(connection.queries, start=1):
                        queries_extra[f"query_{idx}"] = {
                            "sql": q.get("sql"),
                            "duration_ms": int(float(q.get("time", 0)) * 1000),
                        }
                except Exception:
                    query_duration_ms = None

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
