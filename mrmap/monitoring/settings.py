import logging
from django.utils.translation import gettext_lazy as _

monitoring_logger = logging.getLogger('MrMap.monitoring')

# Defines monitoring constants
MONITORING_TIME = "23:59:00"
MONITORING_REQUEST_TIMEOUT = 30  # seconds

# Define some thresholds for monitoring health check
WARNING_RESPONSE_TIME = 300     # time in ms (milliseconds)
CRITICAL_RESPONSE_TIME = 600    # time in ms (milliseconds)
WARNING_RELIABILITY = 95        # percentage
CRITICAL_RELIABILITY = 90        # percentage

MONITORING_THRESHOLDS = {'WARNING_RESPONSE_TIME': WARNING_RESPONSE_TIME,
                         'CRITICAL_RESPONSE_TIME': CRITICAL_RESPONSE_TIME,
                         'WARNING_RELIABILITY': WARNING_RELIABILITY,
                         'CRITICAL_RELIABILITY': CRITICAL_RELIABILITY, }

# Some pre defined health messages
DEFAULT_UNKNOWN_MESSAGE = _(f'The health state is unknown, cause no health checks runs for this resource.')
