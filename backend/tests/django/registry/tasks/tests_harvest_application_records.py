"""Harvesting application records end to end: flag, request, import, relation (#827).

The flag ``HarvestingJob.harvest_applications`` (default True, epic #824) requests
``application`` records with the same OR-filter the two existing types travel in, the
import task writes what it delivers onto ``ApplicationMetadataRecord`` through the very
path a downloaded record takes, and the bookkeeping relation learns the third column.
This module is the contract of that story:

* the record types a run requests are the flags set on the job, and the GetRecords
  constraint of such a run carries one ``ogc:Literal`` per requested type - three by
  default, and the ``csw:Record`` fallback of #689 carries them too;
* an application document imported through the harvest import task lands as an
  ``ApplicationMetadataRecord`` with a ``HarvestedMetadataRelation`` of the application
  column, and answers the collecting states new / updated / existing / duplicated the
  way the two existing types do;
* a document the catalogue delivered for the run's buckets but whose XML names another
  ``hierarchyLevel`` is dropped as unhandled and loud - the post-filter decision of
  #826. The spike measured 0/10 violations on four live catalogues, so these are the
  guard-rail tests;
* an import without a catalogue behind it is no bucket delivery and stays unfiltered,
  and the unsupported ``CHE_MD_Metadata`` root (#825 decision) stays the documented
  clean import error of the mapper detection - not a crash;
* the relation table keeps its XOR over three columns and its per-type unique states.

The documents are the #825 spike samples under ``test_data/iso_metadata/`` which #826
landed; the expectations on their contents live with the mapping tests of #826.
"""

from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import unquote

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.db.models import F
from django.test import TestCase, override_settings
from django.utils.timezone import now
from MrMap.settings import BASE_DIR
from registry.enums.harvesting import CollectingStatenEnum as State
from registry.enums.harvesting import HarvestingPhaseEnum as Phase
from registry.enums.harvesting import LogLevelEnum
from registry.enums.metadata import MetadataOriginEnum
from registry.models.harvest import (HarvestedMetadataRelation, HarvestingJob,
                                     TemporaryMdMetadataFile)
from registry.models.metadata import (ApplicationMetadataRecord,
                                      DatasetMetadataRecord, MetadataContact,
                                      ServiceMetadataRecord)
from registry.models.service import CatalogueService
from registry.ows_lib.client.core import OgcClient
from registry.tasks.harvest import import_md_metadata_file
from tests.django.utils import MockResponse

ISO_DATA = Path(__file__).parent / '../../test_data/iso_metadata'

CAPABILITIES = f"{BASE_DIR}/tests/django/test_data/capabilities/csw/2.0.2.xml"

# the reference fixture of #826: GDI-BW "Geoportal Stadt Schwäbisch Hall"
APPLICATION = ISO_DATA / 'gdi-bw-04.xml'
APPLICATION_FID = "78538593-0e19-a5b7-c64a-756898eac073"
DATASET = ISO_DATA / 'dataset.xml'
SERVICE = ISO_DATA / 'service.xml'

ZERO_RECORDS = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<csw:GetRecordsResponse xmlns:csw="http://www.opengis.net/cat/csw/2.0.2">'
    '<csw:SearchResults numberOfRecordsMatched="0" numberOfRecordsReturned="0"'
    ' elementSet="summary" nextRecord="0" />'
    '</csw:GetRecordsResponse>'
)


def get_records_document(start_position, answered, total):
    """a GetRecords answer naming `total` records and carrying `answered` of them"""
    records = "".join(
        f'<gmd:MD_Metadata gco:id="r{start_position + i}"/>' for i in range(answered))
    return ('<csw:GetRecordsResponse xmlns:csw="http://www.opengis.net/cat/csw/2.0.2"'
            ' xmlns:gmd="http://www.isotc211.org/2005/gmd"'
            ' xmlns:gco="http://www.isotc211.org/2005/gco">'
            f'<csw:SearchResults numberOfRecordsMatched="{total}"'
            f' numberOfRecordsReturned="{answered}" elementSet="full" nextRecord="0">'
            f'{records}</csw:SearchResults></csw:GetRecordsResponse>')


