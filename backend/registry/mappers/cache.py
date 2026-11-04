import threading
import time
from collections import OrderedDict
from uuid import UUID


# -------------------------------------------------------------------
# Cache
# -------------------------------------------------------------------


class LocalXmlCache:
    """Instance-scoped stand-in for GlobalXmlCache with the same call surface.

    A mapper running on one of these keeps every parsed instance inside its own
    run: nothing is registered in process-global state, so mapping a document
    for extraction alone leaves no trace. Sub-mappers must be constructed with
    the very same cache object - that is what a shared mapper uuid and the
    element-path lookups between parent and child specs rely on, exactly as
    with the class-level GlobalXmlCache.
    """

    def __init__(self):
        self._data = OrderedDict()

    def set(self, key, value):
        self._data[key] = value

    def get(self, key, default=None):
        return self._data.get(key, default)

    def get_many(self, keys):
        return OrderedDict((key, self._data.get(key)) for key in keys)

    def delete(self, key):
        self._data.pop(key, None)
        # a cached instance is also named in the key list stored under its uuid
        key_list = self._data.get(UUID(key.split(":", 1)[0]))
        if isinstance(key_list, list) and key in key_list:
            key_list.remove(key)

    def add_to_list(self, key, value):
        key_list = self._data.get(key)
        if not isinstance(key_list, list):
            key_list = []
            self._data[key] = key_list
        key_list.append(value)

    def clear(self):
        self._data.clear()


class GlobalXmlCache:
    """Threadsicherer Cache mit TTL und automatischem Hintergrund-Cleanup."""
    _lock = threading.RLock()
    _data = OrderedDict()  # key -> (value, expire_time)
    _ttl_seconds = 3600  # 1 Stunde TTL
    _cleanup_interval = 300  # Alle 5 Minuten cleanup durchführen

    _cleanup_thread = None
    _stop_event = threading.Event()

    @classmethod
    def _start_cleanup_thread(cls):
        if cls._cleanup_thread is None or not cls._cleanup_thread.is_alive():
            cls._stop_event.clear()
            cls._cleanup_thread = threading.Thread(
                target=cls._cleanup_loop, daemon=True)
            cls._cleanup_thread.start()

    @classmethod
    def _cleanup_loop(cls):
        while not cls._stop_event.wait(cls._cleanup_interval):
            cls._cleanup_expired_locked()

    @classmethod
    def stop_cleanup_thread(cls):
        """Stoppt den Hintergrund-Cleanup-Thread (z.B. beim Programmende)."""
        cls._stop_event.set()
        if cls._cleanup_thread:
            cls._cleanup_thread.join()

    @classmethod
    def set(cls, key, value):
        expire_at = time.time() + cls._ttl_seconds
        with cls._lock:
            cls._data[key] = (value, expire_at)
            cls._data.move_to_end(key)
        cls._start_cleanup_thread()

    @classmethod
    def get(cls, key, default=None):
        now = time.time()
        with cls._lock:
            item = cls._data.get(key)
            if item is None:
                return default
            value, expire_at = item
            if expire_at < now:
                del cls._data[key]
                return default
            return value

    @classmethod
    def delete(cls, key):
        with cls._lock:
            cls._data.pop(key, None)

            # ✅ uuid aus key bestimmen
            uuid_str = key.split(":", 1)[0]

            item = cls._data.get(UUID(uuid_str))
            if item:
                key_list, expire = item
                if key in key_list:
                    key_list.remove(key)

    @classmethod
    def get_many(cls, keys):
        now = time.time()
        result = OrderedDict()
        with cls._lock:
            for key in keys:
                item = cls._data.get(key)
                if item is None:
                    result[key] = None
                    continue
                value, expire_at = item
                if expire_at < now:
                    del cls._data[key]
                    result[key] = None
                else:
                    result[key] = value
        return result

    @classmethod
    def add_to_list(cls, key, value):
        with cls._lock:
            item = cls._data.get(key)
            now = time.time()
            expire_at = now + cls._ttl_seconds

            if item is None or item[1] < now:
                # Wenn Schlüssel nicht existiert oder abgelaufen, neuen Eintrag mit Liste starten
                cls._data[key] = ([value], expire_at)
            else:
                lst, expire_at = item
                lst.append(value)
                cls._data[key] = (lst, expire_at)
            cls._data.move_to_end(key)

    @classmethod
    def clear(cls):
        with cls._lock:
            cls._data.clear()

    @classmethod
    def _cleanup_expired_locked(cls):
        """Entfernt abgelaufene Einträge. Muss mit Lock gehalten aufgerufen werden."""
        now = time.time()
        keys_to_delete = [k for k, (_, expire_at)
                          in cls._data.items() if expire_at < now]
        for k in keys_to_delete:
            del cls._data[k]
