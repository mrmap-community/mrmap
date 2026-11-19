"""Static guard of audit finding R6 (#1414): ``DescribeFeatureType`` has
no reachable first-party call path.

The verdict and its evidence are
``docs/source/development/wfs-describe-batching-verdict.rst``: the
per-type fetch chain of ``FeatureType``
(:meth:`registry.models.service.FeatureType.fetch_describe_feature_type_document`,
:meth:`~registry.models.service.FeatureType.parse`,
:meth:`~registry.models.service.FeatureType.create_element_instances`) and the
KVP builder behind it
(:meth:`registry.ows_lib.wfs.wfs.WebFeatureServiceClient.describe_feature_type_request`)
exist, are unit-tested through
``tests/django/registry/models/tests_document.py`` and are reached by no
production flow. Registration, update, monitoring, harvest and preview ask
zero ``DescribeFeatureType`` requests, so batching would save zero requests
and #1414 recorded a no-batching verdict instead of implementing one.

This module is the call-path assertion the audit named as the missing
fixture: production code stays out of the chain. A module which appears in a
failure below has wired a new consumer onto the per-type describe fetch.
That is not forbidden forever, but it re-opens the premise this verdict rests
on: read the page above first - if the new consumer fetches for several
feature types of one service in one workflow, the batching requirements of
epic #1408 / issue #1414 (multi-typeName compatibility, namespace and import
mapping, partial-failure handling, no sharing across auth or version) become
live again and belong to that decision, not to a drive-by call.
"""
from pathlib import Path

from django.test import SimpleTestCase
from MrMap.settings import BASE_DIR

# Production modules the chain may name: the models module which defines the
# fetch chain (including the error text naming the method) and the ows_lib
# module which defines the request builder. Everything else referencing a
# symbol is a consumer.
FETCH_CHAIN_OWNERS = {"registry/models/service.py"}
REQUEST_BUILDER_OWNERS = {"registry/models/service.py",
                          "registry/ows_lib/wfs/wfs.py"}


def production_sources():
    """Yield ``(posix path, path)`` of every production module.

    The test tree would match this guard's own doc string, and migrations
    are data without call sites; both are not call paths and are skipped.
    """
    root = Path(BASE_DIR)
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        if relative.parts[0] == "tests" or "migrations" in relative.parts[:-1]:
            continue
        yield relative.as_posix(), path


class DescribeFeatureTypeCallPathTest(SimpleTestCase):
    """No production module may reach the per-type DescribeFeatureType fetch."""

    @staticmethod
    def _referencing(symbol, owners):
        """Production modules naming ``symbol`` beyond its owning modules."""
        found = {
            name
            for name, path in production_sources()
            if symbol in path.read_text(errors="ignore")
        }
        unexpected = found - owners
        if unexpected:
            raise AssertionError(
                f"{sorted(unexpected)} reference {symbol}; the DescribeFeatureType "
                f"fetch chain has no production consumer on today's code and #1414 "
                f"recorded its no-batching verdict on exactly that fact "
                f"(docs/source/development/wfs-describe-batching-verdict.rst). A "
                f"deliberate new consumer must be decided against that page and the "
                f"batching requirements of epic #1408 / issue #1414, then this "
                f"guard is extended with the consumer named.")
        return found

    def test_describe_fetch_has_no_production_consumer(self):
        """The fetch chain is referenced by its defining module alone."""
        for symbol in ("fetch_describe_feature_type_document",
                       "create_element_instances"):
            with self.subTest(symbol=symbol):
                found = self._referencing(symbol, FETCH_CHAIN_OWNERS)
                self.assertTrue(
                    found,
                    f"{symbol} is not referenced anywhere: the chain this guard "
                    f"protects seems to have been deleted, which the guard may "
                    f"not silently bless - update the verdict page in the same "
                    f"change")

    def test_describe_request_builder_is_used_by_the_dead_fetch_only(self):
        """No module sends a DescribeFeatureType request beside the chain."""
        found = self._referencing("describe_feature_type_request",
                                  REQUEST_BUILDER_OWNERS)
        self.assertTrue(
            found,
            "describe_feature_type_request is not referenced anywhere: the "
            "builder this guard protects seems to have been deleted - update "
            "the verdict page in the same change")
