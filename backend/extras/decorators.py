import warnings
from functools import wraps

from django.conf import settings
from django.db import connection
from django.test.utils import CaptureQueriesContext


def warn_on_queries(fn):
    """
    Decorator to warn if the wrapped function executes any database queries.

    Usage:

        @warn_on_queries
        def some_method(self):
            ...

    Works at the instance level for model methods.
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        with CaptureQueriesContext(connection) as queries:
            result = fn(*args, **kwargs)
        num_queries = len(queries)
        if num_queries:
            # Build a summary message
            method_name = f"{args[0].__class__.__name__}.{fn.__name__}" if args else fn.__name__
            warnings.warn(
                f"{method_name} triggered {num_queries} database queries. "
                f"Possible missing prefetch/select_related."
            )
            # Optional: print each query for debugging
            if settings.DEBUG:
                for i, q in enumerate(queries, 1):
                    warnings.warn(f"Query {i}: {q.get('sql', '<unknown>')}")
        return result
    return wrapper
