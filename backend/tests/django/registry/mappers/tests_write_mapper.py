"""The write mapper of issue #1242: mapped values written back into the document.

`XmlMapper.write_mapped_values()` is the inverse of `mapped_values()` and
`MDMetadataXmlMapper.write_mapped_records()` the inverse of
`extract_mapped_values()`: they take the values shape the extraction answers
and write it into the ISO 19139 document the values came from. This module is
that contract, over the real fixtures:

* write-back of what was just extracted is semantically neutral - c14n equal,
  because re-serialization normalizes self-closing tags - and a second save
  of the same values is byte-stable, so repeated editor saves converge;
* an existing mapped element has its text or attribute replaced and nothing
  else moves: against the lxml-normalized baseline only the written line
  differs;
* a missing mapped element is created at the position the schema order table
  names and carries the document's own namespace prefixes; the predicates of
  its config path are seeded, which is how access_constraints materializes
  its otherRestrictions restriction code;
* content no mapped field names is preserved byte for byte;
* multi-valued fields pair values with rows by position, create missing rows
  at the spec's `_reverse._row` and remove surplus rows - but only while the
  field carries values at all: an empty list or None never removes content;
* fields whose config has no reverse mapping are skipped and named in the
  warnings; a record that does not fit the document raises.
"""

import difflib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from django.contrib.gis.geos import MultiPolygon, Polygon
from django.test import TestCase
from lxml import etree
from registry.enums.iso import LanguageChoices
from registry.mappers.factory import MDMetadataXmlMapper

ISO_DATA = Path(__file__).parent / '../../test_data/iso_metadata'
GMD = "http://www.isotc211.org/2005/gmd"


def c14n(xml: bytes) -> bytes:
    """Canonical form: equality of what the document says, not its bytes."""
    return etree.tostring(etree.fromstring(xml), method="c14n")


def normalize(xml: bytes) -> bytes:
    """The lxml round trip of the unchanged document - the byte baseline."""
    return etree.tostring(
        etree.fromstring(xml), xml_declaration=True, encoding="utf-8")


def local(el) -> str:
    return etree.QName(el).localname


class WriteMapperTest(TestCase):
    """Shared entry points over the record fixtures."""

    FIXTURES = ("dataset.xml", "gdi-bw-01.xml", "gdi-bw-02.xml",
                "gdi-bw-04.xml", "gdi-de-01.xml", "gdi-de-03.xml",
                "gdi-de-04.xml", "gdi-de-05.xml", "hessen-01.xml",
                "hessen-03.xml", "service.xml")

    def read(self, name):
        return (ISO_DATA / name).read_bytes()

    def extract(self, xml: bytes):
        return MDMetadataXmlMapper.extract_mapped_values(xml)

    def write(self, xml: bytes, records):
        return MDMetadataXmlMapper.write_mapped_records(xml, records)

    def round_trip(self, name, mutate=None):
        """read -> (mutate) -> write -> re-extract, with every intermediate."""
        raw = self.read(name)
        records = self.extract(raw)
        if mutate:
            for record in records:
                mutate(record["values"])
        out, warnings = self.write(raw, records)
        return raw, records, out, warnings, self.extract(out)


class RoundTripTest(WriteMapperTest):
    """Writing back what the document itself says changes nothing."""

    def test_write_back_of_extracted_values_is_semantically_neutral(self):
        for name in self.FIXTURES:
            with self.subTest(fixture=name):
                raw = self.read(name)
                out, warnings = self.write(raw, self.extract(raw))
                self.assertEqual(c14n(raw), c14n(out))

    def test_repeated_save_is_byte_stable(self):
        raw, records, out, _, reread = self.round_trip("gdi-de-01.xml")
        out2, _ = self.write(out, reread)
        self.assertEqual(out, out2)

    def test_repeated_save_after_a_change_is_byte_stable(self):
        def mutate(values):
            values["title"] = "Ein neuer Titel"
            values["keywords"] = [{"keyword": "eins"}, {"keyword": "zwei"}]

        raw, records, out, _, reread = self.round_trip(
            "gdi-de-01.xml", mutate)
        out2, _ = self.write(out, reread)
        self.assertEqual(out, out2)
        # and the changed values survived both saves
        self.assertEqual(reread[0]["values"]["title"], "Ein neuer Titel")
        self.assertEqual(
            [k["keyword"] for k in reread[0]["values"]["keywords"]],
            ["eins", "zwei"])

    def test_extraction_after_the_write_answers_the_same_values(self):
        for name in ("gdi-de-01.xml", "gdi-bw-04.xml", "service.xml",
                     "hessen-01.xml", "dataset.xml"):
            with self.subTest(fixture=name):
                _, records, _, _, reread = self.round_trip(name)
                self.assertEqual(len(records), len(reread))
                for before, after in zip(records, reread):
                    self.assertEqual(before["spec"], after["spec"])
                    self.assertEqual(before["model"], after["model"])
                    self.assertEqual(before["values"], after["values"])