class HarvestHarness:
    """A catalogue, a run and a stored document, imported the way the task does.

    Nothing is mocked but the remote service itself: documents are stored the way
    ``_store_page`` stores a downloaded record and are imported by the function the
    import task calls.
    """

    def setUp(self):
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        settings = override_settings(MEDIA_ROOT=media.name)
        settings.enable()
        self.addCleanup(settings.disable)
        self.contact = MetadataContact.objects.create(name='Application harvest contact')
        self.catalogue = CatalogueService(
            id='22222222-1111-1111-1111-111111111111', title='Application catalogue',
            version=202, origin=1, service_url='https://example.com/csw',
            metadata_contact=self.contact, service_contact=self.contact)
        CatalogueService.objects.bulk_create([self.catalogue])
        with open(CAPABILITIES, mode='rb') as cap:
            self.catalogue.xml_backup_file = SimpleUploadedFile(
                'capabilities.xml', cap.read())
        self.catalogue.save()

    def new_run(self, **flags):
        """A harvesting run of the catalogue, downloading the way a flagged run does.

        A catalogue only carries one unfinished job, so the runs of a test close
        in order, each one answering what it harvested.
        """
        HarvestingJob.objects.filter(
            service=self.catalogue, done_at__isnull=True).update(done_at=now())
        job = HarvestingJob(
            service=self.catalogue, total_records=1,
            phase=Phase.RECORDS_TO_DB)
        for key, value in flags.items():
            setattr(job, key, value)
        HarvestingJob.objects.bulk_create([job])
        return job

    def stored(self, job, document):
        """The document of a run, stored and waiting for the import."""
        file = TemporaryMdMetadataFile(
            job=job, requested_url='https://example.com/csw?page=1',
            download_duration=None)
        file.md_metadata_file.save(
            Path(document).name, ContentFile(Path(document).read_bytes()), save=False)
        TemporaryMdMetadataFile.objects.bulk_create([file])
        return file


class ApplicationRecordImportTest(HarvestHarness, TestCase):
    """The mapping-to-model path of an application record, through the import task."""

    def import_document(self, job, document=APPLICATION):
        return import_md_metadata_file(self.stored(job, document).pk)

    def relation(self, job, record):
        return HarvestedMetadataRelation.objects.get(
            harvesting_job=job, application_metadata_record=record)

    def test_application_document_lands_as_application_record_and_relation(self):
        job = self.new_run()
        results = self.import_document(job)
        self.assertEqual(len(results), 1)
        record = ApplicationMetadataRecord.objects.get(
            file_identifier=APPLICATION_FID)
        self.assertEqual(record.title, "Geoportal Stadt Schwäbisch Hall")
        # the bookkeeping: the relation carries the record in the application column
        # and names the run which found it
        relation = self.relation(job, record)
        self.assertEqual(relation.collecting_state, State.NEW)
        self.assertIsNone(relation.dataset_metadata_record_id)
        self.assertIsNone(relation.service_metadata_record_id)
        self.assertIn(str(self.catalogue.pk),
                      [str(pk) for pk in record.harvested_through.values_list('pk', flat=True)])
        # a successful import deletes the stored file
        self.assertFalse(TemporaryMdMetadataFile.objects.filter(job=job).exists())
        # the provenance of the run reaches the record: #976 fixed the defaults for
        # every record type and the application path travels with the fix
        self.assertEqual(record.origin, MetadataOriginEnum.CATALOGUE.value)
        self.assertEqual(
            record.origin_url,
            self.catalogue.client.get_record_by_id_request(id=APPLICATION_FID).url)

    def test_collecting_states_new_updated_existing_and_duplicated(self):
        job = self.new_run()
        self.import_document(job)
        record = ApplicationMetadataRecord.objects.get(
            file_identifier=APPLICATION_FID)
        self.assertEqual(self.relation(job, record).collecting_state, State.NEW)

        # a catalogue which republishes the document: the next run updates it
        ApplicationMetadataRecord.objects.filter(pk=record.pk).update(
            date_stamp=F('date_stamp') - timedelta(days=1))
        republished = self.new_run()
        self.import_document(republished)
        self.assertEqual(
            self.relation(republished, record).collecting_state, State.UPDATED)

        # the next run again changes nothing
        untouched = self.new_run()
        self.import_document(untouched)
        self.assertEqual(
            self.relation(untouched, record).collecting_state, State.EXISTING)

        # the same run delivering the record twice is a duplication the remote
        # service is guilty of - kept for analysis, flagged on the file (#858 lineage)
        file = self.stored(untouched, APPLICATION)
        import_md_metadata_file(file.pk)
        states = list(HarvestedMetadataRelation.objects.filter(
            harvesting_job=untouched,
            application_metadata_record=record).values_list(
                'collecting_state', flat=True))
        self.assertIn(State.EXISTING, states)
        self.assertIn(State.DUPLICATED, states)
        file.refresh_from_db()
        self.assertTrue(file.has_import_error)
        self.assertIn('duplicated', file.import_error)

    def test_dataset_and_service_documents_still_land_on_their_own_models(self):
        """the third bucket shares the run without disturbing the two existing paths"""
        job = self.new_run()
        self.import_document(job, DATASET)
        self.import_document(job, SERVICE)
        self.assertEqual(DatasetMetadataRecord.objects.count(), 1)
        self.assertEqual(ServiceMetadataRecord.objects.count(), 1)
        self.assertEqual(
            HarvestedMetadataRelation.objects.filter(
                harvesting_job=job,
                dataset_metadata_record__isnull=False).count(), 1)
        self.assertEqual(
            HarvestedMetadataRelation.objects.filter(
                harvesting_job=job,
                service_metadata_record__isnull=False).count(), 1)


