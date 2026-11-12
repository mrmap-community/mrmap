"""#1028: the background cleanup thread of GlobalXmlCache must survive its work.

_cleanup_expired_locked() mutates cls._data and documents that the caller must
hold cls._lock. The cleanup loop used to call it without the lock, so a
concurrent set() mutated the OrderedDict mid-iteration and the resulting
"RuntimeError: OrderedDict mutated during iteration" killed the thread -
resurrected only by the next set(), dying again on the next cycle. While the
thread was dead, entries whose key was never read again (per-document keys of
a harvest) stayed in memory past their TTL. These tests pin the contract the
loop broke:

* the cleanup cycle takes cls._lock, so it never touches cls._data while a
  writer holds it,
* one failing cycle does not end the loop - the thread keeps cleaning,
* concurrent set()/get() traffic against an aggressive TTL leaves the thread
  alive and raises nothing inside it (the reproduction of the issue).

The cache is process-global class state; every test stops the thread and
restores the class attributes so sibling modules keep the defaults.
"""

import threading
import time
from unittest.mock import patch

from django.test import SimpleTestCase

from registry.mappers.cache import GlobalXmlCache


class GlobalXmlCacheCleanupTest(SimpleTestCase):
    def setUp(self):
        # A previous test module may have started the thread through set() with
        # the production interval; take it over so this module starts its own
        # thread under the short intervals its timings assume.
        self._reset_cleanup_thread()
        self.addCleanup(self._reset_cleanup_thread)

    def _reset_cleanup_thread(self):
        GlobalXmlCache._stop_event.set()
        thread = GlobalXmlCache._cleanup_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=5)
        GlobalXmlCache._cleanup_thread = None
        GlobalXmlCache._stop_event.clear()
        GlobalXmlCache._data.clear()
        GlobalXmlCache._ttl_seconds = 3600
        GlobalXmlCache._cleanup_interval = 300

    def _wait_for(self, predicate, timeout=5.0):
        """Poll until predicate() holds; True if it held within the timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.01)
        return predicate()

    def test_cleanup_cycle_waits_for_the_lock(self):
        """An expired entry is not removed while a writer holds cls._lock.

        The entry expires 0.1 s after it is set; the test then holds the lock
        for 0.4 s, i.e. across tens of 0.01 s cleanup cycles. Without the lock
        the cycle deletes the entry right through the writer - the #1028 race.
        """
        GlobalXmlCache._ttl_seconds = 0.1
        GlobalXmlCache._cleanup_interval = 0.01
        GlobalXmlCache.set("expired-key", "value")

        with GlobalXmlCache._lock:
            time.sleep(0.4)
            self.assertIn(
                "expired-key", GlobalXmlCache._data,
                "cleanup removed an entry while the lock was held")

        # The loop is not just blocked, it is intact: it cleans as soon as it
        # gets the lock back.
        self.assertTrue(
            self._wait_for(lambda: "expired-key" not in GlobalXmlCache._data),
            "cleanup thread never removed the expired entry")

    def test_cleanup_thread_survives_a_failing_cycle(self):
        """One cycle's exception is logged, not fatal for the loop."""
        GlobalXmlCache._cleanup_interval = 0.01
        with patch.object(
                GlobalXmlCache, "_cleanup_expired_locked",
                side_effect=[RuntimeError("simulated cycle failure"),
                             None]) as cleanup:
            GlobalXmlCache._start_cleanup_thread()
            self.assertTrue(
                self._wait_for(lambda: cleanup.call_count >= 2),
                "the cleanup thread died after its first failing cycle")
            self.assertTrue(GlobalXmlCache._cleanup_thread.is_alive())

    def test_concurrent_set_and_get_keep_the_thread_alive(self):
        """The reproduction of #1028: spam set()/get() against a 1 ms TTL.

        The issue measured 11 thread deaths from 200 000 set() calls; a death
        surfaces through threading.excepthook as RuntimeError("OrderedDict
        mutated during iteration"). The fixed loop iterates under cls._lock,
        so no such exception can arise and none is expected.
        """
        deaths = []
        original_hook = threading.excepthook
        threading.excepthook = lambda args: deaths.append(args.exc_value)
        self.addCleanup(
            setattr, threading, "excepthook", original_hook)

        GlobalXmlCache._ttl_seconds = 0.001
        GlobalXmlCache._cleanup_interval = 0.001

        errors = []

        def spam_sets():
            try:
                for i in range(50000):
                    GlobalXmlCache.set(f"k{i}", i)
            except Exception as exc:  # pragma: no cover - failure path
                errors.append(exc)

        def spam_gets():
            try:
                for i in range(50000):
                    GlobalXmlCache.get(f"k{i // 2}")
            except Exception as exc:  # pragma: no cover - failure path
                errors.append(exc)

        writer = threading.Thread(target=spam_sets)
        reader = threading.Thread(target=spam_gets)
        writer.start()
        reader.start()
        writer.join(timeout=30)
        reader.join(timeout=30)

        self.assertEqual(errors, [])
        self.assertEqual(
            deaths, [],
            f"cleanup thread died inside the run: {deaths!r}")
        self.assertTrue(GlobalXmlCache._cleanup_thread.is_alive())
