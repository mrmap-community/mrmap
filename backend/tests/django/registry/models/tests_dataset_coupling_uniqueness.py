"""The coupling of one dataset record to one element is stored once (#1483).

``MetadataRecord.add_metadata_relation`` asserts a coupling with
``get_or_create`` inside ``select_for_update``. The lock answers the case where
the row is already there; for a missing row it locks nothing at all, so two
writers of one couple - the same reference collected twice, a registration
beside an update - both saw no row and both wrote one. The service side of the
same table never had that hole, because its pairs are unique constraints since
their first migration; the dataset side is closed the same way here, with
``is_internal`` in the key: a couple is one row per kind of coupling, because
the imported evidence a capabilities document carried and a curator's internal
coupling of the very same pair are rows of their own by design
(``MetadataRelation.publication_kind``).

``DatasetCouplingUniquenessTests`` pins what the schema answers for the live
model. ``DatasetCouplingDedupeMigrationTest`` travels the real
``MigrationExecutor`` back to the schema before the constraint, writes the
repetitions that schema allowed, and runs the upgrade which removes them before
it refuses them.
"""

from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from mptt2.models import Tree

from registry.enums.metadata import MetadataOriginEnum
from registry.models.metadata import (DatasetMetadataRecord, MetadataContact,
                                      MetadataRelation, ReferenceSystem)
from registry.models.service import (FeatureType, Layer, WebFeatureService,
                                     WebMapService)

#: the described elements a dataset record may be coupled to. The check
#: constraint of ``MetadataRelation`` allows a dataset record beside these two
#: only, so they are also the only pair columns which need a constraint.
ELEMENTS = ('layer', 'feature_type')


class CouplingParts:
    """One dataset record, one layer and one feature type to couple it to."""

    def make_coupling_parts(self):
        """Create the couple's three parts for this test run.

        Not ``setUpTestData``: the migration test below is a
        ``TransactionTestCase``, which has no class level data to set up, and
        both classes want the same rows.
        """
        contact = MetadataContact.objects.create(name='Coupling contact')
        self.dataset = DatasetMetadataRecord.objects.create(
            metadata_contact=contact, dataset_contact=contact,
            title='Coupled dataset', code_space='de.mrmap.',
            code='coupled-dataset',
            file_identifier='de.mrmap.coupled-dataset')
        wms = WebMapService.objects.create(
            title='Coupling wms', version=130, origin=1,
            service_url='https://example.com/wms/coupling',
            metadata_contact=contact, service_contact=contact)
        self.layer = Layer.objects.create(
            service=wms, title='Coupled layer', identifier='coupled-layer',
            mptt_tree=Tree.objects.create(), mptt_lft=1, mptt_rgt=2,
            mptt_depth=0)
        wfs = WebFeatureService.objects.create(
            title='Coupling wfs', version=200, origin=1,
            service_url='https://example.com/wfs/coupling',
            metadata_contact=contact, service_contact=contact)
        self.feature_type = FeatureType.objects.create(
            service=wfs, title='Coupled feature type',
            identifier='coupled-feature-type',
            default_reference_system=ReferenceSystem.objects.create())

    def element(self, name):
        """The described element one couple is about"""
        return getattr(self, name)


class DatasetCouplingUniquenessTests(CouplingParts, TestCase):
    """What the schema answers for one couple of a dataset record."""

    def setUp(self):
        super().setUp()
        self.make_coupling_parts()

    def test_the_same_reference_is_re_asserted_and_not_stacked(self):
        """The idempotence ``add_metadata_relation`` promises, unchanged.

        This is what the ``get_or_create`` was written for: collecting the same
        reference again answers the coupling which is already there.
        """
        first = self.dataset.add_metadata_relation(
            related_object=self.element('layer'))
        again = self.dataset.add_metadata_relation(
            related_object=self.element('layer'))

        self.assertEqual(first.pk, again.pk)
        self.assertEqual(MetadataRelation.objects.count(), 1)

    def test_the_second_row_of_a_couple_is_refused(self):
        """The write the missing constraint let through (#1483).

        Each subtest names the element whose pair column the constraint covers:
        the two are separate constraints and a copy-paste in one of them reads
        as green for the other.
        """
        for element in ELEMENTS:
            with self.subTest(element=element):
                described = self.element(element)
                evidence = self.dataset.add_metadata_relation(
                    related_object=described)

                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        MetadataRelation.objects.create(
                            dataset_metadata=self.dataset,
                            **{element: described},
                            origin=MetadataOriginEnum.CATALOGUE.value,
                            is_internal=evidence.is_internal)

                self.assertEqual(
                    MetadataRelation.objects.filter(
                        dataset_metadata=self.dataset,
                        **{element: described}).count(), 1,
                    'a second row of the couple survived the constraint')

    def test_the_two_kinds_of_a_couple_stay_rows_of_their_own(self):
        """Why ``is_internal`` belongs to the key of the constraint.

        The imported evidence of a capabilities document and the coupling a
        curator maintains in MrMap are separate rows of one pair: only one of
        them is published, and a constraint over the bare pair would refuse a
        curator's coupling of a reference the document already carried - or the
        harvest of a document for a pair a curator coupled first.
        """
        for element in ELEMENTS:
            with self.subTest(element=element):
                described = self.element(element)
                evidence = self.dataset.add_metadata_relation(
                    related_object=described)
                curated = self.dataset.add_metadata_relation(
                    related_object=described,
                    origin=MetadataOriginEnum.EDITOR.value, is_internal=True)

                self.assertNotEqual(evidence.pk, curated.pk)
                self.assertFalse(evidence.is_internal)
                self.assertTrue(curated.is_internal)
                self.assertEqual(
                    MetadataRelation.objects.filter(
                        dataset_metadata=self.dataset,
                        **{element: described}).count(), 2)

    def test_a_row_without_an_element_is_no_couple_of_anything(self):
        """The record-only rows of the table are no pairs to compare.

        ``add_metadata_relation`` accepts no described element at all; the pair
        columns of such a row stay empty, which no pair constraint of the table
        has ever compared - not before this one and not after it.
        """
        for _ in range(2):
            MetadataRelation.objects.create(
                dataset_metadata=self.dataset,
                origin=MetadataOriginEnum.CATALOGUE.value)

        self.assertEqual(
            MetadataRelation.objects.filter(
                dataset_metadata=self.dataset, layer__isnull=True,
                feature_type__isnull=True).count(), 2)