class ChangedContentTest(WriteMapperTest):
    """What a write is allowed to touch."""

    def test_only_the_written_line_changes(self):
        raw = self.read("gdi-de-01.xml")
        baseline = normalize(raw).splitlines()
        records = self.extract(raw)
        records[0]["values"]["title"] = "Nur diese Zeile"
        out, _ = self.write(raw, records)
        changed = out.splitlines()
        diffs = [
            (j1, j2)
            for tag, _, _, j1, j2 in
            difflib.SequenceMatcher(None, baseline, changed).get_opcodes()
            if tag != "equal"
        ]
        self.assertEqual(len(diffs), 1, "more than one region of the "
                                        "document moved")
        block = b"\n".join(changed[diffs[0][0]:diffs[0][1]])
        self.assertIn("Nur diese Zeile".encode("utf-8"), block)

    def test_unmapped_sections_are_preserved_byte_for_byte(self):
        raw = self.read("gdi-de-01.xml")

        def mutate(values):
            values["keywords"] = [{"keyword": "neu"}]
            values["abstract"] = "Kurzer neuer Text"

        _, _, out, _, _ = self.round_trip("gdi-de-01.xml", mutate)
        for tag in ("distributionInfo", "dataQualityInfo"):
            before = etree.fromstring(raw).xpath(
                f"//*[local-name()='{tag}']")
            after = etree.fromstring(out).xpath(
                f"//*[local-name()='{tag}']")
            self.assertEqual([etree.tostring(e) for e in before],
                             [etree.tostring(e) for e in after],
                             f"{tag} was touched")

    def test_existing_text_is_replaced_not_the_element_rebuilt(self):
        # the written file_identifier keeps the element - and everything the
        # element carried besides its text
        raw = self.read("gdi-de-01.xml")
        records = self.extract(raw)
        records[0]["values"]["file_identifier"] = "neue.kennung"
        out, _ = self.write(raw, records)
        nodes = etree.fromstring(out).xpath(
            "//*[local-name()='fileIdentifier']/*[local-name()="
            "'CharacterString']")
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0].text, "neue.kennung")

    def test_charset_is_written_to_the_codelist_value_attribute(self):
        def mutate(values):
            values["charset"] = 2  # ucs2

        _, _, out, _, reread = self.round_trip("gdi-de-01.xml", mutate)
        nodes = etree.fromstring(out).xpath(
            "//*[local-name()='MD_CharacterSetCode']")
        self.assertTrue(nodes)
        self.assertEqual(nodes[0].get("codeListValue"), "ucs2")
        self.assertEqual(reread[0]["values"]["charset"], 2)


class CreationTest(WriteMapperTest):
    """Missing mapped elements come back at the schema correct position."""

    def test_created_element_uses_the_documents_own_prefixes(self):
        def mutate(values):
            values["update_frequency_code"] = 4  # weekly

        _, _, out, _, reread = self.round_trip("gdi-de-01.xml", mutate)
        created = etree.fromstring(out).xpath(
            "//*[local-name()='MD_MaintenanceInformation']")
        self.assertEqual(len(created), 1)
        self.assertTrue(etree.tostring(created[0]).startswith(
            b"<ns0:MD_MaintenanceInformation"),
            "lxml must reuse the ns0 prefix of the document")
        self.assertEqual(created[0].xpath(
            ".//*[local-name()='MD_MaintenanceFrequencyCode']/@codeListValue"
        ), ["weekly"])
        self.assertEqual(reread[0]["values"]["update_frequency_code"], 4)

    def test_created_element_lands_at_the_schema_position(self):
        def mutate(values):
            values["update_frequency_code"] = 4

        _, _, out, _, _ = self.round_trip("gdi-de-01.xml", mutate)
        identification = etree.fromstring(out).xpath(
            "//*[local-name()='MD_DataIdentification']")[0]
        kids = [local(k) for k in identification]
        index = kids.index("resourceMaintenance")
        # the ISO sequence puts resourceMaintenance after the responsible
        # parties and before the overview graphics - which is exactly where
        # the element order table says it goes
        self.assertGreater(index, kids.index("pointOfContact"))
        self.assertLess(index, kids.index("graphicOverview"))

    def test_access_constraints_seeds_its_restriction_code(self):
        raw = self.read("gdi-de-04.xml")
        records = self.extract(raw)
        # A missing text node keeps the non-null model field's empty default.
        self.assertEqual(records[0]["values"]["access_constraints"], "")
        records[0]["values"]["access_constraints"] = "Zugang beschränkt"
        out, _ = self.write(raw, records)

        # count() instead of a second filter predicate: the chained
        # "[...][@a='v']" form raises "Invalid type" on this document with
        # libxml2 2.14 (#1242 CI), count() evaluates everywhere identically
        created = etree.fromstring(out).xpath(
            "//*[local-name()='MD_LegalConstraints']"
            "[count(.//*[local-name()='MD_RestrictionCode']"
            "[@codeListValue='otherRestrictions'])>0]"
            "[count(.//*[local-name()='otherConstraints'])>0]")
        self.assertEqual(len(created), 1)
        self.assertTrue(etree.tostring(created[0]).startswith(
            b"<ns0:MD_LegalConstraints"))
        self.assertEqual(self.extract(out)[0]["values"]["access_constraints"],
                         "Zugang beschränkt")


