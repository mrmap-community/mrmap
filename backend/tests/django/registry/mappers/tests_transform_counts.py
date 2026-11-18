"""How often importing one metadata document maps, transforms and serializes.

#1415 reviews the parse -> map -> persist -> couple stages of an imported ISO
19139 record for semantically identical repeated XML work. The inventory of
what those stages cost is
``docs/source/development/metadata-transform-inventory.rst``; this module is
its deterministic half: the transformations are counted at the seams where the
code performs them, so a regression which reintroduces a redundant
full-document transform fails here and not in a production harvest.

What the counts pin down:

* ``MDMetadataXmlMapper.from_xml`` reads a document once - the
  serialize-and-reparse detach which used to run on every import only cuts a
  node out of a wrapper document, which is what it is for (#1415);
* one import serializes the document backup only when a record is actually
  written: a created or republished record pays one serialization, an
  unchanged re-harvest pays none (the write counts of #858 stand, this module
  counts the transforms beside them);
* the bucket check of a catalogue run reads the ``hierarchyLevel`` answer the
  mapping already detected instead of running the same traversal a second
  time (#827's post-filter);
* mapping scales with files, not with records: independent harvest records
  keep their own import, provenance and bookkeeping, and the N deliveries of
  one shared advertised document map N times - a cross-run cache which could
  answer them once must not grow here. The database work a repeated coupling
  costs (lookup upserts, M2M sets, supersede queries) is #1392's question;
* the parsed instances of one import leave the process-global cache with the
  import, instead of being held there until their TTL (#1028 bounded them,
  this releases them).
"""

import contextlib
import copy
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import Count, F
from django.test import SimpleTestCase, TestCase, override_settings
from lxml import etree
from registry.enums.harvesting import HarvestingPhaseEnum as Phase
from registry.enums.metadata import MetadataOriginEnum
from registry.mappers.cache import GlobalXmlCache, LocalXmlCache
from registry.mappers.factory import MDMetadataXmlMapper
from registry.mappers.xml_mapper import XmlMapper
from registry.models.harvest import (HarvestedMetadataRelation, HarvestingJob,
                                     TemporaryMdMetadataFile)
from registry.models.metadata import (DatasetMetadataRecord,
                                      LayerRemoteMetadata, MetadataContact,
                                      MetadataRelation,
                                      WebMapServiceRemoteMetadata,
                                      couple_document)
from registry.models.service import CatalogueService, Layer, WebMapService

ISO_DATA = Path(__file__).parent / '../../test_data/iso_metadata'
DATASET_XML = (ISO_DATA / 'dataset.xml').read_bytes()
# a real catalogue sample which is stored the way a harvest stores a record:
# the MD_Metadata element is the document's root
STANDALONE_SAMPLE = ISO_DATA / 'gdi-de-01.xml'
CSW_CAPABILITIES = ISO_DATA.parent / 'capabilities/csw/2.0.2.xml'

# the file identifier the dataset sample carries (as in #1261's tests)
FILE_IDENTIFIER = 'de.dwd.geoserver.fach.RBSN_FF'
LINK = 'http://example.gov/md/shared'


def as_standalone_document(content=DATASET_XML):
    """The dataset record as the harvesting stores it per file.

    ``HarvestingJob._store_page`` cuts every ``MD_Metadata`` out of the
    answered page and stores it as its own document, and the filesystem
    import and the registration download store the same shape - so the
    imported file normally *is* the record's document (#1415).
    """
    node = etree.fromstring(content).xpath(
        "//*[local-name()='MD_Metadata']")[0]
    return etree.tostring(
        node, xml_declaration=True, pretty_print=True, encoding='UTF-8')


STANDALONE = as_standalone_document()