class DatasetCouplingDedupeMigrationTest(CouplingParts, TransactionTestCase):
    """0060 removes the repetitions of a couple, then refuses them."""

    migrate_from = [
        ('registry',
         '0059_remove_catalogueservice_registry_ca_update__7b419c_idx_and_more')]
    migrate_to = [
        ('registry', '0060_the_dataset_coupling_is_unique_per_kind')]

    def setUp(self):
        super().setUp()
        self.addCleanup(self.restore_schema)
        self.make_coupling_parts()

    def restore_schema(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def repetitions(self):
        """The rows a deployment carries under the schema which allowed them.

        Written with the models of the state before the constraint, because
        that is the schema which let them in: one couple per element with three
        repetitions - the first of them is what the dedupe has to leave behind,
        the two after it are what it has to remove - beside a row of the very
        same pair which is an internal one, which is a couple of its own and has
        to survive, beside a row which names no element at all, which is no pair
        and has to survive too.

        Returns:
            dict: per element the primary key of the first row and of the
                internal row, plus the key of the row which names no element
        """
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        apps = executor.loader.project_state(self.migrate_from).apps
        Relation = apps.get_model('registry', 'MetadataRelation')
        dataset = apps.get_model(
            'registry', 'DatasetMetadataRecord').objects.get(pk=self.dataset.pk)
        described = {
            'layer': apps.get_model('registry', 'Layer').objects.get(
                pk=self.layer.pk),
            'feature_type': apps.get_model(
                'registry', 'FeatureType').objects.get(pk=self.feature_type.pk),
        }

        written = {}
        for element in ELEMENTS:
            rows = [Relation.objects.create(
                dataset_metadata=dataset, **{element: described[element]},
                origin=MetadataOriginEnum.CAPABILITIES.value)
                for _ in range(3)]
            written[element] = {
                'first': rows[0].pk,
                'internal': Relation.objects.create(
                    dataset_metadata=dataset,
                    **{element: described[element]},
                    origin=MetadataOriginEnum.EDITOR.value,
                    is_internal=True).pk,
            }
        written['without_element'] = Relation.objects.create(
            dataset_metadata=dataset,
            origin=MetadataOriginEnum.CATALOGUE.value).pk
        return written

    def rows_per_couple(self):
        """The rows the upgrade left behind, grouped by the couple they form.

        Grouped by what the pair constraint compares - the element of the
        coupling and its kind - and answered as the primary keys of the rows, so
        an assertion about a survivor names the row it means.

        Returns:
            dict: per (element, kind of coupling) the primary keys of its rows,
                in the order they were written
        """
        couples = {}
        for element in ELEMENTS:
            for kind in (False, True):
                couples[(element, kind)] = list(
                    MetadataRelation.objects.filter(
                        dataset_metadata=self.dataset, is_internal=kind,
                        **{element: self.element(element)}).order_by('pk')
                    .values_list('pk', flat=True))
        return couples

    def test_the_upgrade_keeps_one_row_per_couple(self):
        """The oldest row of a couple stands, its repetitions are gone.

        The oldest one stands because that is the row every writer of the
        couple would have re-used: ``get_or_create`` returns the row it finds,
        and before the constraint existed it found the first one written. The
        internal coupling of the very same pair is a couple of its own and keeps
        its row, which is why the assertion reads per kind and not per pair.
        """
        seeded = self.repetitions()

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)

        survivors = self.rows_per_couple()
        for element in ELEMENTS:
            with self.subTest(element=element):
                self.assertEqual(survivors[(element, False)],
                                 [seeded[element]['first']],
                                 'the dedupe kept a repetition of the imported '
                                 'coupling, or dropped its first row')
                self.assertEqual(survivors[(element, True)],
                                 [seeded[element]['internal']],
                                 'the dedupe treated the internal coupling of a '
                                 'pair as a repetition of the imported one')

        self.assertTrue(
            MetadataRelation.objects.filter(
                pk=seeded['without_element']).exists(),
            'the dedupe compared a row which names no element to a repetition')

    def test_the_upgraded_schema_refuses_a_new_repetition(self):
        """After the upgrade it is the constraint which answers the race."""
        self.repetitions()
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)

        for element in ELEMENTS:
            with self.subTest(element=element):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        MetadataRelation.objects.create(
                            dataset_metadata=self.dataset,
                            **{element: self.element(element)},
                            origin=MetadataOriginEnum.CATALOGUE.value)
