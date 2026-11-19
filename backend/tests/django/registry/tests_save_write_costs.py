"""What the custom save paths pay per write (#1482).

Three save paths decided more than they needed to read:

* ``OgcService.save`` and ``Layer.save`` compared the old ``is_active``
  with the new one by loading the **whole old row** - the metadata text
  and the document reference of a service, the bounding box geometry of a
  layer - before every single update save, for a boolean comparison. The
  reads are single-column now; the cascade triggers they guard are
  pinned to fire exactly as before, in both directions.
* ``FeatureType.save`` wrote ``is_active=True`` onto its service on every
  active update save, whether the service needed it or not. The UPDATE
  matches inactive rows only now: the activation still happens exactly
  once, the no-op of every further save stops being a write.
* ``ServiceHistoricalRecords`` asked ``instance.service`` which service an
  element belongs to, per audit row of every harvested element - loading
  the whole service row each time. A service the caller already holds is
  used from the field cache (no query at all) and the skip question
  otherwise goes to the one column of the service row it is about.

The assertions are about the SHAPE of the SQL around a save (which columns
a read names, whether a write runs at all); the observable state each path
leaves behind is asserted unchanged next to it. Query-shape assertions are
scoped to one row's statements and state, never table-wide.
"""
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from mptt2.models import Tree

from registry.models.metadata import MetadataContact, ReferenceSystem
from registry.models.service import (FeatureType, Layer, WebFeatureService,
                                     WebMapService)


class SingleColumnOldReadTests(TestCase):
    """The is_active comparison reads the flag, not the old row (#1482)."""

    @classmethod
    def setUpTestData(cls):
        contact = MetadataContact.objects.create(name='Save cost contact')
        cls.wms = WebMapService.objects.create(
            title='Save cost wms', version=130, origin=1,
            service_url='https://example.com/wms/costs',
            metadata_contact=contact, service_contact=contact)
        cls.layer = Layer.objects.create(
            service=cls.wms, title='Save cost layer',
            identifier='save-cost-layer',
            mptt_tree=Tree.objects.create(), mptt_lft=1, mptt_rgt=2,
            mptt_depth=0)

    def test_a_service_update_save_reads_only_the_flag_it_compares(self):
        """A rename save may not pay for the row's text and document.

        The pre-save read of the old row selected every column of the
        service - the metadata text and the capabilities document
        reference included - to compare one boolean. The read is pinned
        to name that column and no wide one.
        """
        service = WebMapService.objects.get(pk=self.wms.pk)
        service.title = 'renamed, no activation involved'
        with CaptureQueriesContext(connection) as queries:
            service.save()

        reads = [q['sql'] for q in queries.captured_queries
                 if q['sql'].startswith('SELECT')
                 and '"registry_webmapservice"' in q['sql']]
        self.assertTrue(reads, 'the pre-save read disappeared entirely')
        for sql in reads:
            self.assertNotIn(
                '"title"', sql,
                'a service read still selects the wide columns of the row')
        self.assertTrue(
            any('"is_active"' in sql for sql in reads),
            'the pre-save no longer reads the one column it compares')

    def test_the_activation_cascade_of_a_service_fires_both_ways_still(self):
        """The cheaper read must not move the trigger it guards."""
        service = WebMapService.objects.get(pk=self.wms.pk)
        service.is_active = True
        service.save()
        self.assertTrue(
            Layer.objects.filter(pk=self.layer.pk)
            .values_list('is_active', flat=True).get(),
            'activating the service no longer activates its layers')

        service.is_active = False
        service.save()
        self.assertFalse(
            Layer.objects.filter(pk=self.layer.pk)
            .values_list('is_active', flat=True).get(),
            'deactivating the service no longer deactivates its layers')

    def test_a_layer_update_save_reads_only_the_flag(self):
        """Same for the layer, where the wide column is the geometry."""
        layer = Layer.objects.get(pk=self.layer.pk)
        layer.title = 'renamed layer'
        with CaptureQueriesContext(connection) as queries:
            layer.save()

        reads = [q['sql'] for q in queries.captured_queries
                 if q['sql'].startswith('SELECT')
                 and '"registry_layer"' in q['sql']]
        self.assertTrue(reads, 'the pre-save read disappeared entirely')
        for sql in reads:
            self.assertNotIn(
                '"bbox_lat_lon"', sql,
                'a layer read still selects the bounding box geometry')
        self.assertTrue(
            any('"is_active"' in sql for sql in reads),
            'the pre-save no longer reads the one column it compares')

    def test_layer_activation_still_cascades_to_the_family_and_service(self):
        """The trigger of the layer side, unchanged by the cheaper read."""
        layer = Layer.objects.get(pk=self.layer.pk)
        layer.is_active = True
        layer.save()

        self.assertTrue(
            Layer.objects.filter(pk=self.layer.pk)
            .values_list('is_active', flat=True).get(),
            'the layer family no longer follows the activation')
        self.assertTrue(
            WebMapService.objects.filter(pk=self.wms.pk)
            .values_list('is_active', flat=True).get(),
            'activating a layer no longer activates its service')


