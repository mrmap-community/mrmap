"""Bounded, reviewable values for the dimensions of the ``mrmap.*`` metrics.

A metric dimension is a storage decision, and an unbounded one is the outage
nobody wants: a task name an attacker or a plugin chooses, a queue name from a
foreign broker, a route nobody registered. So every value which becomes a
dimension goes through this module, which knows exactly two answers: a value from
the reviewed list, or one of the fixed bucket names.

Nothing here invents a value: :func:`route` never substitutes a request path for a
missing route template (ADR-0003 says so explicitly), and an unknown task is
``other`` rather than a truncated version of the real name - a truncated name is
still a name.
"""

#: the fixed values of the contract
OTHER = "other"
UNMATCHED = "unmatched"
UNRESOLVED = "unresolved"

#: the nine methods of the HTTP semantics plus the fallback of upstream
#: ``sanitize_method``; anything else an implementation produces is folded here
HTTP_METHODS = frozenset({
    "CONNECT", "DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT",
    "TRACE", "_OTHER",
})

#: the error categories of the contract: finite, reviewed, and never a free-form
#: exception class or message an attacker or a plugin writes
ERROR_TYPES = frozenset({"timeout", "connection", "server", "client", "other"})

#: how many distinct task names one process may remember before everything new
#: folds into ``other``. The budget is a per-process memory bound, not a claim
#: about the deployment: a worker which has seen ``budget`` classes is a worker
#: whose registry is not the reviewed one.
_SEEN_CACHE_LIMIT = 4096


class _BoundedSet:
    """A set which stops growing at a fixed size, so a cache cannot be flooded."""

    def __init__(self, limit=_SEEN_CACHE_LIMIT):
        self._limit = limit
        self._seen = {}

    def remember(self, value, limit=None):
        """Whether ``value`` fits into the budget (and is now remembered)."""
        if value in self._seen:
            return True
        cap = self._limit if limit is None else min(limit, self._limit)
        if cap <= 0 or len(self._seen) >= cap:
            return False
        self._seen[value] = True
        return True

    def clear(self):
        self._seen.clear()

    def __len__(self):
        return len(self._seen)


#: values this process has already mapped (a dict as an ordered set); the limits
#: bound the mapping itself, which is what bounds the cardinality of the metric
_seen_tasks = _BoundedSet()
_seen_routes = _BoundedSet(2048)


def task_class(task_name, allowed=(), budget=200):
    """The reviewed class of a Celery task name.

    ADR-0003 allows only *registered first-party* names as a dimension, and
    anything else becomes ``other``. Three answers, in this order:

    *   an allowlist the operator wrote wins, including the last dotted spelling
        of an entry (``registry.tasks.harvest.run`` for an entry ``harvest.run``),
        because the module path of a task is an implementation detail;
    *   otherwise the name must be one this process can actually execute - the
        Celery registry is the first-party list, and a name which is not in it
        cannot have been executed by this worker either;
    *   everything else is ``other``, never a truncated version of the real name:
        a truncated name is still a name.

    The budget is a second guard rather than the mechanism. It bounds what one
    process remembers, so a plugin which registers an unbounded number of dynamic
    tasks cannot grow a dimension without bound.
    """
    if not task_name:
        return OTHER
    name = str(task_name).strip()
    if not name:
        return OTHER
    if allowed:
        # the reviewed spelling is the answer, and a registered name is allowed to
        # be it in full: an operator who writes "harvest.run" means the task whose
        # module path is "registry.tasks.harvest.run", because the module path of
        # a task is an implementation detail of this deployment
        for entry in allowed:
            if name == entry or name.endswith("." + entry):
                return entry
        return OTHER
    if name.startswith("celery."):
        # celery's own housekeeping tasks (chord cleanup, heartbeat) describe the
        # machinery, not the deployment's work
        return OTHER
    if name not in _registered_task_names():
        return OTHER
    return name if _seen_tasks.remember(name, limit=budget) else OTHER


_registered_cache = {"value": None}


def _registered_task_names():
    """The task names this process can execute, read once per process.

    The Celery registry is the only honest first-party list: a name is in it
    because importable code of this deployment or an installed plugin declared it.
    When no app is configured at all the answer is empty, and then *nothing* is a
    known class - which folds every series into ``other`` rather than trusting a
    name the process never registered.
    """
    if _registered_cache["value"] is not None:
        return _registered_cache["value"]
    names = frozenset()
    try:
        from celery import current_app
        names = frozenset(str(name) for name in (current_app.tasks or {}))
    except Exception:
        names = frozenset()
    _registered_cache["value"] = names
    return names


def queue(queue_name):
    """The declared queue of an attempt, or ``other``.

    The declared queues of the deployment are few and fixed
    (``MrMap/celery_queues.py``); a routing key which is not one of them came
    from a producer this deployment does not own, and becomes one series named
    ``other`` rather than a series per foreign name.

    The number of names this may answer is bounded by :func:`_declared_queues`,
    which reads the operator's budget from the settings; a caller cannot widen it.
    """
    if not queue_name:
        return OTHER
    name = str(queue_name).strip()
    if not name or len(name) > 64:
        return OTHER
    declared = _declared_queues()
    if name in declared:
        return name
    return OTHER


