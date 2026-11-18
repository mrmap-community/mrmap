"""The single flight of ``extras.locks`` (#1411).

A flight exists so that concurrent workers do one piece of work instead of two,
and so that a worker which dies does not lock that work away. Both halves are
pinned here: who may work, and how a lease stops meaning anything once it ran
out. The cache is the substrate, so these run on a local-memory cache and need no
database.

A lease of its own is never shorter than a second - which is the point of one of
the tests below - so the fixtures which need an already expired lease plant the
key in the cache directly and wait a few milliseconds over it.
"""

from time import sleep
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase
from django.test.utils import override_settings
from extras.locks import ANSWER_SUFFIX, SingleFlight

LOC_MEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "single-flight-tests",
    },
}


@override_settings(CACHES=LOC_MEM)
class SingleFlightTest(SimpleTestCase):
    """One holder works, the others join, and an expired lease binds nobody."""

    def setUp(self):
        cache.clear()

    def flight(self, lease_seconds=60, key="work/a"):
        return SingleFlight(key=key, lease_seconds=lease_seconds)

    def test_one_caller_takes_the_work(self):
        self.assertTrue(self.flight().acquire())

    def test_a_second_caller_does_not_get_the_same_work(self):
        self.assertTrue(self.flight().acquire())
        self.assertFalse(self.flight().acquire(),
                         "two holders of one key are the thing this avoids")

    def test_a_holder_which_re_acquires_is_not_joined_to_itself(self):
        claim = self.flight()
        self.assertTrue(claim.acquire())
        self.assertFalse(claim.acquire(), "a holder may not join its own flight")

    def test_another_key_is_untouched(self):
        self.assertTrue(self.flight(key="work/a").acquire())
        self.assertTrue(self.flight(key="work/b").acquire(),
                        "two pieces of work are two flights")

    def test_the_lease_is_reported_as_held(self):
        claim = self.flight()
        self.assertFalse(claim.held())
        claim.acquire()
        self.assertTrue(claim.held())

    def test_the_holder_hands_the_lease_back(self):
        claim = self.flight()
        claim.acquire()
        claim.release()
        self.assertFalse(claim.held())
        self.assertTrue(self.flight().acquire())

    def test_a_holder_which_died_stops_keeping_the_work(self):
        """The crash of a holder costs one lease, not the work: whoever asks after
        it ran out takes the work over."""
        cache.add("work/a", "a-holder-which-died", 0.01)
        self.assertFalse(self.flight().acquire())

        sleep(0.05)

        self.assertFalse(self.flight().held())
        self.assertTrue(self.flight().acquire())

    def test_a_slow_holder_does_not_unlock_the_work_it_no_longer_owns(self):
        """Its lease ran out while it was still working and a second holder took
        the work; handing the lease back afterwards must not free the work of that
        second holder."""
        cache.add("work/a", "a-holder-which-is-still-working", 0.02)
        sleep(0.05)
        second = self.flight()
        self.assertTrue(second.acquire())

        SingleFlight(key="work/a", lease_seconds=60,
                     token="a-holder-which-is-still-working").release()

        self.assertTrue(second.held(), "the new holder still owns the work")
        self.assertFalse(self.flight().acquire(),
                         "and nobody else gets the work either")

    def test_finishing_leaves_the_outcome_for_the_callers_which_joined(self):
        claim = self.flight()
        claim.acquire()
        self.assertIsNone(claim.answered())

        claim.finish(("stored", 12))

        self.assertEqual(claim.answered(), ("stored", 12))
        self.assertFalse(claim.held(), "an answered flight frees the work")
        self.assertTrue(self.flight().acquire(),
                        "a caller which arrives after the answer still gets a "
                        "flight of its own")

    def test_taking_the_lease_clears_the_outcome_of_the_flight_before(self):
        """An outcome belongs to the deliveries which overlapped with the work it
        answers. A caller which arrives after that flight is over starts a flight of
        its own and must not be answered from what the old holder left behind - the
        leftover of a finished flight is not an answer for the next attempt."""
        first = self.flight()
        first.acquire()
        first.finish(("stored", 12))
        self.assertEqual(self.flight().answered(), ("stored", 12),
                         "while nobody took the lease again, the outcome is readable")

        second = self.flight()

        self.assertTrue(second.acquire())
        self.assertIsNone(second.answered(),
                          "the new flight knows nothing of the finished one")

    def test_the_outcome_is_kept_below_a_key_of_its_own(self):
        """The lease and the outcome of one key must not overwrite each other: a
        holder which is still working says so, while the answer of the one before
        is still readable below its own key."""
        claim = self.flight()
        claim.acquire()

        self.assertIsNone(cache.get(f"work/a{ANSWER_SUFFIX}"))
        self.assertEqual(cache.get("work/a"), claim.token)

    def test_a_lease_shorter_than_a_second_is_not_a_lease(self):
        """A lease which expires before the work it protects could even begin
        would hand the work to a second caller for nothing."""
        self.assertEqual(self.flight(lease_seconds=0).lease_seconds, 1)
        self.assertEqual(self.flight(lease_seconds=0.2).lease_seconds, 1)
        self.assertEqual(self.flight(lease_seconds=1.2).lease_seconds, 2)

    def test_lease_and_outcome_expire_with_the_time_of_the_work(self):
        """Both are bounded by the lease: a lease which outlived the work it
        protects would keep the work from a second attempt for nothing, and an
        outcome which outlived it would be answered to a caller which is not
        waiting for this work anymore."""
        claim = self.flight(lease_seconds=42)
        with patch.object(cache, "add", wraps=cache.add) as add, \
                patch.object(cache, "set", wraps=cache.set) as write:
            claim.acquire()
            claim.finish(("stored", 1))

        self.assertEqual([call.args[2] for call in add.call_args_list], [42])
        self.assertEqual([call.args[2] for call in write.call_args_list], [42])
