"""The epic #824 closure scenario at task level: MrMap harvests its own /csw.

The acceptance asks that "a second MrMap harvesting this /csw collects the
application records end-to-end". The two-instance deployment itself can not
run inside one test database; what this module proves instead is the complete
data loop a deployment performs, with both halves taken from production code:

*   the publisher half is THIS repository's endpoint: three records -- one of
    each kind, carrying the real #825 spike documents -- answer a KVP
    ``GetRecords`` of all three kinds, and the response bytes are the only
    thing that travels;
*   the harvester half deletes the publisher's records (the second instance
    starts empty), stores every delivered document the way the harvesting
    client stores a downloaded record, and runs the real import task of #827
    over it -- the mapping, persistence and ``HarvestedMetadataRelation``
    bookkeeping are the production ones, not a re-enactment.

If the endpoint served a kind the client could not import, or the importer
could not digest what the endpoint ships, the run below would not find the
record on the other side. The response shape itself is pinned in
``test_csw_queryables.py`` (paging over the mixed set) and
``test_csw_get_record_by_id.py``; the import side is
``tests/django/registry/tasks/tests_harvest_application_records.py``. This
module welds the two ends together.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from lxml import etree

from registry.enums.harvesting import CollectingStatenEnum as State
from registry.enums.harvesting import HarvestingPhaseEnum as Phase
from registry.enums.metadata import MetadataOriginEnum
from registry.models.harvest import (HarvestedMetadataRelation, HarvestingJob,
                                     TemporaryMdMetadataFile)
from registry.models.metadata import (ApplicationMetadataRecord,
                                      DatasetMetadataRecord, MetadataContact,
                                      ServiceMetadataRecord)
from registry.models.service import CatalogueService
from registry.ows_lib.xml.consts import NAMESPACE_LOOKUP
from registry.tasks.harvest import import_md_metadata_file

ISO_DATA = Path(__file__).parent / 'test_data/iso_metadata'

#: the CSW 2.0.2 capabilities document the harvester's catalogue stores as its
#: own -- the import derives each record's origin_url from its operations
CAPABILITIES = Path(__file__).parent / 'test_data/capabilities/csw/2.0.2.xml'

#: the three #825 spike documents, one per record kind
PUBLISHED = (
    (DatasetMetadataRecord, 'dataset.xml', 'de.dwd.geoserver.fach.RBSN_FF'),
    (ServiceMetadataRecord, 'service.xml',
     'ee065040-1015-44c7-839e-e8e349c74bbd'),
    (ApplicationMetadataRecord, 'gdi-bw-04.xml',
     '78538593-0e19-a5b7-c64a-756898eac073'),
)

GET_RECORDS = {
    'SERVICE': 'CSW',
    'REQUEST': 'GetRecords',
    'VERSION': '2.0.2',
    # what the harvesting client asks for: Table 65's full view, so the
    # answer carries the documents the import has to digest unchanged
    'ElementSetName': 'full',
}

ALL_KINDS = ("type = 'dataset' OR type = 'service' OR type = 'application'")

SEARCH_RESULTS = '/csw:GetRecordsResponse/csw:SearchResults/*'

CSW_NS = {'csw': NAMESPACE_LOOKUP['csw_2_0_2']}


class SecondMrMapHarvestsThisCswTest(TestCase):
    """Publish every kind, harvest the answer, find every kind again."""

    def setUp(self):
        # the import writes files; keep them out of the checkout
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        settings = override_settings(MEDIA_ROOT=media.name)
        settings.enable()
        self.addCleanup(settings.disable)

        self.contact = MetadataContact.objects.create(
            name='CSW roundtrip contact')
        for model, document, identifier in PUBLISHED:
            fields = {
                'metadata_contact': self.contact,
                'code_space': 'de.roundtrip.',
                'code': identifier,
                'file_identifier': identifier,
            }
            if model is DatasetMetadataRecord:
                fields['dataset_contact'] = self.contact
            elif model is ApplicationMetadataRecord:
                fields['application_contact'] = self.contact
            model.objects.create(
                xml_backup_file=SimpleUploadedFile(
                    document, (ISO_DATA / document).read_bytes(),
                    content_type='application/xml'),
                **fields)

    def test_every_published_kind_survives_the_harvest_import(self):
        # -- the publisher answers one all-kinds GetRecords --
        response = self.client.get('/csw', {
            **GET_RECORDS,
            'resultType': 'results',
            'CONSTRAINTLANGUAGE': 'CQL_TEXT',
            'Constraint': ALL_KINDS,
        })
        self.assertEqual(response.status_code, 200, response.content)
        delivered = [
            etree.tostring(element) for element in etree.fromstring(
                response.content).xpath(SEARCH_RESULTS, namespaces=CSW_NS)]
        self.assertEqual(3, len(delivered), response.content)

        # -- the second instance begins: its own catalogue, an empty registry --
        for model, _, _ in PUBLISHED:
            model.objects.all().delete()
        self.assertFalse(ApplicationMetadataRecord.objects.exists())

        catalogue = CatalogueService.objects.create(
            title='Instance A catalogue', version=202, origin=1,
            service_url='https://instance-a.example.org/csw',
            metadata_contact=self.contact, service_contact=self.contact)
        # the import asks the catalogue's client for the origin_url of each
        # record -- the client reads the service's stored capabilities, the
        # same CSW 2.0.2 document the #827 harness stores on its catalogue
        catalogue.xml_backup_file = SimpleUploadedFile(
            'capabilities.xml', CAPABILITIES.read_bytes())
        catalogue.save()
        job = HarvestingJob.objects.create(
            service=catalogue, total_records=len(delivered),
            phase=Phase.RECORDS_TO_DB)

        # -- every delivered document takes the client's storage path and the
        # real import task of #827 --
        for document in delivered:
            file = TemporaryMdMetadataFile.objects.create(
                job=job, requested_url='https://instance-a.example.org/csw',
                download_duration=None)
            file.md_metadata_file.save(
                'md_metadata.xml', ContentFile(document))
            import_md_metadata_file(file.pk)

        # -- all three kinds landed, the application record among them --
        for model, _, identifier in PUBLISHED:
            if not model.objects.filter(file_identifier=identifier).exists():
                # the import stays loud: an undigested document names itself
                # on the stored file, and the refusal without that report
                # leaves the roundtrip undiagnosable
                errors = list(TemporaryMdMetadataFile.objects.filter(
                    job=job, has_import_error=True).values_list(
                        'import_error', flat=True))
                self.fail(
                    f'{model.__name__} {identifier} did not survive the '
                    f'harvest; import errors: {errors}')

        application = ApplicationMetadataRecord.objects.get(
            file_identifier='78538593-0e19-a5b7-c64a-756898eac073')
        # provenance and bookkeeping of a harvested record, like the two
        # known types get them (#827)
        self.assertEqual(MetadataOriginEnum.CATALOGUE.value, application.origin)
        relation = HarvestedMetadataRelation.objects.get(
            harvesting_job=job, application_metadata_record=application)
        self.assertEqual(State.NEW, relation.collecting_state)
        self.assertIsNone(relation.dataset_metadata_record_id)
        self.assertIsNone(relation.service_metadata_record_id)

    def test_get_record_by_id_answers_the_harvested_document_by_identifier(self):
        """The identifier which travels is the identifier which opens the record.

        The client pages GetRecords for the fileIdentifiers and fetches the
        documents by GetRecordById; both answers must agree, or the second
        instance imports documents the first never promised.
        """
        listing = etree.fromstring(self.client.get('/csw', {
            **GET_RECORDS,
            'resultType': 'results',
            'CONSTRAINTLANGUAGE': 'CQL_TEXT',
            'Constraint': "type = 'application'",
        }).content)
        [identifier] = listing.xpath(
            '//gmd:fileIdentifier/gco:CharacterString/text()',
            namespaces={'gmd': NAMESPACE_LOOKUP['gmd'],
                        'gco': NAMESPACE_LOOKUP['gco']})
        self.assertEqual(
            '78538593-0e19-a5b7-c64a-756898eac073', identifier)

        by_id = etree.fromstring(self.client.get('/csw', {
            'SERVICE': 'CSW', 'REQUEST': 'GetRecordById',
            'VERSION': '2.0.2', 'Id': identifier,
        }).content)
        documents = by_id.xpath(
            '//*[local-name()="GetRecordByIdResponse"]/*'
            '[local-name()="MD_Metadata"]')
        self.assertEqual(1, len(documents), by_id)
        self.assertEqual(
            identifier, documents[0].xpath(
                './/*[local-name()="fileIdentifier"]'
                '//*[local-name()="CharacterString"]/text()')[0])