_declared_cache = {"value": None, "limit": None}


def _declared_queues():
    """The queue names ``MrMap/settings.py`` declares, read once per process.

    Read from settings rather than from the celery app, because the worker's
    ``amqp.queues`` reflects its ``-Q`` option and a narrowed worker would then
    call the queues it does not consume ``other`` - which is the opposite of what
    the dimension means.
    """
    from django.conf import settings

    limit = getattr(settings, "OTEL_MAX_QUEUES", 16)
    if _declared_cache["value"] is not None and _declared_cache["limit"] == limit:
        return _declared_cache["value"]
    names = set()
    for entry in getattr(settings, "CELERY_TASK_QUEUES", ()) or ():
        name = getattr(entry, "name", None) or (
            entry.get("name") if isinstance(entry, dict) else None)
        if name:
            names.add(str(name))
    default = getattr(settings, "CELERY_TASK_DEFAULT_QUEUE", None)
    if default:
        names.add(str(default))
    names = set(names)
    if len(names) > limit:
        # the budget of the issue is a hypothesis about the registry (#1779
        # names 16); when the real registry is bigger, the bigger number is the
        # setting to raise - and the operator hears about it once, here.
        from logging import getLogger
        getLogger("MrMap.telemetry").warning(
            "opentelemetry: the deployment declares %d queues, more than "
            "MRMAP_OTEL_MAX_QUEUES=%d; raise the budget or queues will fold "
            "into '%s' (#1779).", len(names), limit, OTHER)
        names = set(list(names)[:limit])
    _declared_cache["value"] = names
    _declared_cache["limit"] = limit
    return names


def route(route_template, budget=500):
    """The registered route template of a request, or the honest absence.

    ``http.route`` must be a *template*: ``api/services/wms/<int:resource_id>/``
    says one thing about the deployment, ``api/services/wms/4211/`` says one
    thing per resource and would exceed the whole instrument budget on its own.
    A resolver miss is ``unresolved`` and a view without a template is
    ``unmatched``; the request path is never a substitute, which is what turns
    "no cardinality risk" from a hope into a property of the code.
    """
    if not route_template:
        return UNRESOLVED
    value = str(route_template).strip()
    if not value:
        return UNRESOLVED
    if value.startswith("/"):
        # a path rather than a template: a leading slash never appears in a
        # Django ``path()`` pattern, so this is somebody's request path.
        return UNMATCHED
    if len(value) > 255 or "?" in value or value.count("/") > 64:
        return UNMATCHED
    # the number of distinct templates one process may contribute; beyond the
    # budget the route is not a URLconf of this deployment anymore. The view's
    # cardinality cap is the hard bound, this is the cheap first look and the
    # reason a flooding scanner never reaches the aggregator.
    if not _seen_routes.remember(value, limit=budget):
        return UNMATCHED
    return value


def method(value):
    """One of the nine methods, or ``_OTHER`` (upstream's own spelling)."""
    if not value:
        return "_OTHER"
    name = str(value).strip().upper()
    return name if name in HTTP_METHODS else "_OTHER"


def status(value):
    """An integer status of 100..599, or ``None`` when there is no response."""
    try:
        code = int(value)
    except (TypeError, ValueError):
        return None
    return code if 100 <= code <= 599 else None


def scheme(value):
    """``http``/``https`` only - never a scheme a proxy asserted."""
    if not value:
        return None
    name = str(value).strip().lower()
    return name if name in ("http", "https") else None


def error_type(value):
    """A reviewed error category, never an exception class name.

    Upstream sets ``error.type`` to ``type(exception).__qualname__`` for client
    spans; that is a plugin's class name becoming a dimension, so it maps to the
    closest reviewed category here and the specific class stays where it belongs.
    """
    if not value:
        return "other"
    name = str(value).strip().lower()
    if name in ERROR_TYPES:
        return name
    for category in ("timeout", "connection"):
        if category in name:
            return category
    if "server" in name or "5" in name:
        return "server"
    if "client" in name or "4" in name:
        return "client"
    return "other"


def remote_kind(url_or_host):
    """What kind of remote call this is, without naming the remote.

    ``wms``/``wfs``/``csw``/``other`` is the only reading of an OGC endpoint a
    metric may carry: the hostname of a third party's service is that third
    party's business identifier, and the query string of a GetCapabilities is
    somebody else's input.
    """
    if not url_or_host:
        return OTHER
    text = str(url_or_host).lower()
    for kind in ("wms", "wfs", "csw"):
        if kind in text:
            return kind
    return OTHER


def reset_caches():
    """Forget what this process has memorized; the seam the tests isolate with."""
    _seen_tasks.clear()
    _seen_routes.clear()
    _registered_cache["value"] = None
    _declared_cache["value"] = None
    _declared_cache["limit"] = None