class FeatureTypeActivationWriteTests(TestCase):
    """Activating a feature type writes its service once, not per save (#1482)."""

    @classmethod
    def setUpTestData(cls):
        contact = MetadataContact.objects.create(name='Feature type contact')
        cls.wfs = WebFeatureService.objects.create(
            title='Save cost wfs', version=200, origin=1,
            service_url='https://example.com/wfs/costs',
            metadata_contact=contact, service_contact=contact)
        cls.reference = ReferenceSystem.objects.create()
        cls.feature_type = FeatureType.objects.create(
            service=cls.wfs, title='Active from the start',
            identifier='save-cost-ft',
            default_reference_system=cls.reference, is_active=True)

    def test_creating_an_active_feature_type_writes_no_service(self):
        """The creation path never touched the service - stays so."""
        with CaptureQueriesContext(connection) as queries:
            FeatureType.objects.create(
                service=self.wfs, title='second', identifier='save-cost-ft-2',
                default_reference_system=self.reference, is_active=True)

        self.assertFalse(
            any(q['sql'].startswith('UPDATE "registry_webfeatureservice"')
                for q in queries.captured_queries),
            'creating a feature type started writing the service')
        self.assertFalse(
            WebFeatureService.objects.filter(pk=self.wfs.pk)
            .values_list('is_active', flat=True).get())

    def test_the_service_is_activated_once_and_never_written_again(self):
        """The first update save activates; further saves do not write.

        The old UPDATE matched the service row unconditionally, so every
        save of every active feature type wrote the service table again.
        Asking the UPDATE to match only inactive rows keeps the one real
        activation and drops every no-op write behind it.
        """
        feature_type = FeatureType.objects.get(pk=self.feature_type.pk)
        with CaptureQueriesContext(connection) as queries:
            feature_type.title = 'renamed once'
            feature_type.save()
        self.assertTrue(
            any(q['sql'].startswith('UPDATE "registry_webfeatureservice"')
                for q in queries.captured_queries),
            'the activation of an inactive service went missing')
        self.assertTrue(
            WebFeatureService.objects.filter(pk=self.wfs.pk)
            .values_list('is_active', flat=True).get())

        again = FeatureType.objects.get(pk=self.feature_type.pk)
        with CaptureQueriesContext(connection) as queries:
            again.title = 'renamed twice'
            again.save()
        self.assertFalse(
            any(q['sql'].startswith('UPDATE "registry_webfeatureservice"')
                for q in queries.captured_queries),
            'an already active service was written by a save again')
        self.assertTrue(
            WebFeatureService.objects.filter(pk=self.wfs.pk)
            .values_list('is_active', flat=True).get())


class CandidateAuditSkipTests(TestCase):
    """The audit skip of candidate elements reads less, skips the same."""

    @classmethod
    def setUpTestData(cls):
        contact = MetadataContact.objects.create(name='Candidate contact')
        cls.wms = WebMapService.objects.create(
            title='Published side', version=130, origin=1,
            service_url='https://example.com/wms/published',
            metadata_contact=contact, service_contact=contact)
        cls.candidate = WebMapService.objects.create(
            title='Update candidate', version=130, origin=1,
            service_url='https://example.com/wms/published',
            update_candidate_of=cls.wms,
            metadata_contact=contact, service_contact=contact)
        cls.candidate_layer = Layer.objects.create(
            service=cls.candidate, title='Candidate layer',
            identifier='candidate-layer',
            mptt_tree=Tree.objects.create(), mptt_lft=1, mptt_rgt=2,
            mptt_depth=0)
        cls.published_layer = Layer.objects.create(
            service=cls.wms, title='Published layer',
            identifier='published-layer',
            mptt_tree=Tree.objects.create(), mptt_lft=1, mptt_rgt=2,
            mptt_depth=0)

    def test_a_service_the_caller_holds_is_never_read_again_for_the_skip(self):
        """select_related'd service: the skip question is already answered.

        The old code asked ``instance.service`` regardless of what the
        caller had loaded - a second, per-audit-row read of the whole
        service. With the service in the field cache the save answers
        without a single query against the service table.
        """
        layer = Layer.objects.select_related('service').get(
            pk=self.candidate_layer.pk)
        with CaptureQueriesContext(connection) as queries:
            layer.title = 'renamed candidate'
            layer.save()

        self.assertFalse(
            any('"registry_webmapservice"' in q['sql']
                for q in queries.captured_queries),
            'the audit skip read the service table despite the cached one')
        self.assertEqual(
            Layer.change_log.model.objects.filter(id=layer.pk).count(), 0,
            'an element of an update candidate grew an audit row')

    def test_without_the_cache_the_skip_asks_for_the_one_column(self):
        """The narrow question, not the wide row, on the cold path too."""
        layer = Layer.objects.get(pk=self.candidate_layer.pk)
        with CaptureQueriesContext(connection) as queries:
            layer.title = 'renamed candidate, cold'
            layer.save()

        service_reads = [
            q['sql'] for q in queries.captured_queries
            if q['sql'].startswith('SELECT')
            and '"registry_webmapservice"' in q['sql']]
        self.assertTrue(
            service_reads,
            'the skip question went missing on the uncached path')
        for sql in service_reads:
            self.assertIn(
                '"update_candidate_of_id"', sql,
                'the service read is no longer the single-column question')
            self.assertNotIn(
                '"title"', sql,
                'the service read loads the wide row again')
        self.assertEqual(
            Layer.change_log.model.objects.filter(id=layer.pk).count(), 0,
            'an element of an update candidate grew an audit row')

    def test_published_elements_keep_writing_their_audit_rows(self):
        """The control the skip needs: the published side still is audited.

        Counted against one row only - three writes to this layer, three
        audit rows, on both the cached and the uncached save path.
        """
        cached = Layer.objects.select_related('service').get(
            pk=self.published_layer.pk)
        cached.title = 'renamed cached'
        cached.save()

        uncached = Layer.objects.get(pk=self.published_layer.pk)
        uncached.title = 'renamed uncached'
        uncached.save()

        self.assertEqual(
            Layer.change_log.model.objects.filter(
                id=self.published_layer.pk).count(), 3,
            'the published element lost an audit row (create + two saves)')
