"""Property-based drift guard for the #981 refactor (issue acceptance).

`pre_981_mapped_values.json` in `tests/django/test_data/iso_metadata/` holds
the mapped values of every ISO fixture in that directory - plus
`wms-service-metadata.xml` - captured with the mapper code BEFORE the #981
extraction refactor: every field value the old traversal produced, normalized
with the same rules this module applies. For every fixture this test maps the
document with the current code and demands:

* the record set is the same: same number of records, same spec, same model,
* every field value that existed before is dict-equal now - existing
  harvesting behavior is unchanged by the refactor,
* the new keys (`_values` access and coupling specs of #981) may only be
  added, never replace or shadow an existing one,
* a fixture the old mapper rejected still fails with the same clean error.
"""

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from uuid import UUID

from django.test import TestCase
from registry.mappers.factory import MDMetadataXmlMapper

ISO_DIR = Path(__file__).parent / '../../test_data/iso_metadata'
GOLDEN = ISO_DIR / 'pre_981_mapped_values.json'

FIXTURES = ("dataset.xml", "gdi-bw-01.xml", "gdi-bw-02.xml", "gdi-bw-04.xml",
            "gdi-de-01.xml", "gdi-de-03.xml", "gdi-de-04.xml",
            "gdi-de-05.xml", "geocat-01.xml", "hessen-01.xml",
            "hessen-03.xml", "service.xml", "../wms-service-metadata.xml")


def jsonable(value):
    """Normalize one mapped value for the golden comparison.

    The same function the pre-refactor capture ran, so both sides of the
    comparison normalize identically: containers recurse, enums answer their
    member name, datetimes their ISO string, geometries their WKT and SRID.
    Django's Choices members are ints and stay plain ints - the value the
    database will hold.
    """
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, bytes):
        return {"__bytes__": value.decode("utf-8", "replace")}
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        if isinstance(value, set):
            items.sort(key=str)
        return [jsonable(v) for v in items]
    if getattr(type(value), "_member_map_", None) is not None:
        return {"__enum__": f"{type(value).__name__}.{value.name}"}
    if isinstance(value, (datetime, date, time)):
        return {"__iso__": value.isoformat()}
    if isinstance(value, timedelta):
        return {"__duration__": str(value)}
    if isinstance(value, UUID):
        return {"__uuid__": str(value)}
    if hasattr(value, "wkt") and hasattr(value, "srid"):
        return {"__geom__": {"wkt": value.wkt, "srid": value.srid}}
    return {"__repr__": repr(value)}


class MappedValuesDriftGuardTest(TestCase):
    maxDiff = None

    @classmethod
    def setUpTestData(cls):
        cls.golden = json.loads(GOLDEN.read_text())

    def extract_normalized(self, fixture):
        records = MDMetadataXmlMapper.extract_mapped_values(
            fixture.read_bytes())
        return [{
            "spec": record["spec"],
            "model": record["model"].split(".")[-1],
            "values": jsonable(record["values"]),
        } for record in records]

    def test_every_fixture_still_maps_to_the_pre_refactor_values(self):
        for name in FIXTURES:
            fixture = (ISO_DIR / name).resolve()
            with self.subTest(fixture=fixture.name):
                expected = self.golden[fixture.name]
                if isinstance(expected, dict) and "error" in expected:
                    with self.assertRaises(Exception) as caught:
                        self.extract_normalized(fixture)
                    self.assertEqual(
                        f"{type(caught.exception).__name__}: "
                        f"{caught.exception}",
                        expected["error"])
                    continue
                mapped = self.extract_normalized(fixture)
                self.assertEqual(len(mapped), len(expected))
                for before, after in zip(expected, mapped):
                    self.assertEqual(after["spec"], before["spec"])
                    self.assertEqual(after["model"], before["model"])
                    # every field that existed before is unchanged, and the
                    # refactor may only add the new _values keys on top
                    self.assertTrue(
                        set(before["values"]) <= set(after["values"]),
                        f"fields lost: "
                        f"{set(before['values']) - set(after['values'])}")
                    unchanged = {
                        key: after["values"][key]
                        for key in before["values"]
                    }
                    self.assertEqual(unchanged, before["values"])

    def test_the_access_and_coupling_keys_are_the_only_addition(self):
        """No key of a pre-refactor mapped record was renamed or dropped; the
        only new keys are the documented #981 access and coupling specs."""
        new_keys = {"online_links", "distributor_online_links", "operations",
                    "operates_on", "coupled_resources"}
        for name in FIXTURES:
            fixture = (ISO_DIR / name).resolve()
            expected = self.golden[fixture.name]
            if isinstance(expected, dict) and "error" in expected:
                continue
            with self.subTest(fixture=fixture.name):
                mapped = self.extract_normalized(fixture)
                for before, after in zip(expected, mapped):
                    added = set(after["values"]) - set(before["values"])
                    self.assertTrue(
                        added <= new_keys,
                        f"unexpected new keys: {added - new_keys}")
