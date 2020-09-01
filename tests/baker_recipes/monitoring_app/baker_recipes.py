from model_bakery.recipe import Recipe, foreign_key
from datetime import datetime, timedelta
from monitoring.models import MonitoringRun, Monitoring, HealthState
from monitoring.settings import WARNING_RESPONSE_TIME, CRITICAL_RESPONSE_TIME
from tests.baker_recipes.service_app.baker_recipes import active_wms_service_metadata

monitoring_run = Recipe(
    MonitoringRun,
    end=datetime.now(),
    duration=timedelta(seconds=1),
)

monitoring_result = Recipe(
    Monitoring,
    metadata=foreign_key(active_wms_service_metadata),
    duration=timedelta(milliseconds=WARNING_RESPONSE_TIME-1),
    status_code=200,
    available=True,
    monitored_uri='example.com',
    monitoring_run=foreign_key(monitoring_run),
)
