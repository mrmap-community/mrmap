"""The shard split has to be complete, stable and loud when it cannot be.

Three properties carry the CI job: every discovered test lands in exactly one
shard (a missing test would show up as coverage that quietly fell off, not as a
red job), the split is the same on every runner (otherwise the three jobs of one
run disagree about who owns which module and a test can run twice or never), and
a shard that would run nothing raises (a green job that executed no test is the
worst failure this file can produce).
"""

from io import StringIO

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase

from MrMap.management.commands.list_test_shards import module_of, shard_labels


class _Case:
    """Stand-in for a discovered TestCase method."""

    def __init__(self, module, name="test_it"):
        self.__class__ = type(name, (), {"__module__": module})
        self._id = f"{module}.{self.__class__.__name__}.{name}"

    def id(self):
        return self._id


class ShardLabelsTest(SimpleTestCase):
    def test_every_module_appears_exactly_once(self):
        counts = {f"tests.django.registry.test_{i}": (i % 7) + 1 for i in range(40)}

        buckets = [shard_labels(counts, shard, 4) for shard in range(4)]

        self.assertEqual(sorted(m for bucket in buckets for m in bucket), sorted(counts))
        self.assertTrue(all(buckets), "an empty shard would be a green job that ran nothing")

    def test_the_split_is_the_same_on_every_runner(self):
        counts = {f"tests.django.test_{i}": (i * 37) % 11 + 1 for i in range(60)}

        first = [shard_labels(counts, shard, 3) for shard in range(3)]
        second = [shard_labels(counts, shard, 3) for shard in range(3)]

        self.assertEqual(first, second)

    def test_the_heaviest_module_runs_alone(self):
        # Longest-processing-time packing puts the fat module by itself, which is
        # what keeps one 900-test file from sitting on top of a shard that already
        # carries the rest of its weight.
        counts = {"tests.django.test_fat": 900} | {
            f"tests.django.test_small_{i}": 3 for i in range(10)
        }

        buckets = [shard_labels(counts, shard, 3) for shard in range(3)]

        fat = next(bucket for bucket in buckets if "tests.django.test_fat" in bucket)
        self.assertEqual(fat, ["tests.django.test_fat"])

    def test_the_buckets_carry_similar_numbers_of_tests(self):
        # Balance, not just partitioning: a shard that carries half the suite makes
        # the matrix as slow as running it in one piece, and this is the assertion
        # that catches packing by module count instead of by test count.
        counts = {f"tests.django.registry.test_{i}": (i % 23) + 1 for i in range(60)}

        buckets = [shard_labels(counts, shard, 3) for shard in range(3)]
        loads = [sum(counts[module] for module in bucket) for bucket in buckets]

        self.assertLessEqual(max(loads) - min(loads), sum(loads) // 10,
                             f"shards carry {loads}")

    def test_more_shards_than_modules_refuses(self):
        with self.assertRaises(CommandError) as caught:
            shard_labels({"tests.django.test_only": 3}, 2, 3)
        self.assertIn("green job that ran nothing", str(caught.exception))

    def test_bad_numbers_refuse(self):
        counts = {"tests.django.test_a": 1, "tests.django.test_b": 2}

        with self.assertRaises(CommandError):
            shard_labels(counts, 0, 0)
        with self.assertRaises(CommandError):
            shard_labels(counts, 3, 2)


class ModuleOfTest(SimpleTestCase):
    def test_uses_the_class_module(self):
        self.assertEqual(module_of(_Case("tests.django.accounts.test_groups")),
                         "tests.django.accounts.test_groups")


class CommandTest(SimpleTestCase):
    def test_one_shard_names_the_whole_suite(self):
        # The default of a single shard must be the whole suite, because that is
        # what every local `docker compose run django-tests` still does.
        out = StringIO()
        call_command("list_test_shards", of=1, shard=0, top="tests.django", stdout=out)

        labels = [line for line in out.getvalue().splitlines() if line.strip()]
        self.assertGreater(len(labels), 50)
        self.assertTrue(all(label.startswith("tests.django.") for label in labels))
