"""The keyword list rule as the import writes it (issue #919).

`md_metadata_file_to_db` is the one place every harvested record of every
record type is finalized, and #600's quality indicator had no writer at all.
This module follows the first writer through the real import - the harness of
#858, nothing mocked, the documents of the real-metadata corpus - and pins
what the issue asks the writer to guarantee:

* a merged keyword list flags the new record inside the one write the record
  already costs (#858): the rule runs on the keywords the document just
  mapped, no second XML parse, no second write,
* the flag survives a run which changes nothing, it is cleared by a
  re-harvest of a corrected remote, and it arrives on a record which entered
  the registry before the rule existed - its next re-harvest flags it even
  though the run changes nothing else,
* the keyword itself is stored exactly as the catalogue published it: one
  row, the whole string, never split, never rewritten - and the record is
  republished with it as the one keyword element it is,
* a clean record is never written by the rule and a run which finds nothing
  logs nothing, so the indicator stays a signal and the harvest log does not
  become a wall.

The rule reaches all three record types because all three are finalized in
this one place: the dataset sample, the service sample and an application
sample of the mapper corpus are imported here.
"""

from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase
from lxml import etree
from registry.enums.harvesting import CollectingStatenEnum as State
from registry.models.metadata import (ApplicationMetadataRecord,
                                      DatasetMetadataRecord, Keyword,
                                      ServiceMetadataRecord)
from rest_framework.test import APIClient
from tests.django.registry.mappers.tests_import_writes_each_record_once import \
    ImportHarness

ISO_DATA = Path(__file__).parent / '../../test_data/iso_metadata'

# one sampled document per record type, like the provenance tests import them
SAMPLES = {
    "dataset": ("dataset.xml", DatasetMetadataRecord),
    "service": ("service.xml", ServiceMetadataRecord),
    "application": ("gdi-bw-01.xml", ApplicationMetadataRecord),
}

PLACES = ("Remshalden", "Welzheim", "Sulzbach an der Murr", "Murrhardt",
          "Alfdorf", "Plüderhausen", "Schorndorf", "Rudersberg", "Leutenbach",
          "Weissach im Tal")
GDI_BW_LIST = ",".join([f"Flächennutzungsplan WN {place}" for place in PLACES]
                       + ["other"])

# the legitimate comma: a German apposition below the measured threshold
APPOSITION = "Heimerziehung, in einer sonst. betreuten Wohnform"

DATE = "2021-01-01T00:00:00"


def keyword_document(sample, file_identifier, values, date_stamp=DATE):
    """A copy of a sampled document which publishes `values` as its keywords.

    One element of `values` becomes one gmd:keyword element - so the merged
    list of the reported catalogue is one value which happens to carry eleven
    comma separated parts, while the corrected remote passes the eleven parts
    as eleven values. Everything else the document carried is kept.
    """
    tree = etree.parse(ISO_DATA / sample)
    root = tree.getroot()

    identifier = root.xpath("//*[local-name()='fileIdentifier']"
                            "//*[local-name()='CharacterString']")[0]
    identifier.text = file_identifier
    stamp = root.xpath("//*[local-name()='dateStamp']"
                       "/*[local-name()='DateTime' or local-name()='Date']")[0]
    stamp.text = date_stamp

    # every record config maps from its identification section, dataset and
    # application from gmd:MD_DataIdentification, service from
    # srv:SV_ServiceIdentification - attach below whichever one the document
    # carries. The gmd namespace is taken from the document's own
    # identificationInfo (documents disagree on its version URI), the gco one
    # from a CharacterString it already carries.
    gmd = root.xpath("//*[local-name()='identificationInfo']")[0] \
        .tag.split("}")[0].lstrip("{")
    gco = root.xpath("//*[local-name()='CharacterString']")[0] \
        .tag.split("}")[0].lstrip("{")
    identification = root.xpath(
        "//*[local-name()='SV_ServiceIdentification' "
        "or local-name()='MD_DataIdentification']")[0]
    block = etree.SubElement(identification, f"{{{gmd}}}descriptiveKeywords")
    keywords = etree.SubElement(block, f"{{{gmd}}}MD_Keywords")
    for value in values:
        keyword = etree.SubElement(keywords, f"{{{gmd}}}keyword")
        text = etree.SubElement(keyword, f"{{{gco}}}CharacterString")
        text.text = value
    return etree.tostring(tree, encoding="utf-8")