class CollectionTest(WriteMapperTest):
    """Rows of a mapped collection pair with the rows the reader answered."""

    def test_keyword_rows_are_written_positionally_and_surplus_removed(self):
        def mutate(values):
            values["keywords"] = [{"keyword": "eins"}, {"keyword": "zwei"}]

        raw, records, out, _, reread = self.round_trip(
            "gdi-de-01.xml", mutate)
        keywords = reread[0]["values"]["keywords"]
        self.assertEqual(
            [k["keyword"] for k in keywords], ["eins", "zwei"])
        # the surplus rows are gone as whole gmd:keyword rows, not as texts
        texts = [
            el.text for el in etree.fromstring(out).xpath(
                "//*[local-name()='MD_Keywords']"
                "/*[local-name()='keyword']/*[local-name()='CharacterString']")
        ]
        self.assertEqual(sorted(t.strip() for t in texts),
                         ["eins", "zwei"])
        # and the values the rows did not survive - the thesauri - stay
        self.assertEqual(
            len(etree.fromstring(raw).xpath(
                "//*[local-name()='thesaurusName']")),
            len(etree.fromstring(out).xpath(
                "//*[local-name()='thesaurusName']")))

    def test_empty_list_never_removes_rows(self):
        def mutate(values):
            values["keywords"] = []

        raw, _, out, _, _ = self.round_trip("gdi-de-01.xml", mutate)
        self.assertEqual(c14n(raw), c14n(out))

    def test_added_keyword_row_lands_beside_the_existing_rows(self):
        raw = self.read("gdi-de-01.xml")
        records = self.extract(raw)
        before = len(records[0]["values"]["keywords"])
        records[0]["values"]["keywords"].append({"keyword": "ganz neu"})
        out, _ = self.write(raw, records)
        reread = self.extract(out)[0]["values"]["keywords"]
        self.assertEqual(len(reread), before + 1)
        self.assertEqual(reread[-1]["keyword"], "ganz neu")

    def test_added_language_row_carries_the_code_list_attribute(self):
        raw = self.read("gdi-de-01.xml")
        records = self.extract(raw)
        existing = [row["value"] for row in records[0]["values"]["languages"]]
        other = next(
            member.value for member in LanguageChoices
            if member.value not in existing)
        records[0]["values"]["languages"].append({"value": other})
        out, _ = self.write(raw, records)
        reread = self.extract(out)[0]["values"]["languages"]
        self.assertEqual([row["value"] for row in reread], existing + [other])
        # the created wrapper satisfies the predicate the config reads with
        codes = etree.fromstring(out).xpath(
            "//*[local-name()='LanguageCode'"
            " and @codeListValue='" + str(LanguageChoices(other).label) + "']")
        self.assertTrue(codes)
        self.assertTrue(all(
            c.get("codeList") ==
            "http://www.loc.gov/standards/iso639-2/" for c in codes))

    def test_rows_the_parser_skipped_do_not_shift_the_pairing(self):
        # gdi-bw-04 carries keyword placeholders with gco:nilReason="missing"
        # which the reader drops; writing its values back must land them on
        # the same rows and leave the placeholders alone
        raw = self.read("gdi-bw-04.xml")
        out, _ = self.write(raw, self.extract(raw))
        self.assertEqual(c14n(raw), c14n(out))
        self.assertTrue(etree.fromstring(out).xpath(
            "//*[@*[local-name()='nilReason']]"))

    def test_contact_is_written_to_the_element_the_reader_answered(self):
        # gdi-de-05 names several pointOfContact parties; the FK field is
        # answered from the last one, so the write belongs to that one
        raw = self.read("gdi-de-05.xml")
        records = self.extract(raw)
        first_before = etree.fromstring(raw).xpath(
            "//*[local-name()='pointOfContact']//*[local-name()"
            "='organisationName']//*[local-name()='CharacterString']")[0].text
        contact = dict(records[0]["values"]["application_contact"])
        contact["name"] = "Neue Stelle"
        records[0]["values"]["application_contact"] = contact
        out, _ = self.write(raw, records)
        parties = etree.fromstring(out).xpath(
            "//*[local-name()='pointOfContact']//*[local-name()"
            "='organisationName']//*[local-name()='CharacterString']")
        self.assertEqual(parties[0].text, first_before)
        self.assertEqual(parties[-1].text, "Neue Stelle")
        self.assertEqual(
            self.extract(out)[0]["values"]["application_contact"]["name"],
            "Neue Stelle")


