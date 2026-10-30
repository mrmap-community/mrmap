from django_celery_results.backends.cache import CacheBackend
from redis.exceptions import ConnectionError, TimeoutError


class RetryingCacheBackend(CacheBackend):
    """Let Celery retry Redis result operations without rerunning task bodies."""

    def exception_safe_to_retry(self, exc):
        return isinstance(exc, (ConnectionError, TimeoutError))
