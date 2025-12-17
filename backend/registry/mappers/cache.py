import threading
import time
from collections import OrderedDict
from uuid import UUID


# -------------------------------------------------------------------
# Cache
# -------------------------------------------------------------------


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


