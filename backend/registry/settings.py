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


# How long one GetRecords request may take. The time scales with the requested page size, so a
# big page which is only slow is not mistaken for a refused one and shrunk away (#694). The
# per-record share is what the flat 60 s of the historical step size of 50 meant, the base covers
# connect and parse time, and the cap keeps a pathological size from occupying a worker forever.
HARVESTING_REQUEST_TIMEOUT_BASE_SECONDS = 10
HARVESTING_REQUEST_TIMEOUT_PER_RECORD_SECONDS = 1.2
HARVESTING_REQUEST_TIMEOUT_MAX_SECONDS = 900


# How long one request of a service registration may wait for its server: the
# capabilities document and every remote metadata document which that document
# references. The value is shared on purpose - both requests are asked of the
# same host within one registration, so a host which cannot answer a plain GET
# within this window is a host Mr. Map must not wait for. It has to be said
# explicitly because nothing else bounds these requests: no
# ``task_time_limit`` or ``soft_time_limit`` of the deployment stops a task
# which sits in a request, and a server which accepts the connection and then
# stays silent would hold a worker of the ``download`` queue for every
# registration which references one of its documents (#1260).
REGISTRATION_REQUEST_TIMEOUT_SECONDS = 15


# The bounds of the registration reference work queue (#1263). A delivery of
# one reference holds its work row under a lease: long enough that a healthy
# fetch-and-import is never cut short (one request is itself bounded by
# REGISTRATION_REQUEST_TIMEOUT_SECONDS, the import is a local persist), short
# enough that a worker which dies with a claim is back in play within one
# recovery pass of the hourly sweep. The recovery batch bounds what one pass
# re-drives, so a long incident recovers progressively instead of flooding
# the ``download`` queue. The grace is how long an unreferenced file below a
# process prefix may survive: the window between writing a document to
# storage and committing the row which names it is bounded by one import, and
# the grace must comfortably exceed it - the sweep rather leaves a byte for
# the next pass than deletes a document a live attempt is reading.
REGISTRATION_REFERENCE_LEASE_SECONDS = 900
REGISTRATION_RECOVERY_BATCH_SIZE = 500
REGISTRATION_ORPHAN_FILE_GRACE_SECONDS = 120


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
