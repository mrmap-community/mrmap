"""Coalescing concurrent work on one key: the single flight.

Two workers can be asked for the same thing at the same time - a broker which
redelivers one message, a scheduled fan-out which fires again while its previous
run is still working, two consumers of one queue. When the answer is something
which gets written down anyway, the second ask costs a request to a third party
and answers nothing the first one would not have answered.

The single flight is the coordination which avoids that second ask: one caller
takes a bounded lease named after the work, does the work and leaves its outcome
behind; every caller which arrives while the lease is held waits for that outcome
instead of doing the work again. A caller whose lease runs out - because it died,
or because its work outlived the lease it took - stops keeping the work from a
second attempt, so nothing which failed is locked away.

The substrate is the cache the deployment already shares between its workers
(``settings.CACHES``). The guarantees are the ones a cache gives and no more: the
flight makes duplicate work unlikely, it never makes work correct. A lease can
expire while its holder is still running, which lets a second holder do the same
work; whatever a flight protects must therefore stay idempotent, and a caller
which needs the answer rather than a guess reads its own result back. The
harvesting of a catalogue page does exactly that (#1411): the claim keeps two
deliveries of one page from asking the catalogue twice, while the stored rows of
that page - written by ``HarvestingJob._store_page``, which settles two workers
storing one page under the lock of the job - stay the authority over what a
snapshot holds.

A deployment whose cache belongs to a single process coalesces within that
process only: an optimisation lost, not a correctness problem.
"""

from math import ceil
from uuid import uuid4

from django.core.cache import cache

#: the suffix of the key under which a finished flight leaves its outcome
ANSWER_SUFFIX = ":answer"


class SingleFlight:
    """One caller does the work for one key, the others join its outcome.

    Args:
        key (str): what identifies the work. Two callers with the same key are
            two deliveries of one thing; the key must therefore name everything
            which makes the work different, and nothing which does not.
        lease_seconds (int|float): how long the holder may work. It has to
            outlast the work it protects, because a lease which expires early
            hands the work to a second caller while the first one still works.
        token: the identity of this caller within the lease. Two callers of one
            flight must not hold the same token, or one could hand back the
            lease of the other.

    The outcome a flight carries is whatever ``finish`` was given; the flight has
    no opinion about its shape.
    """

    def __init__(self, key, lease_seconds, token=None):
        self.key = key
        self.answer_key = f'{key}{ANSWER_SUFFIX}'
        # a lease shorter than a second would run out before its holder asked
        # the question it is there for
        self.lease_seconds = max(1, ceil(lease_seconds))
        self.token = token or uuid4().hex

    def acquire(self) -> bool:
        """Take the lease of the work.

        Returns:
            bool: whether this caller holds the lease now, and is therefore the
                one which does the work. False also when the lease belongs to
                this caller already, so a holder does not join its own flight.
        """
        return cache.add(self.key, self.token, self.lease_seconds)

    def held(self) -> bool:
        """Whether the work is claimed - by this caller or by another one."""
        return cache.get(self.key) is not None

    def answered(self):
        """The outcome the holder left behind, or None while nothing answered."""
        return cache.get(self.answer_key)

    def finish(self, outcome) -> None:
        """Leave ``outcome`` for the callers which joined, and hand the lease back.

        The outcome lives exactly as long as the lease did: a caller which joined
        this flight is still within that time and reads it, a caller which
        arrives later starts a new flight and asks for itself.
        """
        cache.set(self.answer_key, outcome, self.lease_seconds)
        self.release()

    def release(self) -> None:
        """Hand the lease back, leaving a lease somebody else took alone.

        A holder which could not finish has to release: the retry of the work
        should not have to wait out a lease nobody works under anymore. Reading
        before deleting is not a swap, so a lease which was taken over in that
        moment keeps its new holder - the check is there to keep a slow holder
        from unlocking the work it no longer owns, which is all a lease can be
        asked for without an atomic compare-and-delete in the cache.
        """
        if cache.get(self.key) == self.token:
            cache.delete(self.key)
