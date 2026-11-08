"""#1044: reading a service's capabilities never fetches the remote document.

`Service.capabilities` used to answer a stored file which is gone from the
media storage with the service's GetCapabilities URL, and `OgcClient.__init__`
answered that string with a synchronous remote GetCapabilities request - on
*every* access, up to 3 times per imported record file, never healing the
state it warned about. The maintainer decision on the issue splits the
operations: a stored read (no network, no writes), an explicit remote fetch
(`remote_capabilities`, staged as an update candidate only), and recovery of
the storage - never a blind save while something is read.

These tests pin the read half of that split, with the calls and queries
counted: a present document is answered locally; a missing one raises the
integrity error of the service once (deduplicated, cleared on a verified
re-read) without touching the row, without reaching the network and without
being laundered into a per-record import error. The last class pins the
operator half: the refresh probes the storage and the alert row exists
exactly while the named document is gone (#1044).
"""

import os
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from registry.enums.harvesting import HarvestingPhaseEnum as Phase
from registry.enums.metadata import MetadataOriginEnum
from registry.exceptions.service import CapabilitiesBackupMissing
from registry.models.alerts import ServiceAlert
from registry.models.harvest import HarvestingJob, TemporaryMdMetadataFile
from registry.models.metadata import (ApplicationMetadataRecord,
                                      DatasetMetadataRecord, MetadataContact,
                                      ServiceMetadataRecord)
from registry.models import service as service_module
from registry.models.service import CatalogueService, WebMapService
from registry.ows_lib.csw.csw import CatalogueServiceClient
from registry.querys.alerts import refresh_service_alerts
from registry.tasks.harvest import import_md_metadata_file

TEST_DATA = Path(__file__).parent / '../../test_data'
CAPABILITIES = TEST_DATA / 'capabilities/csw/2.0.2.xml'

# the three #825 spike documents, one per record kind - the same corpus the
# harvest roundtrip of the import imports
PUBLISHED = (
    (DatasetMetadataRecord, 'dataset.xml', 'de.dwd.geoserver.fach.RBSN_FF'),
    (ServiceMetadataRecord, 'service.xml',
     'ee065040-1015-44c7-839e-e8e349c74bbd'),
    (ApplicationMetadataRecord, 'gdi-bw-04.xml',
     '78538593-0e19-a5b7-c64a-756898eac073'),
)

WRITE_SQL = re.compile(r'^\s*(INSERT|UPDATE|DELETE)\b', re.IGNORECASE)


def write_queries(captured):
    """The write statements among the captured queries of a context."""
    return [q['sql'] for q in captured if WRITE_SQL.match(q['sql'])]


def logged_messages(calls):
    """The messages of logger calls made with the ``msg=`` keyword, as the
    structured logging of this project calls it."""
    return [
        c.kwargs.get('msg', c.args[0] if c.args else '') for c in calls]


class CapabilitiesReadHarness:
    """A catalogue with a stored capabilities document on a temp storage.

    The process-wide dedup of the integrity report must not leak between
    tests, so its registry is emptied after each one.
    """

    def setUp(self):
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        settings = override_settings(MEDIA_ROOT=media.name)
        settings.enable()
        self.addCleanup(settings.disable)
        self.addCleanup(service_module._capabilities_backup_missing.clear)

    def make_catalogue(self):
        """A CSW whose `xml_backup_file` names a real file on the storage."""
        contact = MetadataContact.objects.create(
            name='capabilities integrity contact')
        catalogue = CatalogueService.objects.create(
            title='Integrity catalogue', version=202, origin=1,
            service_url='https://integrity.example.org/csw',
            metadata_contact=contact, service_contact=contact)
        catalogue.xml_backup_file = SimpleUploadedFile(
            'capabilities.xml', CAPABILITIES.read_bytes())
        catalogue.save()
        return catalogue

    def remove_backup_file(self, catalogue):
        """Deletes the named file; the row keeps naming it (storage incident).

        Only a name in the database whose file is gone raises
        FileNotFoundError out of `xml_backup` - an unset field answers b"".
        """
        path = catalogue.xml_backup_file.path
        os.remove(path)
        return path


