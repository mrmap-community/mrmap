"""Print the test labels of one CI shard, so the unit suite can run in pieces.

The unit job is the long pole of the QA workflow and it is not the parts this
repository can still influence: measured on a pull request of 27 Nov, the job
took 27m10s, of which 1m58s was the image build, 1m15s the migrations of the
four test databases, 13s the pulls of postgis, redis and mapserver - and
23m01s the 3490 tests themselves. The suite already runs ``--parallel=4``, which
``docker-compose.dev.yml`` justifies with its own measurements (655 s serial,
356 s with two workers, 225 s with four) and which the four vCPUs of a hosted
runner exhaust: the workers are not paid for in memory (12.1 GiB peak), they are
paid for in cores there are no more of.

What is left is to spread the suite over several runners. This command is the
half that lives inside the image: it discovers the tests exactly the way
``manage.py test`` does and answers which whole modules belong to shard *i* of
*n*. Splitting whole modules rather than single test methods keeps a test class's
shared fixtures, mocks and database touches in one process, which is what the
suite assumes today; and it is what makes the shards reproducible, because the
answer depends only on the tree and on *i* and *n* - no timing, no machine.

Discovery, not a checked-in list: a list that nobody regenerates is a list that
quietly stops covering new files, and a shard that runs nothing is green. The
command therefore refuses to answer when it found no tests at all, and when the
modules it is about to name hold fewer tests than discovery counted.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test.utils import get_runner


def iter_tests(suite):
    """Yield every leaf test of a (possibly nested) test suite."""
    for item in suite:
        if hasattr(item, "id"):
            yield item
        else:
            yield from iter_tests(item)


def module_of(test):
    """The dotted module a discovered test belongs to.

    ``__module__`` of the class is the truth; the id is only the fallback for
    the suite items that are not TestCase methods (doctests included).
    """
    cls = getattr(test, "__class__", None)
    module = getattr(cls, "__module__", None) if cls is not None else None
    if module:
        return module
    test_id = getattr(test, "id", None)
    if test_id:
        return test_id.rsplit(".", 2)[0]
    raise CommandError(f"cannot tell which module {test!r} lives in")


def shard_labels(counts, shard, of):
    """Split whole modules over *of* buckets and return the bucket *shard*.

    Longest-processing-time packing: heaviest module first, and each module joins
    the bucket that currently carries the *fewest tests* - not the fewest modules,
    which would let one 900-test file collect the small ones it already outweighs.
    Ties break by module count and then by name, so the split is the same on every
    runner; the only inputs are ``counts``, ``shard`` and ``of``.
    """
    if of < 1:
        raise CommandError("--of must be at least 1")
    if not 0 <= shard < of:
        raise CommandError(f"--shard must be between 0 and {of - 1}, got {shard}")

    buckets = [[] for _ in range(of)]
    loads = [0] * of
    for module in sorted(counts, key=lambda name: (-counts[name], name)):
        target = min(range(of), key=lambda index: (loads[index], len(buckets[index]), index))
        buckets[target].append(module)
        loads[target] += counts[module]

    if not buckets[shard]:
        raise CommandError(
            f"shard {shard} of {of} got no module - there are more shards than modules "
            f"({len(counts)}), which in CI would read as a green job that ran nothing")
    return sorted(buckets[shard])


class Command(BaseCommand):
    help = ("Print the test labels of one shard of the unit suite, so CI can run "
            "the suite in pieces on separate runners. Whole modules only, so a "
            "test class never runs in two places, and the answer depends on "
            "nothing but the tree and the two numbers.")

    # the shards run before any database exists for them, and discovery needs
    # no checks: do not pay for either, and do not require a reachable postgis
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--shard", type=int, default=0,
                            help="zero-based index of the shard to print")
        parser.add_argument("--of", type=int, default=1,
                            help="total number of shards; 1 means the whole suite")
        parser.add_argument("--top", default="tests",
                            help="package to discover below (default: tests)")

    def handle(self, *args, **options):
        shard, of, top = options["shard"], options["of"], options["top"]

        runner = get_runner(settings)(verbosity=0, interactive=False)
        suite = runner.build_suite([top])

        counts = {}
        counted = 0
        for test in iter_tests(suite):
            module = module_of(test)
            counts[module] = counts.get(module, 0) + 1
            counted += 1

        if not counted:
            raise CommandError(f"discovery below {top!r} found no tests at all")
        if counted != suite.countTestCases():
            raise CommandError(
                f"discovery counted {counted} tests but the suite reports "
                f"{suite.countTestCases()}; the shard would run an unknown share")

        labels = shard_labels(counts, shard, of)
        self.stdout.write("\n".join(labels))