class RefusalTest(WriteMapperTest):
    """What the write mapper must leave alone and must refuse."""

    def test_none_values_never_remove_content(self):
        def mutate(values):
            values["title"] = None
            values["abstract"] = ""
            values["keywords"] = None

        raw, _, out, _, _ = self.round_trip("gdi-de-01.xml", mutate)
        self.assertEqual(c14n(raw), c14n(out))

    def test_fields_without_reverse_mapping_warn_and_are_skipped(self):
        raw = self.read("gdi-de-01.xml")
        records = self.extract(raw)
        values = records[0]["values"]
        values["code"] = "anderer-code"
        values["code_space"] = "anderer/raum/"
        out, warnings = self.write(raw, records)
        self.assertEqual(c14n(raw), c14n(out))
        self.assertTrue(any("code" in w for w in warnings), warnings)
        # bounding_geometry and time_extents got their _reverse_parser with
        # #1246: writing back what the extraction answered is neutral, not a
        # warning - the extent tests below assert their real behaviour
        self.assertFalse(
            any("bounding_geometry" in w for w in warnings), warnings)

    def test_record_count_mismatch_raises(self):
        raw = self.read("gdi-de-01.xml")
        records = self.extract(raw)
        with self.assertRaises(ValueError):
            self.write(raw, records + records)
        with self.assertRaises(ValueError):
            self.write(raw, [])

    def test_record_of_another_kind_raises(self):
        raw = self.read("gdi-de-01.xml")
        records = self.extract(raw)
        records[0]["spec"] = "service"
        with self.assertRaises(ValueError):
            self.write(raw, records)