class CountedEtree:
    """The lxml handle of the mapper factory, with transformations counted.

    The factory parses the document and - for a node which has to be cut out
    of a bigger one - serializes and reparses it through this module
    attribute; swapping it counts the transformations exactly where the
    mapper performs them.
    """

    def __init__(self):
        self.parses = 0
        self.serializations = 0

    def fromstring(self, *args, **kwargs):
        self.parses += 1
        return etree.fromstring(*args, **kwargs)

    def tostring(self, *args, **kwargs):
        self.serializations += 1
        return etree.tostring(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(etree, name)


class TransformationCounter:
    """Counts the transformations of the code under test.

    ``count_transformations`` counts the parses and detach serializations of
    ``from_xml``, ``count_backup_serializations`` the document backup of the
    record persistence and ``count_level_detection`` the hierarchyLevel
    traversal; ``reset_counts`` zeroes what is counted for a second phase.
    """

    def count_transformations(self):
        self.etree = CountedEtree()
        stack = contextlib.ExitStack()
        stack.enter_context(
            patch('registry.mappers.factory.etree', self.etree))
        self.addCleanup(stack.close)

    def count_backup_serializations(self):
        """Counts ``serialize_document`` calls; answers the list of calls."""
        self.serialize_calls = []
        real = XmlMapper.serialize_document

        def counting(mapper_self, *args, **kwargs):
            self.serialize_calls.append(1)
            return real(mapper_self, *args, **kwargs)

        stack = contextlib.ExitStack()
        stack.enter_context(
            patch.object(XmlMapper, 'serialize_document', counting))
        self.addCleanup(stack.close)

    def count_level_detection(self):
        """Counts the hierarchyLevel detections; answers the mock."""
        real = MDMetadataXmlMapper._detect_hierarchy_level
        detect = MagicMock(side_effect=real)
        stack = contextlib.ExitStack()
        stack.enter_context(patch.object(
            MDMetadataXmlMapper, '_detect_hierarchy_level', detect))
        self.addCleanup(stack.close)
        return detect

    def reset_counts(self):
        self.etree.parses = 0
        self.etree.serializations = 0
        del self.serialize_calls[:]


class FromXmlTransformCountTest(TransformationCounter, TestCase):
    """What reading one document into mappers costs the lxml machinery."""

    def test_a_standalone_document_is_read_by_one_parse_and_no_serialization(
            self):
        """the shape of every stored harvest file and every downloaded
        advertised document: the node is the document, so cutting it out
        would only pay for a structurally identical tree (#1415)"""
        self.count_transformations()

        mappers = MDMetadataXmlMapper.from_xml(STANDALONE)

        self.assertEqual(len(mappers), 1)
        self.assertEqual((self.etree.parses, self.etree.serializations),
                         (1, 0),
                         'the detach copy must only run for a node which '
                         'needs to be cut out of a bigger document')

    def test_a_catalogue_sample_stored_as_its_own_document_costs_one_parse(
            self):
        """not a constructed shape but a real sample of the test data, the way
        the filesystem import hands it in"""
        self.count_transformations()

        mappers = MDMetadataXmlMapper.from_xml(
            STANDALONE_SAMPLE.read_bytes())

        self.assertEqual(len(mappers), 1)
        self.assertEqual((self.etree.parses, self.etree.serializations), (1, 0))

    def test_the_shared_tree_maps_the_same_record(self):
        """skipping the copy must not change what the traversal answers: the
        file identifier of the record the document names"""
        self.count_transformations()
        mapper = MDMetadataXmlMapper.from_xml(STANDALONE)[0]

        parsed = mapper.xml_to_django()[0]

        self.assertEqual(parsed.file_identifier, FILE_IDENTIFIER)

    def test_a_node_below_a_wrapper_is_still_cut_into_its_own_tree(self):
        """paths and xml backup are those of one standalone document, which a
        node below a search-response wrapper only gets by the copy"""
        self.count_transformations()

        mappers = MDMetadataXmlMapper.from_xml(DATASET_XML)

        self.assertEqual(len(mappers), 1)
        self.assertEqual((self.etree.parses, self.etree.serializations),
                         (2, 1))

    def test_every_node_of_a_several_record_document_gets_its_own_tree(self):
        """one parse for the document plus one serialize and one parse per
        node below it - the skip is for the one root node only"""
        wrapper = etree.Element('records')
        node = etree.fromstring(DATASET_XML).xpath(
            "//*[local-name()='MD_Metadata']")[0]
        wrapper.append(copy.deepcopy(node))
        wrapper.append(copy.deepcopy(node))
        self.count_transformations()

        mappers = MDMetadataXmlMapper.from_xml(
            etree.tostring(wrapper, encoding='utf-8'))

        self.assertEqual(len(mappers), 2)
        self.assertEqual((self.etree.parses, self.etree.serializations),
                         (3, 2))

    def test_the_mapper_carries_the_kind_the_document_names(self):
        """the detection answer travels with the mapper for the bucket check
        of an import; a forced kind never pretends to be that answer"""
        self.count_transformations()

        detected = MDMetadataXmlMapper.from_xml(DATASET_XML)[0].hierarchy_level
        forced = MDMetadataXmlMapper.from_xml(
            STANDALONE, hierarchy_level='dataset')[0].hierarchy_level

        self.assertEqual(detected, 'dataset')
        self.assertIsNone(forced)


class ImportHarness(TransformationCounter):
    """One stored document, imported the way the harvesting task does it.

    Nothing is mocked but the counters: the document is stored like a
    downloaded record and imported by the code the import task calls.
    """

    def setUp(self):
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        settings = override_settings(MEDIA_ROOT=media.name)
        settings.enable()
        self.addCleanup(settings.disable)
        self.count_transformations()
        self.count_backup_serializations()

    def new_run(self, service=None, **record_type_flags):
        job = HarvestingJob(
            total_records=1, phase=Phase.RECORDS_TO_DB, service=service,
            **record_type_flags)
        HarvestingJob.objects.bulk_create([job])
        return job

    def stored_file(self, run, content=STANDALONE):
        file = TemporaryMdMetadataFile(
            job=run, requested_url='https://example.com/csw?page=1')
        file.md_metadata_file.save(
            'record.xml', ContentFile(content), save=False)
        TemporaryMdMetadataFile.objects.bulk_create([file])
        return file

    def import_file(self, run, content=STANDALONE):
        return self.stored_file(run, content).md_metadata_file_to_db()


class CatalogueHarness(ImportHarness):
    """The same import, with a catalogue behind the run.

    Only a run with a service behind it is a bucket delivery: without one the
    post-filter of #827 is skipped before it asks the document anything.
    """

    def setUp(self):
        super().setUp()
        contact = MetadataContact.objects.create(name='Transform count contact')
        self.catalogue = CatalogueService(
            id='22222222-1111-1111-1111-111111111111',
            title='Transform count catalogue', version=202, origin=1,
            service_url='https://example.com/csw',
            metadata_contact=contact, service_contact=contact)
        CatalogueService.objects.bulk_create([self.catalogue])
        self.catalogue.xml_backup_file = SimpleUploadedFile(
            'capabilities.xml', CSW_CAPABILITIES.read_bytes())
        self.catalogue.save()


class ImportTransformCountTest(ImportHarness, TestCase):
    """What one file import costs the transform machinery."""

    def test_importing_a_new_record_costs_one_parse_and_one_serialization(
            self):
        """one read of the document and one backup for the written record -
        the record row itself is still written exactly once (#858 stands)"""
        record, updated, existed = self.import_file(self.new_run())[0]

        self.assertFalse(updated)
        self.assertFalse(existed)
        self.assertEqual((self.etree.parses, self.etree.serializations),
                         (1, 0))
        self.assertEqual(len(self.serialize_calls), 1)

    def test_an_unchanged_reharvest_costs_no_serialization(self):
        """the catalogue answered the same document again: the record is not
        written, so there is no backup to serialize for it - the unchanged
        path is a documented no-change path (#1415)"""
        self.import_file(self.new_run())
        self.reset_counts()

        _, updated, existed = self.import_file(self.new_run())[0]

        self.assertTrue(existed)
        self.assertFalse(updated)
        self.assertEqual((self.etree.parses, self.etree.serializations),
                         (1, 0))
        self.assertEqual(
            self.serialize_calls, [],
            'the whole-document backup was serialized for every re-harvest, '
            'including the ones which wrote nothing')

    def test_a_republished_record_pays_for_a_new_backup(self):
        """a newer date stamp is written, so its backup is serialized - once"""
        self.import_file(self.new_run())
        record = DatasetMetadataRecord.objects.get(
            file_identifier=FILE_IDENTIFIER)
        DatasetMetadataRecord.objects.filter(pk=record.pk).update(
            date_stamp=F('date_stamp') - timedelta(days=1))
        self.reset_counts()

        _, updated, existed = self.import_file(self.new_run())[0]

        self.assertTrue(updated)
        self.assertTrue(existed)
        self.assertEqual(len(self.serialize_calls), 1)

    def test_independent_harvest_records_map_once_per_file(self):
        """one document, two independent harvest records: the mapping does not
        collapse across files - each file carries its own import error ledger,
        its own relation to its run and its own provenance - so it is read
        once per file, while the record stays one and is written and
        serialized once."""
        self.import_file(self.new_run())
        self.import_file(self.new_run())

        self.assertEqual(self.etree.parses, 2,
                         'one read per imported file; fewer could only come '
                         'from a cross-run cache, which must not grow here')
        self.assertEqual(len(self.serialize_calls), 1)
        self.assertEqual(DatasetMetadataRecord.objects.count(), 1)
        record = DatasetMetadataRecord.objects.get()
        self.assertEqual(
            record.origin, MetadataOriginEnum.FILE_SYSTEM_IMPORT.value)
        self.assertEqual(record.origin_url, 'http://localhost')
        self.assertEqual(
            HarvestedMetadataRelation.objects.count(), 2,
            'each run booked its own relation to the record')

    def test_a_failed_import_releases_its_cache_before_the_error_propagates(
            self):
        """the release belongs to the import, not to its outcome: a retried
        file maps the document again under a fresh uuid"""
        file = self.stored_file(self.new_run())
        before = set(GlobalXmlCache._data)

        with patch.object(
                TemporaryMdMetadataFile, '_import_mapped_instance',
                side_effect=ValueError('boom')):
            with self.assertRaises(ValueError):
                file.md_metadata_file_to_db()

        file.refresh_from_db()
        self.assertTrue(file.has_import_error)
        self.assertEqual(set(GlobalXmlCache._data) - before, set())


class BucketDetectionCountTest(CatalogueHarness, TestCase):
    """The hierarchyLevel answer is asked once per document, not twice."""

    def test_the_bucket_check_reads_the_detection_of_the_mapping(self):
        """a catalogue run which requests the document's kind imports it, and
        the hierarchyLevel element is traversed exactly once - by the mapper
        factory, which chose the mapping config with it (#1415)"""
        detect = self.count_level_detection()

        result = self.import_file(self.new_run(service=self.catalogue))

        self.assertEqual(len(result), 1)
        self.assertEqual(detect.call_count, 1,
                         'the import mapped the document and then checked '
                         'its bucket by running the same traversal again')

    def test_a_wrong_bucket_delivery_is_decided_after_one_detection(self):
        """a document the catalogue delivered for a bucket it does not name
        is dropped - and that decision needed one detection, not two (#827)"""
        detect = self.count_level_detection()
        job = self.new_run(service=self.catalogue, harvest_datasets=False)

        result = self.import_file(job)

        self.assertEqual(result, [])
        self.assertEqual(detect.call_count, 1)
        self.assertEqual(DatasetMetadataRecord.objects.count(), 0)
        file = TemporaryMdMetadataFile.objects.get(job=job)
        self.assertIn('hierarchy_level_mismatch', file.import_error)


class SharedReferenceCadenceTest(TransformationCounter, TestCase):
    """One advertised document, every element which points at it.

    The registration story behind #1410: a service and its layers advertise
    the same metadata url; every reference is one delivery which maps its own
    copy - the fetch is shared, the mapping stays per delivery, because no
    cross-run cache may grow here. What a delivery does NOT pay for anymore:
    the detach copy of the document and a whole-document backup serialization
    each. The element count is read from the fixtures, so the cadence
    assertion is deterministic however the fixtures are shaped.
    """

    fixtures = ['test_users.json', 'test_keywords.json', 'test_crs.json',
                'test_wms.json']

    @classmethod
    def setUpTestData(cls):
        # the service the fixture layers hang under, whichever the fixture
        # order answers: the one which carries the most layers
        busiest = (Layer.objects
                   .values('service')
                   .annotate(n=Count('pk'))
                   .order_by('-n').first())
        cls.wms = WebMapService.objects.get(pk=busiest['service'])
        cls.described = [cls.wms] + list(
            Layer.objects.filter(service=cls.wms))
        cls.reference_count = len(cls.described)
        content = STANDALONE.decode('utf-8')
        for element in cls.described:
            model = (WebMapServiceRemoteMetadata
                     if isinstance(element, WebMapService)
                     else LayerRemoteMetadata)
            model.objects.create(
                link=LINK, remote_content=content, describes=element)

    def setUp(self):
        super().setUp()
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        settings = override_settings(MEDIA_ROOT=media.name)
        settings.enable()
        self.addCleanup(settings.disable)
        self.count_transformations()
        self.count_backup_serializations()
        self.assertGreaterEqual(
            self.reference_count, 3,
            'the cadence question needs several elements on one document')

    def collect(self):
        for model in (LayerRemoteMetadata, WebMapServiceRemoteMetadata):
            for reference in model.objects.filter(link=LINK):
                reference.create_metadata_instance()

    def test_shared_references_map_once_each_and_write_one_backup(self):
        """the count of one reference is one mapping - by design across
        deliveries - while the serialization count stays one: the reference
        which creates the record pays for its backup, every coupling which
        decides that nothing changed pays for none"""
        self.collect()

        self.assertEqual(DatasetMetadataRecord.objects.count(), 1)
        record = DatasetMetadataRecord.objects.get()
        self.assertEqual(record.origin_url, LINK)
        self.assertEqual(record.origin,
                         MetadataOriginEnum.CAPABILITIES.value)

        self.assertEqual(self.etree.parses, self.reference_count,
                         'one read per shared reference delivery; fewer '
                         'could only come from a cross-run cache')
        self.assertEqual(self.etree.serializations, 0)
        self.assertEqual(len(self.serialize_calls), 1,
                         'each unchanged coupling serialized a full backup '
                         'of the shared document before #1415')

    def test_every_described_element_keeps_its_own_relation(self):
        """the per-delivery mapping is what keeps the per-element coupling
        whole: record identity by fileIdentifier collapses the record, never
        the relations (#982, #1261)"""
        self.collect()

        record = DatasetMetadataRecord.objects.get()
        self.assertEqual(
            MetadataRelation.objects.filter(
                dataset_metadata=record).count(),
            self.reference_count,
            'the shared mapping must not collapse the per-element couplings')


class CacheReleaseTest(ImportHarness, TestCase):
    """What an import leaves in - and no longer leaves in - global state."""

    def test_a_completed_import_leaves_nothing_in_the_global_cache(self):
        """the parsed instances of a document are read by its own import and
        by nobody later: their keys carry a fresh uuid, so holding them until
        the TTL is holding a parsed copy of everything the worker imported"""
        before = set(GlobalXmlCache._data)

        self.import_file(self.new_run())

        self.assertEqual(
            set(GlobalXmlCache._data) - before, set(),
            'the import left its parsed document in the process-global '
            'cache for the whole TTL')

    def test_a_coupled_document_leaves_nothing_in_the_global_cache(self):
        """the registration seam releases the mapping it just consumed; the
        record it answers rides on the returned objects, not on the cache"""
        before = set(GlobalXmlCache._data)

        record = couple_document(STANDALONE, LINK, None)

        self.assertIsNotNone(record)
        self.assertEqual(
            DatasetMetadataRecord.objects.filter(
                file_identifier=FILE_IDENTIFIER).count(), 1)
        self.assertEqual(set(GlobalXmlCache._data) - before, set())


class LocalCacheReleaseTest(SimpleTestCase):
    """``release`` drops one mapper's entries and nobody else's."""

    def test_release_drops_only_the_entries_of_its_mapper(self):
        cache = LocalXmlCache()
        first = XmlMapper(xml=b'<x/>', mapping={}, cache=cache)
        second = XmlMapper(xml=b'<x/>', mapping={}, cache=cache)
        first.store_to_cache('/a', 'instance-a')
        second.store_to_cache('/b', 'instance-b')

        first.release_cache()

        self.assertIsNone(first.read_from_cache('/a'))
        self.assertEqual(second.read_from_cache('/b'), 'instance-b')
        # the uuid-keyed key list is gone too, not just the instances
        self.assertIsNone(cache.get(first.uuid))
