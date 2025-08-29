import json
import os
import uuid
from logging import Logger
from pathlib import Path

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
        self.start = timezone.now()
        collected_queries = []

        def query_logger_execute_wrapper(execute, sql, params, many, context):
            start_time = timezone.now()
            try:
                return execute(sql, params, many, context)
            finally:
                interpolated_sql = interpolate_sql(sql, params)
                # Ersetze alle Zeilenumbrüche und Tabs durch Leerzeichen
                clean_sql = interpolated_sql.replace(
                    '\n', ' ').replace('\t', ' ')
                # Optional: Mehrere Leerzeichen auf eins reduzieren
                clean_sql = ' '.join(clean_sql.split())
                collected_queries.append(
                    {
                        "sql": clean_sql,
                        "duration_ms": self.get_duration_ms(start_time)
                    }
                )

        with connection.execute_wrapper(query_logger_execute_wrapper):
            response = self.get_response(request)

        self._response(request, response, collected_queries)
        return response

    def _response(self, request, response=None, queries=None, exception=None):
        request_duration_ms = self.get_duration_ms(self.start)
        if request_duration_ms <= self.threshold_ms:
            return
        # slow request detected

        request_id = uuid.uuid4()
        # Basisdaten
        structured_data = {
            "metaSDID@request": {
                "request_id": str(request_id),
                "details_json": request.build_absolute_uri(f"{settings.MEDIA_URL}logs/{request_id}.json"),
                "path": request.build_absolute_uri(),
                "duration_ms": request_duration_ms,
                "status_code": response.status_code if response else 500,
                "method": request.META.get("REQUEST_METHOD", "GET"),
            },
        }

        if queries:
            log_details = {
                "metaSDID@message": {"msg": "Slow Request Detected"},
                **structured_data
            }
            query_meta = log_details.setdefault("metaSDID@queries", {})
            for idx, q in enumerate(queries, start=1):
                query_meta.update(
                    {
                        f"{idx}_sql": q["sql"],
                        f"{idx}_duration_ms": q["duration_ms"]
                    }
                )
        try:
            path = Path(os.path.join(settings.MEDIA_ROOT, "logs"))
            path.mkdir(parents=True, exist_ok=True)

            with open(path / f"{request_id}.json", "w+") as fp:
                # cause some syslog server implementations are limiting message size, we store verbose details as simple media files
                json.dump(log_details, fp)
        except Exception:
            pass

        logger.warning(
            msg="Slow Request Detected",
            extra={
                "disable_python_meta": True,
                "structured_data": structured_data,
            }
        )
