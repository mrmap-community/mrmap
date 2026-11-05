"""The keyword list rule and the quality indicator it writes (issue #919).

A catalogue which publishes ten values in one `gmd:keyword` element ships poor
metadata: "Keyword value" is 1..*, so ten values are ten element occurrences.
The record is schema-valid, validator-clean and INSPIRE-conformant (#919
checked the sources) - which is exactly why the finding must be a quality
signal, reported through the indicator #600 built the read side of and which
had no writer at all.

The rule: `len(parts) > 1 and len(keyword) > KEYWORD_LIST_THRESHOLD` over the
parts a `[,;]` split leaves, with the threshold measured over the keyword
corpus before it was chosen (see the comment at the constant). The rule is
about granularity, never about text: a legitimate keyword may carry a comma
as an apposition or a decimal separator, a long single value stays unflagged,
and the keyword itself is never split, rejected or rewritten.

These tests pin the shapes the issue names as tests to expect: the single
value, the comma-joined list at, below and above the threshold, the German
apposition and decimal comma which must stay unflagged, the recomputation
which clears a flag whose offending keywords are gone, and the untouched
`is_broken` - a quality problem is not broken metadata.
"""

from django.db import connection
from django.test import TestCase
from django.utils import translation
from registry.models.metadata import (DatasetMetadataRecord, Keyword,
                                      MetadataContact)

# the reported shape: one gmd:keyword element of the GDI-BW record, ten named
# plans plus "other" - 347 characters of perfectly good, perfectly merged
# metadata
GDI_BW_LIST = ",".join([
    f"Flächennutzungsplan WN {place}" for place in (
        "Remshalden", "Welzheim", "Sulzbach an der Murr", "Murrhardt",
        "Alfdorf", "Plüderhausen", "Schorndorf", "Rudersberg", "Leutenbach",
        "Weissach im Tal")
] + ["other"])

# a legitimate keyword with one comma: a German apposition, and the longest
# comma keyword the threshold measurement found (50 characters)
APPOSITION = "Heimerziehung, in einer sonst. betreuten Wohnform"
DECIMAL_COMMA = "Horizontale Auflösung von 0,0625 Grad"


class KeywordListRuleTest(TestCase):
    """The rule shape, element by element - no record needed."""

    def publishes(self, keyword):
        return DatasetMetadataRecord.keyword_publishes_several_values(keyword)

    def test_a_single_value_is_not_a_list(self):
        for keyword in ("Niederschlag", "Wasserrahmenrichtlinie",
                        "a moderately long single value which carries no delimiter at all"):
            self.assertFalse(self.publishes(keyword), keyword)

    def test_the_reported_shape_is_a_list(self):
        self.assertGreater(len(GDI_BW_LIST), 340)
        self.assertTrue(self.publishes(GDI_BW_LIST))

    def test_the_rule_is_longer_than_the_threshold_not_longer_or_equal(self):
        # a keyword of exactly KEYWORD_LIST_THRESHOLD characters is still ok,
        # one character more crosses the measured line
        threshold = DatasetMetadataRecord.KEYWORD_LIST_THRESHOLD
        below = ("ab," + "x" * threshold)[:threshold]
        at = "a" * 90 + "," + "b" * 10
        self.assertEqual(len(below), threshold)
        self.assertEqual(len(at), threshold + 1)
        self.assertFalse(self.publishes(below))
        self.assertTrue(self.publishes(at))

    def test_a_short_apposition_and_a_decimal_comma_stay_unflagged(self):
        self.assertLessEqual(len(APPOSITION), 50)
        self.assertFalse(self.publishes(APPOSITION))
        self.assertFalse(self.publishes(DECIMAL_COMMA))

    def test_a_long_single_value_is_no_list_however_long(self):
        # the rule must not become a length rule in disguise: without a
        # delimiter there is no granularity problem, whatever the length
        self.assertFalse(self.publishes("Gitterpunkt " * 30))

    def test_a_semikolon_joins_a_list_as_much_as_a_comma(self):
        keyword = "; ".join([f"Flächennutzungsplan WN {place}" for place in (
            "Remshalden", "Welzheim", "Sulzbach an der Murr", "Murrhardt")])
        self.assertTrue(self.publishes(keyword))

    def test_delimiters_at_the_edge_deliver_no_part_and_no_list(self):
        single = "Aufgabenstellung" + "," * 40 + " " * 60
        self.assertFalse(self.publishes(single))

    def test_the_rule_judges_no_text_beyond_the_delimiter(self):
        # blank parts do not count as values, but no part is edited and the
        # blank rule of parse_keyword stays the only text judgement
        self.assertFalse(self.publishes(", , " + " " * 120))


