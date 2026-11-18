"""The freshness policy of a service update (#1413).

Epic #1408 phase C asks which downstream work an update may skip when the
service did not change, and which it must repeat. The answer is recorded in
``docs/source/development/update-metadata-refresh-policy.rst``; this module
holds the deterministic tests behind its table:

* Unchanged capabilities decide NO_UPDATE_NEEDED without a candidate - yet
  the advertised ISO documents are still handed to the collection step
  (#1274): capabilities equality is a hash over the *capabilities* bytes, it
  proves nothing about the ISO documents the service points at.
* Adoption leaves the service stored as the new capabilities published it:
  the stored capabilities document is replaced by the one the update adopted
  (#1150, #1044 read exactly that file), so the next run of an unchanged
  service decides NO_UPDATE_NEEDED instead of staging a full candidate again.
* The advertised metadata references of the published service are the ones
  the adopted document advertises: rows the candidate carried move onto the
  published elements, rows the new document does not advertise anymore go
  away with this update's step collecting the new list - not the stale one
  of the registration.
* The rows of the table which live in the collection machinery - same URL
  with changed ISO bytes, same URL with unchanged bytes, a failed remote
  document - are answered in ``tests/django/registry/tasks/
  tests_metadata_collection.py`` and ``tests_collect_reference.py``; the
  update walks that very machinery (#1274), so they need no second fixture
  here.

The measurements the issue asks for ride on these tests: request counts are
pinned by the ``Session.send`` side_effect running out on any request the
flow should not make, parse counts by patching ``OGCServiceXmlMapper.from_xml``
- the one door every candidate document goes through.
"""

from pathlib import Path
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from MrMap.settings import BASE_DIR
from registry.enums.update import UpdateJobStatusEnum
from registry.mappers.factory import OGCServiceXmlMapper
from registry.models.metadata import (FeatureTypeRemoteMetadata,
                                      LayerRemoteMetadata,
                                      WebFeatureServiceRemoteMetadata,
                                      WebMapServiceRemoteMetadata)
from registry.models.service import (FeatureType, Layer,
                                     WebFeatureService, WebMapService)
from registry.models.update import (WebFeatureServiceUpdateJob,
                                    WebMapServiceUpdateJob)
from registry.tasks.service import advertised_references
from registry.tasks.update import (collect_update_metadata, run_csw_update,
                                   run_wfs_update, run_wms_update)
from requests.sessions import Session
from rest_framework import status
from tests.django.utils import MockResponse

WMS_CAPS_PATH = Path(f"{BASE_DIR}/tests/django/test_data/capabilities/"
                     "wms/fixture_1.3.0.xml")
WMS_SIMPLE_PATH = Path(f"{BASE_DIR}/tests/django/test_data/capabilities/"
                       "wms/simple_update_fixture_1.3.0.xml")
WFS_CAPS_PATH = Path(f"{BASE_DIR}/tests/django/test_data/capabilities/"
                     "wfs/fixture_2.0.0.xml")
WFS_SIMPLE_PATH = Path(f"{BASE_DIR}/tests/django/test_data/capabilities/"
                       "wfs/simple_update_fixture_2.0.0.xml")

# the service-level INSPIRE metadata link the WMS fixtures advertise, as the
# capabilities mapper reads it (entities decoded), and a replacement which
# only differs in the id it asks for - the "changed URL" row of the table
OLD_WMS_LINK = (
    "https://gdk.gdi-de.org/gdi-de/srv/eng/csw?request=GetRecordById"
    "&version=2.0.2&service=CSW"
    "&outputSchema=http://www.isotc211.org/2005/gmd"
    "&elementSetName=full&id=de.dwd.services.wms")
NEW_WMS_LINK = OLD_WMS_LINK.replace("id=de.dwd.services.wms",
                                    "id=de.example.updated")
# the entity-encoded spelling inside the XML, and the replaced one
OLD_WMS_LINK_XML = OLD_WMS_LINK.replace("&", "&amp;")
NEW_WMS_LINK_XML = NEW_WMS_LINK.replace("&", "&amp;")

# the feature-type level link of the WFS fixtures and its replacement
OLD_WFS_LINK = ("https://registry.gdi-de.org/id/de.bund.dwd/"
                "de.dwd.geoserver.fach.RBSN_T2m")
NEW_WFS_LINK = OLD_WFS_LINK.replace("RBSN_T2m", "RBSN_updated")


def _caps_response(path: Path, replace: tuple[str, str] | None = None):
    if replace:
        content = path.read_text().replace(*replace)
        return MockResponse(status_code=status.HTTP_200_OK, content=content)
    return MockResponse(status_code=status.HTTP_200_OK, content=path)