class StoredCapabilitiesReadTest(CapabilitiesReadHarness, TestCase):
    """A present document is answered by reading it, and by nothing else."""

    def setUp(self):
        super().setUp()
        self.catalogue = self.make_catalogue()

    def test_read_and_client_build_are_local_and_side_effect_free(self):
        """Zero remote calls and zero writes for one capabilities read.

        The read, the client construction out of it and the local request
        derivation must ask the remote nothing and write nothing: neither
        the service row, nor a history row, nor any other table.
        """
        stored = CAPABILITIES.read_bytes()
        with patch("requests.Session.send") as send, \
                CaptureQueriesContext(connection) as queries:
            self.assertEqual(stored, self.catalogue.capabilities)
            client = self.catalogue.client
            # the operation url comes out of the parsed stored document,
            # not out of a request
            url = client.get_record_by_id_request(id='some-id').url
        send.assert_not_called()
        self.assertIn('GetRecordById', url)
        self.assertEqual([], write_queries(queries.captured_queries))
        self.catalogue.refresh_from_db()
        self.assertTrue(
            self.catalogue.xml_backup_file.name.endswith('capabilities.xml'),
            "a read never rewrites the file reference of the service")

    def test_client_is_built_once_per_service_instance(self):
        """One instance, one client - the accesses of a run share it (#1044).

        The client holds a parsed document and a requests session; the
        cache must stay bound to the instance, so a freshly fetched service
        still gets its own client and nothing is shared across instances.
        """
        with patch(
                "registry.models.service.CatalogueServiceClient",
                side_effect=CatalogueServiceClient) as built:
            first = self.catalogue.client
            again = self.catalogue.client
            self.assertIs(first, again)
            fresh = CatalogueService.objects.get(pk=self.catalogue.pk)
            fresh_client = fresh.client
        self.assertEqual(2, built.call_count)
        self.assertIsNot(first, fresh_client)


class MissingCapabilitiesIntegrityTest(CapabilitiesReadHarness, TestCase):
    """A missing document is an integrity error, not a remote fallback."""

    def setUp(self):
        super().setUp()
        self.catalogue = self.make_catalogue()
        self.stored = CAPABILITIES.read_bytes()

    def test_missing_document_raises_without_reaching_the_network(self):
        """Every access raises; nothing is fetched, nothing is healed remotely.

        The access which used to hand the GetCapabilities URL to the client
        constructor now raises the integrity error which names the service,
        the type, the missing path and the recovery status.
        """
        name = self.catalogue.xml_backup_file.name
        self.remove_backup_file(self.catalogue)
        with patch("requests.Session.send") as send:
            with self.assertRaises(CapabilitiesBackupMissing) as ctx:
                _ = self.catalogue.capabilities
            with self.assertRaises(CapabilitiesBackupMissing):
                _ = self.catalogue.client
            with self.assertRaises(CapabilitiesBackupMissing):
                _ = self.catalogue.capabilities
        send.assert_not_called()
        message = str(ctx.exception)
        self.assertIn(str(self.catalogue.pk), message)
        self.assertIn("CSW", message)
        self.assertIn(name, message)
        self.assertEqual("CSW", ctx.exception.service_type)
        self.assertEqual(name, ctx.exception.missing_path)

    def test_missing_document_is_never_written_back(self):
        """The blocking invariant of #1044: no blind save.

        Failing reads leave the row, its file reference, the storage and
        the service history exactly as they were.
        """
        name_before = self.catalogue.xml_backup_file.name
        history_before = self.catalogue.change_log.count()
        path = self.remove_backup_file(self.catalogue)
        with patch("requests.Session.send"), \
                CaptureQueriesContext(connection) as queries:
            with self.assertRaises(CapabilitiesBackupMissing):
                _ = self.catalogue.capabilities
            with self.assertRaises(CapabilitiesBackupMissing):
                _ = self.catalogue.client
        self.assertEqual([], write_queries(queries.captured_queries))
        self.catalogue.refresh_from_db()
        self.assertEqual(name_before, self.catalogue.xml_backup_file.name)
        self.assertEqual(history_before, self.catalogue.change_log.count())
        self.assertFalse(os.path.exists(path))

    def test_the_report_is_deduplicated_until_the_document_reads_well(self):
        """One warning per service and process, cleared by a verified re-read.

        The flood of the old fallback was one dump per access; the integrity
        report stays one per service while the condition holds, a read which
        answers the document again reports the resolution and clears the
        entry, and a later loss is reported again.
        """
        path = self.remove_backup_file(self.catalogue)
        with patch("registry.models.service.logger") as log:
            for _ in range(5):
                with self.assertRaises(CapabilitiesBackupMissing):
                    _ = self.catalogue.capabilities
            warnings = [
                m for m in logged_messages(log.warning.call_args_list)
                if "no capabilities file" in m]
            self.assertEqual(1, len(warnings),
                             "5 accesses must leave exactly one warning")

            # storage restored: the next read is the verified resolution
            with open(path, "wb") as f:
                f.write(self.stored)
            self.assertEqual(self.stored, self.catalogue.capabilities)
            clearings = [
                m for m in logged_messages(log.info.call_args_list)
                if "reads well again" in m]
            self.assertEqual(1, len(clearings))
            self.assertNotIn(
                (self.catalogue._meta.label, str(self.catalogue.pk)),
                service_module._capabilities_backup_missing)

            # a later loss of the same service reports again
            os.remove(path)
            with self.assertRaises(CapabilitiesBackupMissing):
                _ = CatalogueService.objects.get(pk=self.catalogue.pk).capabilities
            warnings = [
                m for m in logged_messages(log.warning.call_args_list)
                if "no capabilities file" in m]
            self.assertEqual(2, len(warnings))


