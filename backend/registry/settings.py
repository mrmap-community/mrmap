from django.utils.translation import gettext_lazy as _
from registry.enums.service import OGCOperationEnum

MRMAP_CSW_PK = "650d436a-5837-4cc3-9cb5-6a0a5488ff09"

SECURE_ABLE_WMS_OPERATIONS = [OGCOperationEnum.GET_MAP,
                              OGCOperationEnum.GET_FEATURE_INFO]
SECURE_ABLE_WFS_OPERATIONS = [OGCOperationEnum.GET_FEATURE,
                              OGCOperationEnum.TRANSACTION]
SECURE_ABLE_OPERATIONS = SECURE_ABLE_WMS_OPERATIONS + SECURE_ABLE_WFS_OPERATIONS
SECURE_ABLE_OPERATIONS_LOWER = [operation.label.lower()
                                for operation in SECURE_ABLE_OPERATIONS]

# The step sizes a harvesting run may ask a catalogue with. A GetRecords request
# has to ask for at least one record, and the size a run works with is stored in
# a smallint of the job (see registry.models.harvest.HarvestingJob), so 32767 is
# the largest size a run can carry. A catalogue which names a size outside of
# this range cannot be harvested at all and is answered with a validation error.
MIN_STEP_SIZE = 1
MAX_STEP_SIZE = 32767


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
MONITORING_DEFAULT_UNKNOWN_MESSAGE = _(
    'The health state is unknown, cause no health checks runs for this resource.')

# Some pre defined conformity messages
CONFORMITY_DEFAULT_UNKNOWN_MESSAGE = _('The validation state is unknown.')
CONFORMITY_DEFAULT_SUCCESS_MESSAGE = _('The resource is valid.')
CONFORMITY_DEFAULT_FAIL_MESSAGE = _('The resource is invalid.')


METADATA_URL_BLACKLIST = ["request=GetMetadata"]
