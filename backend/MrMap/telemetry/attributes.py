"""The attribute names of the telemetry contract, spelled in exactly one place.

Two modules need the same names and must never disagree about them:
:mod:`MrMap.telemetry.policy` decides per name whether it may leave the process,
and :mod:`MrMap.telemetry.metrics` records under them. A literal which drifts
between the two does not fail loudly - it silently drops a dimension from a
series, which is the kind of bug a store only reveals after a release. So the
names live here, in a module which imports neither the SDK nor Django, and both
sides read them from one place.

The upstream names are the semconv spellings of the pinned release. The
``mrmap.*`` names are ADR-0003's own dimensions.
"""

# upstream semantic-convention names, as the pinned instrumentations set them
ATTR_ERROR_TYPE = "error.type"
ATTR_HTTP_METHOD = "http.request.method"
ATTR_URL_SCHEME = "url.scheme"
ATTR_HTTP_STATUS = "http.response.status_code"

# the project's own dimensions, bounded by MrMap.telemetry.naming
ATTR_TASK_CLASS = "mrmap.task.class"
ATTR_QUEUE = "mrmap.queue"
ATTR_TASK_OUTCOME = "mrmap.task.outcome"
ATTR_OBSERVATION_QUALITY = "mrmap.observation.quality"