class HarvestImportCapabilitiesTest(CapabilitiesReadHarness, TestCase):
    """The import of N record files asks the remote nothing at all."""

    def setUp(self):
        super().setUp()
        self.catalogue = self.make_catalogue()
        self.job = HarvestingJob.objects.create(
            service=self.catalogue, total_records=0,
            phase=Phase.RECORDS_TO_DB)

    def store_record_file(self, document):
        file = TemporaryMdMetadataFile.objects.create(
            job=self.job, requested_url='https://integrity.example.org/csw',
            download_duration=None)
        file.md_metadata_file.save(
            'md_metadata.xml',
            ContentFile((TEST_DATA / 'iso_metadata' / document).read_bytes()))
        return file

    def test_import_builds_the_client_once_per_file_and_fetches_nothing(self):
        """No GetCapabilities round trip per record, no per-bucket build.

        The provenance dict names three buckets for the same origin url;
        each imported file must pay one client construction out of the
        stored document - and zero remote calls, zero operation_urls
        queries. The issue measured 2, since #826 3 remote fetches per
        record while the document was missing.
        """
        files = [self.store_record_file(doc) for _, doc, _ in PUBLISHED]
        with patch(
                "registry.models.service.CatalogueServiceClient",
                side_effect=CatalogueServiceClient) as built, \
                patch("requests.Session.send") as send, \
                CaptureQueriesContext(connection) as queries:
            for file in files:
                import_md_metadata_file(file.pk)
        send.assert_not_called()
        self.assertEqual(len(files), built.call_count,
                         "one client construction per imported file, "
                         "not one per provenance bucket")
        operation_url_queries = [
            q['sql'] for q in queries.captured_queries
            if 'registry_operationurl' in q['sql']]
        self.assertEqual(
            [], operation_url_queries,
            "the import derives the origin url from the stored document")
        for model, _, identifier in PUBLISHED:
            record = model.objects.get(file_identifier=identifier)
            self.assertEqual(MetadataOriginEnum.CATALOGUE.value, record.origin)
            self.assertIn('GetRecordById', record.origin_url)

    def test_a_broken_catalogue_ends_the_import_with_the_integrity_error(self):
        """The service's missing document is not laundered into record errors.

        Importing against a service whose document is gone raises the
        integrity error and leaves the file unflagged: marking every file of
        the backlog with the same service-level failure is the per-record
        repetition of #1044 with error rows instead of warnings.
        """
        self.remove_backup_file(self.catalogue)
        file = self.store_record_file('dataset.xml')
        with patch("requests.Session.send") as send:
            with self.assertRaises(CapabilitiesBackupMissing):
                import_md_metadata_file(file.pk)
        send.assert_not_called()
        file.refresh_from_db()
        self.assertFalse(file.has_import_error)
        self.assertFalse(DatasetMetadataRecord.objects.filter(
            file_identifier='de.dwd.geoserver.fach.RBSN_FF').exists())

    def test_total_records_of_a_broken_catalogue_fails_before_requesting(self):
        """The harvest step which starts a run does not ask the remote either.

        `fetch_total_records` used to build the client before its first
        request; with the document gone the step raises the integrity error
        of the service without a single remote call - the run stops once,
        visibly, instead of paying the doomed round trip per retry.
        """
        self.remove_backup_file(self.catalogue)
        job = HarvestingJob.objects.get(pk=self.job.pk)
        with patch("requests.Session.send") as send:
            with self.assertRaises(CapabilitiesBackupMissing):
                job.fetch_total_records()
        send.assert_not_called()