class QualityIndicatorTest(TestCase):
    """What the findings answer and how the indicator field carries them."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.contact = MetadataContact.objects.create(name="quality@example.de")
        cls.dataset_contact = MetadataContact.objects.create(
            name="dataset@quality.example.de")

    def setUp(self):
        self.record = DatasetMetadataRecord.objects.create(
            title="Eine Rekord", metadata_contact=self.contact,
            dataset_contact=self.dataset_contact)

    def carry(self, *keywords):
        self.record.keywords.set(
            [Keyword.objects.get_or_create(keyword=k)[0] for k in keywords])

    def test_a_clean_record_answers_no_finding(self):
        self.carry("Niederschlag", DECIMAL_COMMA, APPOSITION)

        self.assertFalse(self.record.refresh_quality_indicators())
        self.record.refresh_from_db()
        self.assertEqual(self.record.insufficient_quality, "")

    def test_the_merged_list_is_flagged_with_its_named_reason(self):
        self.carry(GDI_BW_LIST, "Wind")

        self.assertTrue(self.record.refresh_quality_indicators())
        text = self.record.insufficient_quality

        self.assertIn("publishes 11 values in one gmd:keyword element", text)
        # the finding names the keyword it reports ...
        self.assertIn("Flächennutzungsplan WN Remshalden", text)
        # ... as an excerpt, because a keyword is as long as its catalogue
        # says (#894) and the field renders as a tooltip
        self.assertIn("…", text)
        self.assertNotIn(GDI_BW_LIST, text)

    def test_the_answer_is_translated_at_write_time(self):
        self.carry(GDI_BW_LIST)

        with translation.override("de"):
            self.assertTrue(self.record.refresh_quality_indicators())
            text = self.record.insufficient_quality

        self.assertIn("veröffentlicht 11 Werte in einem gmd:keyword-Element", text)
        # the keyword itself is machine data and is never translated away
        self.assertIn("Flächennutzungsplan WN Remshalden", text)

    def test_every_offending_element_names_its_own_finding(self):
        self.carry(GDI_BW_LIST,
                   ";".join(["Flächennutzungsplan WN " + "x" * 40] * 4))

        self.record.refresh_quality_indicators()

        self.assertEqual(
            len(self.record.insufficient_quality.splitlines()), 2,
            self.record.insufficient_quality)

    def test_the_flag_is_cleared_when_the_offending_keywords_disappear(self):
        self.carry(GDI_BW_LIST)
        self.assertTrue(self.record.refresh_quality_indicators())
        self.record.save(mark_customized=False)
        self.record.refresh_from_db()
        self.assertNotEqual(self.record.insufficient_quality, "")

        self.carry("Flächennutzungsplan WN Remshalden",
                   "Flächennutzungsplan WN Welzheim")

        self.assertTrue(self.record.refresh_quality_indicators())
        self.assertEqual(self.record.insufficient_quality, "")

    def test_refreshing_an_answered_record_changes_nothing(self):
        self.carry(GDI_BW_LIST)
        self.record.refresh_quality_indicators()
        self.record.save(mark_customized=False)
        self.record.refresh_from_db()

        self.assertFalse(self.record.refresh_quality_indicators())
        self.record.refresh_from_db()
        self.assertNotEqual(self.record.insufficient_quality, "")

    def test_the_indicator_touches_neither_the_keywords_nor_is_broken(self):
        self.carry(GDI_BW_LIST)

        self.record.refresh_quality_indicators()
        self.record.save(mark_customized=False)

        self.record.refresh_from_db()
        self.assertFalse(self.record.is_broken)
        self.assertFalse(self.record.is_customized)
        self.assertEqual(
            [k.keyword for k in self.record.keywords.all()], [GDI_BW_LIST],
            "the rule reports, it never splits or rewrites the keyword")

    def test_the_mapped_keywords_are_judged_without_touching_the_database(self):
        # the import hands the already mapped keywords in; the hot path of a
        # 96,000 record run must not pay a query per record for the rule
        record = DatasetMetadataRecord(title="not saved",
                                       metadata_contact=self.contact,
                                       dataset_contact=self.dataset_contact)

        with self.assertNumQueries(0):
            record.refresh_quality_indicators([GDI_BW_LIST])

        self.assertNotEqual(record.insufficient_quality, "")

    def test_the_written_text_survives_a_republish_of_the_same_keywords(self):
        # the read side of #600 filters on the text, so the written value is
        # what the filter and the chips answer - pin it on the column
        self.carry(GDI_BW_LIST)
        self.record.refresh_quality_indicators()
        self.record.save(mark_customized=False)

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT insufficient_quality FROM registry_datasetmetadatarecord "
                "WHERE id = %s", [self.record.pk])
            stored = cursor.fetchone()[0]

        self.assertIn("publishes 11 values", stored)