class ExtentWriteTest(WriteMapperTest):
    """The extent fragments of #1246: geometry and time rows written back.

    The config's `_reverse_parser` for `bounding_geometry` answers an
    EX_GeographicBoundingBox or EX_BoundingPolygon fragment and the one for
    `time_extents` a gml:TimePeriod fragment; the write mapper places them
    like #1242's rule for the flat paths (replace the first match) and for
    the collection rows (replace the row element's fragment child, create a
    row at `_reverse._row`). These tests mutate the extracted values and
    read the answer back through the same mapper.
    """

    def mutate(self, name, changes):
        """read -> extract -> apply `changes` to the record values -> write."""
        raw = self.read(name)
        records = self.extract(raw)
        changes(records[0]["values"])
        out, warnings = self.write(raw, records)
        return raw, records, out, warnings, self.extract(out)

    def assert_extent_writable(self, warnings):
        self.assertFalse(
            [w for w in warnings
             if "bounding_geometry" in w or "time_extents" in w], warnings)

    def test_bounding_box_change_writes_a_bounding_box(self):
        # the ring in the order :func:`_parse_geographic_bbox` reads it back
        rect = Polygon([(2.0, 48.0), (2.0, 49.0), (3.0, 49.0), (3.0, 48.0),
                        (2.0, 48.0)])

        def change(values):
            values["bounding_geometry"] = MultiPolygon([rect])

        _, _, out, warnings, reread = self.mutate("dataset.xml", change)
        self.assert_extent_writable(warnings)
        self.assertEqual(reread[0]["values"]["bounding_geometry"],
                         MultiPolygon([rect], srid=4326))
        self.assertIn(b"EX_GeographicBoundingBox", out)
        # the written rectangle reads back as the very geometry: a second
        # save of the re-read values is byte-stable
        out2, _ = self.write(out, reread)
        self.assertEqual(out, out2)

    def test_non_rectangular_geometry_replaces_the_box_with_a_polygon(self):
        triangle = Polygon([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 0.0)])

        def change(values):
            values["bounding_geometry"] = MultiPolygon([triangle])

        _, _, out, warnings, reread = self.mutate("dataset.xml", change)
        self.assert_extent_writable(warnings)
        self.assertIn(b"EX_BoundingPolygon", out)
        self.assertNotIn(b"EX_GeographicBoundingBox", out)
        # GML reads polygons in the clockwise convention, the value came in
        # counter-clockwise: the answer back is the same geometry, not the
        # same vertex order - the topological equality is what round trips
        self.assertTrue(reread[0]["values"]["bounding_geometry"].equals(
            MultiPolygon([triangle], srid=4326)))
        out2, _ = self.write(out, reread)
        self.assertEqual(out, out2)

    def test_writing_back_a_polygon_document_is_semantically_neutral(self):
        # after one write put the geometry into the EX_BoundingPolygon shape,
        # re-extracting and writing the result again finds the polygon equal
        # through the spec's _parser - the document bytes of the second save
        # do not move any more than those of an unchanged bounding box
        triangle = Polygon([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 0.0)])

        def change(values):
            values["bounding_geometry"] = MultiPolygon([triangle])

        _, _, out, _, reread = self.mutate("dataset.xml", change)
        out2, warnings = self.write(out, reread)
        self.assert_extent_writable(warnings)
        self.assertEqual(c14n(out), c14n(out2))
        self.assertIn(b"EX_BoundingPolygon", out2)

    def test_geometry_created_in_a_seed_document_without_one(self):
        from registry.mappers.publish import seed_document

        seed = seed_document("dataset")
        records = self.extract(seed)
        self.assertIsNone(records[0]["values"]["bounding_geometry"])
        rect = Polygon([(7.0, 50.0), (7.0, 51.0), (8.0, 51.0), (8.0, 50.0),
                        (7.0, 50.0)])
        records[0]["values"]["bounding_geometry"] = MultiPolygon([rect])
        out, warnings = self.write(seed, records)
        self.assert_extent_writable(warnings)
        self.assertIn(b"EX_GeographicBoundingBox", out)
        self.assertEqual(self.extract(out)[0]["values"]["bounding_geometry"],
                         MultiPolygon([rect], srid=4326))

    def test_time_row_change_updates_the_positions_and_keeps_the_row(self):
        def change(values):
            values["time_extents"][0]["end"] = datetime(
                2021, 6, 30, 12, 0, 0, tzinfo=UTC)

        _, _, out, warnings, reread = self.mutate("hessen-01.xml", change)
        self.assert_extent_writable(warnings)
        row = reread[0]["values"]["time_extents"][0]
        self.assertEqual(row["end"], datetime(2021, 6, 30, 12, 0, 0,
                                              tzinfo=UTC))
        self.assertIn(b"2021-06-30T12:00:00", out)
        # still exactly one temporal row element in the document
        self.assertEqual(
            out.count(b"<gmd:EX_TemporalExtent>"),
            self.read("hessen-01.xml").count(b"<gmd:EX_TemporalExtent>"))
        out2, _ = self.write(out, reread)
        self.assertEqual(out, out2)

    def test_new_time_row_is_created_beside_the_existing_ones(self):
        begin = datetime(2022, 1, 1, tzinfo=UTC)
        end = datetime(2022, 12, 31, tzinfo=UTC)

        def change(values):
            values["time_extents"].append(
                {"begin": begin, "end": end,
                 "resolution": timedelta(0), "is_relative": False})

        _, _, out, warnings, reread = self.mutate("hessen-01.xml", change)
        self.assert_extent_writable(warnings)
        rows = reread[0]["values"]["time_extents"]
        self.assertEqual(len(rows), 2)
        self.assertIn({"begin": begin, "end": end},
                      [{"begin": r["begin"], "end": r["end"]} for r in rows])
        out2, _ = self.write(out, reread)
        self.assertEqual(out, out2)

    def test_writing_a_rolling_row_back_leaves_it_untouched(self):
        # a row without positions is a rolling window - GML shapes with
        # indeterminate positions which the reverse parser answers None for:
        # the write leaves whatever the document carries for that row alone
        # instead of guessing a shape
        raw = self.read("dataset.xml")
        records = self.extract(raw)
        row = records[0]["values"]["time_extents"][0]
        row["begin"] = None
        row["end"] = None
        row["is_relative"] = True
        row["resolution"] = timedelta(days=3)
        out, warnings = self.write(raw, records)
        self.assert_extent_writable(warnings)
        self.assertIn(b"indeterminatePosition", out)
        self.assertEqual(c14n(raw), c14n(out))