class BucketMismatchPostFilterTest(HarvestHarness, TestCase):
    """Records delivered for the run's buckets which the XML disagrees with (#826).

    The application bucket of #827 is what the filter of the request feeds; the
    detected hierarchyLevel is what the document says. A mismatch is dropped as
    unhandled and loud, never stored by the filter the catalogue's index passed.
    """

    def assertDroppedLoud(self, job, file, detected, requested):
        self.imports_nothing(job, file)
        # the file stays for inspection, like every unhandled record
        file.refresh_from_db()
        self.assertTrue(file.has_import_error)
        self.assertIn('hierarchy_level_mismatch', file.import_error)
        self.assertIn(detected, file.import_error)
        log = job.logs.get(level=LogLevelEnum.ERROR.value)
        self.assertIn(f"hierarchyLevel '{detected}'", log.description)
        for literal in requested:
            self.assertIn(literal, log.description)

    def imports_nothing(self, job, file):
        """Imports the file and asserts no record of any kind was written."""
        before = (ApplicationMetadataRecord.objects.count(),
                  DatasetMetadataRecord.objects.count(),
                  ServiceMetadataRecord.objects.count())
        import_md_metadata_file(file.pk)
        self.assertEqual((ApplicationMetadataRecord.objects.count(),
                          DatasetMetadataRecord.objects.count(),
                          ServiceMetadataRecord.objects.count()), before)
        self.assertFalse(
            HarvestedMetadataRelation.objects.filter(harvesting_job=job).exists())

    def test_a_service_record_delivered_for_the_application_bucket_is_dropped(self):
        """the synthetic violation of the #826 decision: the index says application,
        the XML says service - the document never lands, the run says so loudly.
        (The spike measured 0/10 of these on four live catalogues.)"""
        job = self.new_run(harvest_datasets=False, harvest_services=False)
        file = self.stored(job, SERVICE)
        self.assertDroppedLoud(job, file, 'service', ['application'])

    def test_an_application_record_delivered_to_a_legacy_run_is_dropped(self):
        """harvest_applications=False keeps the legacy semantics: the record is not
        stored - it would poison the per-type counts which gate the snapshot math -
        and the log names the run which could not place it"""
        job = self.new_run(harvest_applications=False)
        file = self.stored(job, APPLICATION)
        self.assertDroppedLoud(job, file, 'application', ['dataset', 'service'])

    def test_a_requested_bucket_imports_and_stays_silent(self):
        """the guard rail only fires on mismatches: a run harvesting datasets and
        applications stores the application document without a trace"""
        job = self.new_run(harvest_services=False)
        results = import_md_metadata_file(self.stored(job, APPLICATION).pk)
        self.assertEqual(len(results), 1)
        self.assertFalse(job.logs.filter(
            level__lte=LogLevelEnum.ERROR.value).exists())

    def test_an_import_without_a_catalogue_is_no_bucket_delivery(self):
        """a document handed in by somebody chooses its bucket by being imported -
        the post-filter never fires for a file import"""
        job = HarvestingJob(total_records=1, phase=Phase.RECORDS_TO_DB)
        HarvestingJob.objects.bulk_create([job])
        results = import_md_metadata_file(self.stored(job, APPLICATION).pk)
        self.assertEqual(len(results), 1)
        self.assertTrue(ApplicationMetadataRecord.objects.filter(
            file_identifier=APPLICATION_FID).exists())

    def test_a_che_md_metadata_document_stays_a_clean_import_error(self):
        """CHE_MD_Metadata (geocat.ch) is unsupported on purpose (#825 decision):
        the shared MD_Metadata detection of the mapper rejects it, so the document
        lands as a documented import error which the run keeps for inspection -
        loud, and no crash and no record"""
        job = self.new_run()
        file = self.stored(job, ISO_DATA / 'geocat-01.xml')
        self.assertIsNone(import_md_metadata_file(file.pk))
        self.assertEqual(ApplicationMetadataRecord.objects.count(), 0)
        file.refresh_from_db()
        self.assertTrue(file.has_import_error)
        self.assertIn("No MD_Metadata elements found", file.import_error)