class MissingCapabilitiesAlertTest(CapabilitiesReadHarness, TestCase):
    """The storage incident reaches the operator without reading the service.

    The second half of #1044: `refresh_service_alerts()` probes the storage
    and writes one alert row for a named-but-missing document - the read of
    the alerts cannot answer that state because the media storage is no
    table the annotations could join. The row names the missing path and the
    recovery, points at the workflow which owns it, and leaves no row behind
    once a restoration has been refreshed. A service whose field was never
    set is no such case, and a pending candidate is not alerted of its own
    storage state.
    """

    def name_named_document(self, service):
        """A service whose named document is removed from the storage again."""
        service.xml_backup_file = SimpleUploadedFile(
            'capabilities.xml', CAPABILITIES.read_bytes())
        service.save()
        os.remove(service.xml_backup_file.path)
        return service

    def test_refresh_writes_and_clears_the_row_of_a_catalogue(self):
        """The row exists exactly while the storage misses the document."""
        catalogue = self.make_catalogue()
        name = catalogue.xml_backup_file.name
        path = self.remove_backup_file(catalogue)

        refresh_service_alerts()
        row = ServiceAlert.objects.get(
            id=f'capabilities_backup_missing:CatalogueService:{catalogue.pk}')
        self.assertEqual('error', row.severity)
        self.assertEqual('CatalogueService', row.resource_type)
        self.assertIsNone(row.occurred_at,
                          "the storage incident has no decided moment")
        self.assertIn(name, row.message)
        self.assertIn(str(catalogue.pk), row.message)
        # a CSW update has no settings tab of its own: its overview owns
        # the recovery - the same rule the other alerts answer for a CSW
        self.assertEqual(
            f'/CatalogueService/{catalogue.pk}/show/', row.target_path)

        # nothing heals implicitly: only the refresh after a restoration
        # answers the state away, and then no row of it survives
        with open(path, 'wb') as f:
            f.write(CAPABILITIES.read_bytes())
        refresh_service_alerts()
        self.assertFalse(ServiceAlert.objects.filter(
            category='capabilities_backup_missing').exists())

    def test_a_service_without_a_named_document_reports_nothing(self):
        """An unset field is no incident - its read answers an empty document."""
        contact = MetadataContact.objects.create(name='unset alert contact')
        CatalogueService.objects.create(
            title='Never stored catalogue', version=202, origin=1,
            service_url='https://unset.example.org/csw',
            metadata_contact=contact, service_contact=contact)
        refresh_service_alerts()
        self.assertFalse(ServiceAlert.objects.filter(
            category='capabilities_backup_missing').exists())

    def test_a_map_service_alert_names_its_update_settings(self):
        """Only the CSW lacks a settings tab; the WMS alert owns its tab."""
        contact = MetadataContact.objects.create(name='map alert contact')
        map_service = self.name_named_document(
            WebMapService.objects.create(
                title='Integrity map service', version=130, origin=1,
                service_url='https://integrity.example.org/wms',
                metadata_contact=contact, service_contact=contact))

        refresh_service_alerts()
        row = ServiceAlert.objects.get(
            id=f'capabilities_backup_missing:WebMapService:{map_service.pk}')
        self.assertEqual(
            f'/WebMapService/{map_service.pk}/show/WebMapServiceUpdateSetting',
            row.target_path)

        # a pending candidate with the same incident is not a second alert:
        # it waits for the decision about the service it hangs below, which
        # is the rule the annotation branches answer for every category
        WebMapService.objects.create(
            title='Integrity candidate', service_url=map_service.service_url,
            version=map_service.version, origin=map_service.origin,
            update_candidate_of=map_service,
            metadata_contact=contact, service_contact=contact)
        candidate = WebMapService.objects.get(
            update_candidate_of=map_service)
        self.name_named_document(candidate)
        refresh_service_alerts()
        self.assertEqual(
            1, ServiceAlert.objects.filter(
                category='capabilities_backup_missing').count())