class KeywordListImportTest(ImportHarness, TestCase):
    """The writer in the import, on the dataset sample."""

    def setUp(self):
        super().setUp()
        self.document = keyword_document("dataset.xml", "de.919.keywordlist",
                                         [GDI_BW_LIST, APPOSITION])
        self.run = self.new_run()

    def record(self):
        return DatasetMetadataRecord.objects.get()

    def quality_logs(self, job):
        return job.logs.filter(description__startswith="Keyword quality:")

    def quality_log_text(self, log):
        # the extended description of a harvesting log is stored as a file
        with log.extented_description.open("rb") as stored:
            return stored.read().decode("utf-8")

    def test_a_merged_keyword_flags_the_record_inside_its_one_write(self):
        """one INSERT of the record and one of its history row - the answer of
        the rule rides that write instead of asking for a second one (#858)"""
        self.assertWrites(
            lambda: self.import_document(self.run),
            **{self.record_table: 1, self.history_table: 1})

        record = self.record()
        self.assertIn("publishes 11 values in one gmd:keyword element",
                      record.insufficient_quality)
        self.assertIn("Flächennutzungsplan WN Remshalden",
                      record.insufficient_quality)
        self.assertFalse(record.is_broken)

    def test_the_keyword_is_stored_exactly_as_the_catalogue_published_it(self):
        self.import_document(self.run)

        record = self.record()
        self.assertIn(GDI_BW_LIST, [k.keyword for k in record.keywords.all()])
        self.assertEqual(
            Keyword.objects.filter(keyword="Flächennutzungsplan WN Rudersberg")
            .count(), 0,
            "the rule reports, it never splits the list into new identities")
        self.assertIn(GDI_BW_LIST, record.keywords_list,
                      "the denormalized list keeps the whole element too")

    def test_the_legitimate_apposition_is_not_part_of_the_reason(self):
        self.import_document(self.run)

        self.assertNotIn(APPOSITION, self.record().insufficient_quality)

    def test_a_reharvest_which_changes_nothing_keeps_the_flag_and_writes_nothing(self):
        self.import_document(self.run)

        run = self.new_run()
        self.assertWrites(lambda: self.import_document(run))

        self.assertIn("publishes 11 values",
                      self.record().insufficient_quality)
        self.assertEqual(
            self.record().harvested_dataset_metadata_relations.latest('id')
            .collecting_state, State.EXISTING)
        self.assertEqual(self.quality_logs(run).count(), 0,
                         "a flag which was written before this run says "
                         "nothing new to the log")

    def test_a_reharvest_of_a_corrected_remote_clears_the_flag(self):
        """the catalogue fixed its record: one element per value from now on"""
        self.import_document(self.run)
        self.republish(self.record())

        self.document = keyword_document("dataset.xml", "de.919.keywordlist",
                                         GDI_BW_LIST.split(","))
        self.assertWrites(
            lambda: self.stored_file(self.new_run()).md_metadata_file_to_db(),
            **{self.record_table: 1, self.history_table: 1})

        record = self.record()
        self.assertEqual(record.insufficient_quality, "")
        self.assertFalse(record.is_broken)
        self.assertNotIn(GDI_BW_LIST, [k.keyword for k in record.keywords.all()])

    def test_a_record_imported_before_the_rule_is_flagged_by_an_unchanged_reharvest(self):
        """the row entered the registry while the indicator had no writer; the
        next run books it as EXISTING and writes nothing itself - the rule
        still evaluates and, as the answer differs, writes the flag (#919
        decision 3: the flag must not need a metadata change to arrive)"""
        self.import_document(self.run)
        DatasetMetadataRecord.objects.filter(pk=self.record().pk).update(
            insufficient_quality="")

        self.assertWrites(
            lambda: self.import_document(self.new_run()),
            **{self.record_table: 1, self.history_table: 1})

        record = self.record()
        self.assertIn("publishes 11 values", record.insufficient_quality)
        self.assertFalse(record.is_customized,
                         "the flag of the machine is not an editor's change")
        self.assertEqual(
            record.change_logs.order_by('history_date').last()
            .history_change_reason, "quality")

    def test_a_clean_record_stays_unwritten_and_unflagged(self):
        """the corpus majority: keywords which are single values and legitimate
        appositions answer an empty field and cost no extra write"""
        self.document = (ISO_DATA / "dataset.xml").read_bytes()

        self.import_document(self.run)
        self.assertEqual(self.record().insufficient_quality, "")
        self.assertWrites(lambda: self.import_document(self.new_run()))
        self.assertEqual(self.record().insufficient_quality, "")

    def test_the_run_logs_the_flag_once_and_stays_quiet_otherwise(self):
        self.import_document(self.run)

        self.assertEqual(self.quality_logs(self.run).count(), 1)
        self.assertIn("Flächennutzungsplan WN Remshalden",
                      self.quality_log_text(self.quality_logs(self.run).first()))

        run = self.new_run()
        self.import_document(run)

        self.assertEqual(self.quality_logs(run).count(), 0,
                         "an unchanged re-harvest re-answers the stored flag "
                         "and does not tell the log about it again")

    def test_the_run_of_a_clean_document_logs_no_quality_warning(self):
        self.document = (ISO_DATA / "dataset.xml").read_bytes()

        self.import_document(self.run)

        self.assertFalse(self.quality_logs(self.run).exists())

    def test_the_record_is_republished_with_the_merged_keyword_as_one_element(self):
        """mrmap hands the catalogue's own answer back out: the stored document
        and the keyword relation keep the list as the one element it was -
        quality flag and republished record are answers to different
        questions (#894/#906: storage stays tolerant)"""
        self.import_document(self.run)

        record = self.record()
        with record.xml_backup_file.open("rb") as stored:
            document = etree.fromstring(stored.read())
        merged_elements = [
            k for k in document.xpath("//*[local-name()='keyword']")
            if ",".join(k.itertext()).strip() == GDI_BW_LIST]
        self.assertEqual(len(merged_elements), 1, etree.tostring(
            document)[:1200])

        keywords = [k.keyword for k in record.keywords.all()]
        self.assertEqual(keywords.count(GDI_BW_LIST), 1)

    def test_service_and_application_records_get_the_flag_too(self):
        """all three record types flow through this one finalization"""
        for record_type, (sample, model) in SAMPLES.items():
            with self.subTest(record_type=record_type):
                self.run = self.new_run()
                self.document = keyword_document(
                    sample, f"de.919.keywordlist.{record_type}",
                    [GDI_BW_LIST])

                self.import_document(self.run)

                record = model.objects.get()
                self.assertIn(
                    "publishes 11 values", record.insufficient_quality,
                    f"{record_type} records carry the answer of the rule")
                self.assertFalse(record.is_broken)


