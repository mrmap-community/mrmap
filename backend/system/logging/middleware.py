from logging import Logger

from django.conf import settings
from django.db import connection
from django.utils import timezone
from system.logging.util import interpolate_sql

logger: Logger = settings.ROOT_LOGGER


class LogSlowRequestsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.threshold_ms = int(
            getattr(settings, "LOG_LONG_RUNNING_REQUEST_THRESHOLD_MS", 400))

    def get_duration_ms(self, start):
        return int((timezone.now() - start).total_seconds() * 1000)

    def __call__(self, request):
        request_start = timezone.now()
        collected_queries = []

        def query_logger_execute_wrapper(execute, sql, params, many, context):
            start_time = timezone.now()
            try:
                return execute(sql, params, many, context)
            finally:
                duration_ms = self.get_duration_ms(start_time)
                # Keep collection cheap; interpolate only for slow requests.
                if isinstance(params, (list, dict)):
                    params = params.copy()
                collected_queries.append(
                    {
                        "sql": sql,
                        "params": params,
                        "duration_ms": duration_ms
                    }
                )

        with connection.execute_wrapper(query_logger_execute_wrapper):
            response = self.get_response(request)

        self._response(request, response, collected_queries,
                       self.get_duration_ms(request_start))
        return response

    def _response(self, request, response, queries, request_duration_ms):
        if request_duration_ms <= self.threshold_ms:
            return

        # Basisdaten
        structured_data = {
            "metaSDID@request": {
                "path": request.build_absolute_uri(),
                "duration_ms": request_duration_ms,
                "status_code": response.status_code if response else 500,
                "method": request.META.get("REQUEST_METHOD", "GET"),
            },
        }

        if queries:
            structured_data = {
                "metaSDID@message": {"msg": "Slow Request Detected"},
                **structured_data
            }
            query_meta = structured_data.setdefault("metaSDID@queries", {})
            for idx, q in enumerate(queries, start=1):
                sql = interpolate_sql(q["sql"], q["params"])
                clean_sql = sql.replace('\r', ' ').replace('\n', ' ').replace('\t', ' ')
                query_meta.update(
                    {
                        f"{idx}_sql": clean_sql,
                        f"{idx}_duration_ms": q["duration_ms"]
                    }
                )

        logger.warning(
            msg="Slow Request Detected",
            extra={
                "disable_python_meta": True,
                "structured_data": structured_data,
            }
        )