class UpdateHarness(TestCase):
    """The publication seams an update job hands work over to, captured."""

    def setUp(self):
        super().setUp()
        self.dispatched = []
        for task in (collect_update_metadata, ):
            patcher = patch.object(task, 'apply_async', autospec=True)
            mock = patcher.start()
            self.addCleanup(patcher.stop)
            mock.side_effect = lambda *a, **kw: self.dispatched.append(
                (task.name, kw))
        for runner in (run_wms_update, run_wfs_update, run_csw_update):
            patcher = patch.object(runner, 'apply_async', autospec=True)
            self.addCleanup(patcher.stop)
            patcher.start()


class WmsRefreshPolicyTests(UpdateHarness):
    fixtures = ['test_users.json', 'test_keywords.json', 'test_wms.json']

    def setUp(self):
        super().setUp()
        self.wms = WebMapService.objects.get(
            pk="cd16cc1f-3abb-4625-bb96-fbe80dbe23e3")
        self.wms.xml_backup_file = SimpleUploadedFile(
            'capabilitites.xml', WMS_CAPS_PATH.read_bytes())
        self.wms.save()
        self.layer = Layer.objects.filter(service=self.wms).first()

    # -- row: unchanged capabilities --------------------------------------

    def test_an_unchanged_run_builds_no_candidate_and_hands_the_step_over(
            self):
        """Capabilities byte-identical to the stored document decide
        NO_UPDATE_NEEDED: no request but the capabilities read, no candidate
        parse - and the metadata step is handed over anyway (#1274), because
        the advertised ISO documents may have changed independently."""
        job = WebMapServiceUpdateJob.objects.create(service=self.wms)

        with patch.object(Session, 'send',
                          side_effect=[_caps_response(WMS_CAPS_PATH)]), \
                patch.object(OGCServiceXmlMapper, 'from_xml') as from_xml, \
                self.captureOnCommitCallbacks(execute=True):
            job.update()

        job.refresh_from_db()
        self.assertEqual(job.status,
                         UpdateJobStatusEnum.NO_UPDATE_NEEDED.value)
        from_xml.assert_not_called()
        self.assertIsNone(job.done_at,
                          msg='the run is decided, not over: the metadata '
                              'step still answers (#1274)')
        self.assertTrue(job.still_works)
        self.assertEqual(
            [name for name, _ in self.dispatched],
            [collect_update_metadata.name],
            msg='unchanged capabilities still revalidate the advertised '
                'ISO documents')

    # -- adoption refreshes what the service stores ----------------------

    def test_adoption_stores_the_capabilities_it_published(self):
        """The stored document of the service is the one the update adopted.
        #1044 reads it network-free, #1150 checks its integrity and the next
        update compares against it - all three answer the adopted state only
        if adoption writes it."""
        job = WebMapServiceUpdateJob.objects.create(service=self.wms)
        simple = WMS_SIMPLE_PATH.read_bytes()

        from registry.models.update import \
            WebMapServiceUpdateJob as _J
        orig = _J.adopt_stored_document

        def probe(self):
            cand = self.new_service
            print("DEBUG candidate backup name:",
                  repr(cand.xml_backup_file.name),
                  "bytes:", len(cand.xml_backup))
            orig(self)

        with patch.object(_J, 'adopt_stored_document', probe), \
                patch.object(Session, 'send',
                             side_effect=[_caps_response(WMS_SIMPLE_PATH)]):
            job.update()
            job.metadata_step_completed()

        job.refresh_from_db()
        self.assertEqual(job.status, UpdateJobStatusEnum.UPDATED.value)
        self.wms.refresh_from_db()
        self.assertTrue(
            self.wms.document_equals(simple),
            msg='the stored capabilities document names the adopted state')

    def test_the_next_run_of_the_adopted_document_stages_no_candidate(self):
        """The measurement of the issue, per cycle of a service that settled:
        one capabilities request, zero candidate parses, NO_UPDATE_NEEDED.
        Before the stored document was refreshed on adoption, every cycle
        after the first change re-fetched, re-parsed and re-persisted a whole
        candidate forever, because the stored document still showed the
        document of the registration."""
        job = WebMapServiceUpdateJob.objects.create(service=self.wms)
        with patch.object(Session, 'send',
                          side_effect=[_caps_response(WMS_SIMPLE_PATH)]):
            job.update()
            job.metadata_step_completed()

        second = WebMapServiceUpdateJob.objects.create(service=self.wms)
        with patch.object(Session, 'send',
                          side_effect=[_caps_response(WMS_SIMPLE_PATH)]) \
                as send, \
                patch.object(OGCServiceXmlMapper, 'from_xml') as from_xml, \
                self.captureOnCommitCallbacks(execute=True):
            second.update()

        second.refresh_from_db()
        self.assertEqual(second.status,
                         UpdateJobStatusEnum.NO_UPDATE_NEEDED.value)
        self.assertEqual(send.call_count, 1,
                         msg='one capabilities request, nothing else')
        from_xml.assert_not_called()
        self.assertFalse(
            WebMapService.objects.filter(
                update_candidate_of=self.wms).exists())

    # -- row: changed advertised URL ---------------------------------------

    def test_an_update_publishes_the_metadata_references_it_advertises(self):
        """A changed capabilities document may advertise different metadata
        links. The published service then advertises exactly the new list -
        the rows the candidate carried describe the published elements, the
        rows of the registration which the new document does not name are
        taken back. Without this the update's metadata step would collect
        the stale URLs of the registration and lose the updated external
        documents (#1413); the records of the old links and their relations
        stay until the supersede bookkeeping of #1261 answers them."""
        service_ref = WebMapServiceRemoteMetadata.objects.create(
            link=OLD_WMS_LINK, describes=self.wms)
        layer_ref = LayerRemoteMetadata.objects.create(
            link='http://metadata.example.org/registered-layer.xml',
            describes=self.layer)
        job = WebMapServiceUpdateJob.objects.create(service=self.wms)

        with patch.object(
                Session, 'send',
                side_effect=[_caps_response(
                    WMS_SIMPLE_PATH,
                    replace=(OLD_WMS_LINK_XML, NEW_WMS_LINK_XML))]):
            job.update()

        job.refresh_from_db()
        self.assertEqual(job.status, UpdateJobStatusEnum.UPDATED.value)
        links = {ref.link for ref in advertised_references(self.wms)}
        self.assertEqual(links, {NEW_WMS_LINK},
                         msg='the published service advertises exactly what '
                             'the adopted document advertises')
        self.assertFalse(
            WebMapServiceRemoteMetadata.objects.filter(
                pk=service_ref.pk).exists(),
            msg='the stale service reference of the registration is gone')
        self.assertFalse(
            LayerRemoteMetadata.objects.filter(
                pk=layer_ref.pk).exists(),
            msg='a reference the new document does not advertise is taken '
                'back with the update')
        moved = WebMapServiceRemoteMetadata.objects.get(link=NEW_WMS_LINK)
        self.assertEqual(moved.describes, self.wms,
                         msg='the candidate row describes the published '
                             'service')