class RelationOfThreeTest(TestCase):
    """The XOR of three and the per-type unique states of the relation table (#827)."""

    @classmethod
    def setUpTestData(cls):
        contact = MetadataContact.objects.create(name='Relation contact')
        cls.job = HarvestingJob(total_records=0, phase=Phase.RECORDS_TO_DB)
        HarvestingJob.objects.bulk_create([cls.job])
        cls.dataset = DatasetMetadataRecord(
            metadata_contact=contact, dataset_contact=contact, title='Dataset')
        cls.service = ServiceMetadataRecord(
            metadata_contact=contact, title='Service metadata')
        cls.application = ApplicationMetadataRecord(
            metadata_contact=contact, application_contact=contact,
            title='Application')
        DatasetMetadataRecord.objects.bulk_create([cls.dataset])
        ServiceMetadataRecord.objects.bulk_create([cls.service])
        ApplicationMetadataRecord.objects.bulk_create([cls.application])

    def relation(self, **columns):
        return HarvestedMetadataRelation(
            harvesting_job=self.job, collecting_state=State.NEW, **columns)

    def test_exactly_one_of_the_three_columns_may_carry_the_record(self):
        for columns in [
            dict(dataset_metadata_record=self.dataset,
                 application_metadata_record=self.application),
            dict(dataset_metadata_record=self.dataset,
                 service_metadata_record=self.service,
                 application_metadata_record=self.application),
            {},
        ]:
            with self.subTest(columns=sorted(columns)):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        self.relation(**columns).save()
        # and the one application relation is exactly what the table accepts
        self.relation(application_metadata_record=self.application).save()

    def test_each_type_keeps_its_new_updated_and_existing_state_atomic(self):
        for state in [State.NEW, State.UPDATED, State.EXISTING]:
            with self.subTest(state=state):
                HarvestedMetadataRelation.objects.create(
                    harvesting_job=self.job,
                    application_metadata_record=self.application,
                    collecting_state=state)
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        HarvestedMetadataRelation.objects.create(
                            harvesting_job=self.job,
                            application_metadata_record=self.application,
                            collecting_state=state)
        # duplicated is the state a run may answer more than once, for analysis
        for _ in range(2):
            HarvestedMetadataRelation.objects.create(
                harvesting_job=self.job,
                application_metadata_record=self.application,
                collecting_state=State.DUPLICATED)

    def test_a_removed_relation_names_the_application_it_dropped(self):
        HarvestedMetadataRelation.objects.create(
            harvesting_job=self.job,
            application_metadata_record=self.application,
            collecting_state=State.REMOVED)
        self.assertEqual(
            HarvestedMetadataRelation.objects.filter(
                harvesting_job=self.job, collecting_state=State.REMOVED).count(), 1)


