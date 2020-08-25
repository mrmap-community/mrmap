import logging
from django.utils.translation import gettext_lazy as _

monitoring_logger = logging.getLogger('MrMap.monitoring')

# Define some thresholds for monitoring health check
WARNING_RESPONSE_TIME = 50     # time in ms (milliseconds)
CRITICAL_RESPONSE_TIME = 500    # time in ms (milliseconds)

# Regex for http status code for success availability
SUCCESS_HTTP_CODE_REGEX = r"(20[0-8])|(401)"    # all 200er and 401 status codes are ok

# Some pre defined health messages
DEFAULT_UNKNOWN_MESSAGE = _(f'The health state is unknown, cause no health checks runs for this resource.')