class WfsRefreshPolicyTests(UpdateHarness):
    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wfs.json"]

    def setUp(self):
        super().setUp()
        self.wfs = WebFeatureService.objects.get(
            pk="9cc4889d-0cd4-4c3b-8975-58de6d30db41")
        self.wfs.xml_backup_file = SimpleUploadedFile(
            'capabilitites.xml', WFS_CAPS_PATH.read_bytes())
        self.wfs.save()
        self.featuretype = FeatureType.objects.filter(
            service=self.wfs).first()

    def test_adoption_refreshes_document_and_advertised_references(self):
        """The same policy for the WFS: after adoption the next run of the
        same bytes needs no candidate, and the feature types advertise the
        links the adopted document names - here: the same URL for every
        feature type, replaced under a new href."""
        simple = WFS_SIMPLE_PATH.read_text().replace(
            OLD_WFS_LINK, NEW_WFS_LINK)
        old_refs = [
            FeatureTypeRemoteMetadata.objects.create(
                link=OLD_WFS_LINK, describes=featuretype)
            for featuretype in FeatureType.objects.filter(service=self.wfs)]
        WebFeatureServiceRemoteMetadata.objects.create(
            link='http://metadata.example.org/registered-wfs.xml',
            describes=self.wfs)
        job = WebFeatureServiceUpdateJob.objects.create(service=self.wfs)

        with patch.object(
                Session, 'send',
                side_effect=[MockResponse(
                    status_code=status.HTTP_200_OK, content=simple)]):
            job.update()
            job.metadata_step_completed()

        job.refresh_from_db()
        self.assertEqual(job.status, UpdateJobStatusEnum.UPDATED.value)
        self.wfs.refresh_from_db()
        self.assertTrue(
            self.wfs.document_equals(simple.encode("UTF-8")),
            msg='the stored document shows the adopted state')
        refs = advertised_references(self.wfs)
        self.assertCountEqual(
            {ref.link for ref in refs}, {NEW_WFS_LINK},
            msg='only what the adopted document advertises is advertised')
        for ref in refs:
            self.assertTrue(
                isinstance(ref, FeatureTypeRemoteMetadata),
                msg='the service-level reference the new document does not '
                    'advertise is taken back')
        self.assertEqual(len(refs), 4,
                         msg='every feature type keeps its own reference '
                             'row for the shared link')
        self.assertFalse(
            FeatureTypeRemoteMetadata.objects.filter(
                pk__in=[ref.pk for ref in old_refs]).exists())

        second = WebFeatureServiceUpdateJob.objects.create(service=self.wfs)
        with patch.object(
                Session, 'send',
                side_effect=[MockResponse(
                    status_code=status.HTTP_200_OK, content=simple)]) \
                as send, \
                patch.object(OGCServiceXmlMapper, 'from_xml') as from_xml, \
                self.captureOnCommitCallbacks(execute=True):
            second.update()
        second.refresh_from_db()
        self.assertEqual(second.status,
                         UpdateJobStatusEnum.NO_UPDATE_NEEDED.value)
        self.assertEqual(send.call_count, 1)
        from_xml.assert_not_called()