class KeywordQualityApiTest(ImportHarness, TestCase):
    """The written flag is what the filter and the serializer of #600 answer."""

    fixtures = ['test_users.json']

    def setUp(self):
        super().setUp()
        self.document = keyword_document("dataset.xml", "de.919.keywordlist",
                                         [GDI_BW_LIST])
        self.import_document(self.new_run())
        user = get_user_model().objects.get(username="User1")
        user.is_superuser = True
        user.save()
        self.client = APIClient()
        self.client.force_authenticate(user=user)

    def test_the_quality_filter_answers_the_flagged_record(self):
        # the registry router is registered without trailing slashes
        response = self.client.get(
            "/api/registry/dataset-metadata?filter[has_insufficient_quality]=true",
            HTTP_ACCEPT="application/vnd.api+json")

        self.assertEqual(response.status_code, 200, response.content[:600])
        titles = [row["attributes"]["title"] for row in response.json()["data"]]
        self.assertEqual(titles, ["Windgeschwindigkeit an RBSN Stationen"])

        response = self.client.get(
            "/api/registry/dataset-metadata?filter[has_insufficient_quality]=false",
            HTTP_ACCEPT="application/vnd.api+json")
        self.assertEqual(response.json()["data"], [],
                         "and only the flagged record answers the true facet")

    def test_the_serializer_answers_the_text_verbatim(self):
        record = DatasetMetadataRecord.objects.get()

        response = self.client.get(
            f"/api/registry/dataset-metadata/{record.pk}",
            HTTP_ACCEPT="application/vnd.api+json")

        self.assertEqual(response.status_code, 200, response.content[:600])
        self.assertIn("publishes 11 values",
                      response.json()["data"]["attributes"]["insufficientQuality"])