class RequestFilterTest(HarvestHarness, TestCase):
    """What the flags of a run ask the catalogue for - and the fan-out built on it."""

    def constraint_of(self, job):
        client = self.catalogue.client
        return client.get_constraint(record_types=job.get_record_types())

    def test_the_flags_of_a_run_are_its_record_types(self):
        for flags, expected in [
            ({}, ["dataset", "service", "application"]),
            (dict(harvest_applications=False), ["dataset", "service"]),
            (dict(harvest_datasets=False, harvest_services=False), ["application"]),
        ]:
            with self.subTest(flags=flags):
                job = self.new_run(**flags)
                self.assertEqual(job.get_record_types(), expected)
                constraint = self.constraint_of(job)
                for literal in expected:
                    self.assertIn(f"<ogc:Literal>{literal}</ogc:Literal>", constraint)
                if len(expected) == 1:
                    self.assertNotIn("<ogc:Or>", constraint)
                else:
                    self.assertIn("<ogc:Or>", constraint)

    @patch.object(target=OgcClient, attribute="send_request")
    def test_total_records_and_its_fallback_carry_the_three_type_filter(self, send):
        """the #689 fallback which saves broken catalogues must ask for the third
        type with the same filter it fell back with - or a catalogue which only
        answers csw:Record would silently stop answering applications. The step
        size probe of #694 plans the fan-out afterwards and asks about hits - with
        the same three-type constraint."""
        asked = []

        def answer(request, timeout):
            asked.append(request.url)
            if "csw%3ARecord" in request.url:
                return MockResponse(
                    content=get_records_document(1, 0, total=7), status_code=200)
            return MockResponse(content=ZERO_RECORDS, status_code=200)
        send.side_effect = answer
        job = self.new_run()
        HarvestingJob.objects.filter(pk=job.pk).update(
            phase=Phase.GET_TOTAL_RECORDS_COUNT)
        job.refresh_from_db()
        self.assertEqual(job.fetch_total_records(), 7)
        # gmd request refused to name records, the csw:Record fallback answered 7,
        # the probe of the fan-out size asked about hits
        self.assertEqual(len(asked), 3)
        self.assertIn("csw%3ARecord", asked[1])
        for url in asked:
            constraint = unquote(url)
            for literal in ["dataset", "service", "application"]:
                self.assertIn(
                    f"<ogc:Literal>{literal}</ogc:Literal>", constraint)

    @patch.object(target=OgcClient, attribute="send_request")
    def test_the_page_fan_out_requests_what_the_run_flags(self, send):
        """with the flag on a downloaded page is asked for with the application
        literal, with the flag off it never names the bucket"""
        def answer(request, timeout):
            return MockResponse(
                content=get_records_document(1, 1, total=1), status_code=200,
                url=request.url)
        send.side_effect = answer
        for flag, names_application in [(True, True), (False, False)]:
            with self.subTest(harvest_applications=flag):
                job = self.new_run(harvest_applications=flag)
                HarvestingJob.objects.filter(pk=job.pk).update(
                    phase=Phase.DOWNLOAD_RECORDS, total_records=1)
                job.refresh_from_db()
                self.assertEqual(job.fetch_records(start_position=1), 1)
                url = TemporaryMdMetadataFile.objects.get(
                    job=job).requested_url
                if names_application:
                    self.assertIn("%3Eapplication%3C", url)
                else:
                    self.assertNotIn("%3Eapplication%3C", url)
