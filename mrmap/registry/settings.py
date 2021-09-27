from django.utils.translation import gettext_lazy as _

from registry.enums.service import OGCOperationEnum

SECURE_ABLE_WMS_OPERATIONS = [OGCOperationEnum.GET_MAP.value,
                              OGCOperationEnum.GET_FEATURE_INFO.value]
SECURE_ABLE_WFS_OPERATIONS = [OGCOperationEnum.GET_FEATURE.value,
                              OGCOperationEnum.TRANSACTION.value]
SECURE_ABLE_OPERATIONS = SECURE_ABLE_WMS_OPERATIONS + SECURE_ABLE_WFS_OPERATIONS
SECURE_ABLE_OPERATIONS_LOWER = [operation.lower() for operation in SECURE_ABLE_OPERATIONS]

# Defines monitoring constants
MONITORING_TIME = "23:59:00"
MONITORING_REQUEST_TIMEOUT = 30  # seconds

# Define some thresholds for monitoring health check
WARNING_RESPONSE_TIME = 300  # time in ms (milliseconds)
CRITICAL_RESPONSE_TIME = 600  # time in ms (milliseconds)
WARNING_RELIABILITY = 95  # percentage
CRITICAL_RELIABILITY = 90  # percentage

MONITORING_THRESHOLDS = {'WARNING_RESPONSE_TIME': WARNING_RESPONSE_TIME,
                         'CRITICAL_RESPONSE_TIME': CRITICAL_RESPONSE_TIME,
                         'WARNING_RELIABILITY': WARNING_RELIABILITY,
                         'CRITICAL_RELIABILITY': CRITICAL_RELIABILITY, }

# Some pre defined health messages
MONITORING_DEFAULT_UNKNOWN_MESSAGE = _(f'The health state is unknown, cause no health checks runs for this resource.')

# Some pre defined conformity messages
CONFORMITY_DEFAULT_UNKNOWN_MESSAGE = _(f'The validation state is unknown.')
CONFORMITY_DEFAULT_SUCCESS_MESSAGE = _(f'The resource is valid.')
CONFORMITY_DEFAULT_FAIL_MESSAGE = _(f'The resource is invalid.')