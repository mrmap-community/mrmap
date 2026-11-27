"""The coupling of one dataset record to one element is stored once (#1483).

``MetadataRecord.add_metadata_relation`` asserts a coupling with
``get_or_create`` inside ``select_for_update``. The lock answers the case where
the row is already there; for a missing row it locks nothing at all, so two
writers of one couple - the same reference collected twice, a registration
beside an update - both saw no row and both wrote one. The service side of the
same table never had that hole, because its pairs are unique constraints since
their first migration; the dataset side is closed the same way here.

The key of the new constraints is the key the write path itself re-asserts on:
the pair beside ``is_internal`` and ``origin``, the two columns which say
*which* coupling of a pair a row is. The table holds rows of one couple on
purpose - the imported evidence of a document, the internal coupling a curator
maintains (``MetadataRelation.publication_kind``) and the EDITOR coupling a
collection finds standing beside the one it asserts itself, which
``tests/django/registry/tasks/tests_reference_work_queue.py`` pins - and a key
which left ``origin`` out refuses what that flow writes.

``DatasetCouplingUniquenessTests`` pins what the schema answers for the live
model. ``DatasetCouplingDedupeMigrationTest`` proves the upgrade of #1483 on
the rebuilt chain of #1850: the chain creates the coupling table already
constrained and has no node before the constraint to travel back to, so the
test builds that state itself -- it takes the very constraints which
``0001_initial`` created away, writes the repetitions that schema allowed, and
runs the statements of the upgrade over them before it refuses them.
"""

from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models import Exists, OuterRef
from django.test import TestCase

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

#: the kinds of coupling one couple keeps a row of its own for: ``origin`` and
#: ``is_internal``, the columns ``add_metadata_relation`` keys its
#: ``get_or_create`` on beside the pair, which is what the pair constraint of
#: #1483 therefore compares
KINDS = {
    'imported evidence': (MetadataOriginEnum.CAPABILITIES.value, False),
    'curated coupling': (MetadataOriginEnum.EDITOR.value, True),
    # the shape the collection of an advertised document finds standing:
    # another origin, the same flag
    'curated from the catalogue': (MetadataOriginEnum.EDITOR.value, False),
}

#: the kind the repetitions of a couple are written as, and whose oldest row
#: the dedupe of the upgrade has to leave standing
FIRST_KIND = 'imported evidence'

#: the two pair constraints of the dataset side, per element, as ``0001_initial``
#: of the rebuilt chain creates them -- the same two which the dedupe node of
#: the old chain added over the deduped table
PAIR_CONSTRAINTS = {
    'layer': 'unique_dataset_metadata_representation_for_layer',
    'feature_type': 'unique_dataset_metadata_representation_for_feature_type',
}


class CouplingParts:
    """One dataset record, one layer and one feature type to couple it to."""

    def make_coupling_parts(self):
        """Create the couple's three parts for this test run.

        Not ``setUpTestData``: the dedupe test below writes around these
        rows with the constraints of the schema taken away, and both classes
        want the rows of their own test run.
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

    def test_the_second_row_of_a_couple_of_one_kind_is_refused(self):
        """The write the missing constraint let through (#1483).

        Each subtest names the element and the kind whose row is repeated: the
        two elements are separate constraints, so a copy-paste in one of them
        reads as green for the other, and a kind the key does not compare would
        let the race of #1483 through under its own ``origin``.
        """
        for element in ELEMENTS:
            for kind, (origin, is_internal) in KINDS.items():
                with self.subTest(element=element, kind=kind):
                    described = self.element(element)
                    self.dataset.add_metadata_relation(
                        related_object=described, origin=origin,
                        is_internal=is_internal)

                    with self.assertRaises(IntegrityError):
                        with transaction.atomic():
                            MetadataRelation.objects.create(
                                dataset_metadata=self.dataset,
                                **{element: described},
                                origin=origin, is_internal=is_internal)

                    self.assertEqual(
                        MetadataRelation.objects.filter(
                            dataset_metadata=self.dataset, origin=origin,
                            is_internal=is_internal,
                            **{element: described}).count(), 1,
                        'a second row of one coupling survived the constraint')

    def test_every_kind_of_a_couple_stays_a_row_of_its_own(self):
        """Why ``origin`` and ``is_internal`` belong to the key.

        Three rows of one pair are production readings, not test shapes: the
        evidence a capabilities document carried, the coupling a curator
        maintains in MrMap, and the EDITOR coupling a collection finds standing
        beside the one it asserts itself. A constraint over the bare pair - or
        over the pair plus one of the two columns - would refuse one of them,
        and the write path would answer an IntegrityError for a coupling it
        neither wrote nor may drop.
        """
        for element in ELEMENTS:
            with self.subTest(element=element):
                described = self.element(element)
                asserted = {
                    kind: self.dataset.add_metadata_relation(
                        related_object=described, origin=origin,
                        is_internal=is_internal).pk
                    for kind, (origin, is_internal) in KINDS.items()}

                self.assertEqual(
                    len(set(asserted.values())), len(KINDS),
                    'two kinds of one couple share a row')
                self.assertEqual(
                    MetadataRelation.objects.filter(
                        dataset_metadata=self.dataset,
                        **{element: described}).count(), len(KINDS))

                # and asserting one of them again answers its own row
                for kind, (origin, is_internal) in KINDS.items():
                    self.assertEqual(
                        self.dataset.add_metadata_relation(
                            related_object=described, origin=origin,
                            is_internal=is_internal).pk,
                        asserted[kind],
                        're-asserting a kind answered another kind of the pair')

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


class DatasetCouplingDedupeMigrationTest(CouplingParts, TestCase):
    """The dedupe and the constraint of #1483 on the rebuilt chain.

    The rebuilt history (#1850) creates the coupling table already
    constrained: no node of it exists without the two pair constraints, so
    the executor cannot travel to the state which allowed the repetitions the
    way it did while the dedupe node of the old chain still stood. The test
    builds that state itself instead -- it takes the very constraints
    ``0001_initial`` created away, writes what they refused, and runs the
    statements of the upgrade over the rows: the dedupe of the old node,
    which the new chain never needed because its table was empty when it was
    constrained, and the constraints again, read from the schema of the chain
    -- so a ``0001_initial`` which lost one of them goes red at the reading
    and one which weakened one goes red at the refusal. What the test asks of
    the upgrade is what it asked before: the oldest row of a coupling stands,
    its repetitions are gone, every other kind keeps its own row, and a new
    repetition is answered by the constraint.
    """

    def setUp(self):
        super().setUp()
        self.make_coupling_parts()

    def rebuilt_chain(self):
        """The plan of the rebuilt chain, which the upgrade runs on."""
        plan = MigrationExecutor(connection).loader.graph.forwards_plan(
            ('registry', '0001_initial'))
        self.assertIn(('registry', '0001_initial'), plan)
        return plan

    def chain_pair_constraint_definitions(self):
        """The two pair constraints, as the rebuilt chain created them.

        Read from the catalog of the migrated test database, which is what
        ``0001_initial`` answered: a chain which lost one of the constraints
        is gone here, and the definition of one which no longer compares the
        whole key of #1483 is gone with it -- the refusal of a new repetition
        covers a key which only got weaker.
        """
        definitions = {}
        with connection.cursor() as cursor:
            for element, name in PAIR_CONSTRAINTS.items():
                cursor.execute(
                    "SELECT pg_get_constraintdef(con.oid)"
                    " FROM pg_constraint con"
                    " JOIN pg_class rel ON rel.oid = con.conrelid"
                    " WHERE rel.relname = %s"
                    " AND rel.relnamespace = 'public'::regnamespace"
                    " AND con.conname = %s AND con.contype = 'u'",
                    [MetadataRelation._meta.db_table, name])
                row = cursor.fetchone()
                self.assertIsNotNone(
                    row,
                    'the rebuilt 0001_initial did not create the pair '
                    'constraint %s of the dataset coupling' % name)
                columns = {
                    column.strip() for column in
                    row[0][row[0].index('(') + 1:row[0].rindex(')')]
                    .split(',')}
                self.assertEqual(
                    columns,
                    {'is_internal', 'origin', 'dataset_metadata_id',
                     '%s_id' % element},
                    'the pair constraint %s does not compare the key of '
                    '#1483' % name)
                definitions[name] = row[0]
        return definitions

    @staticmethod
    def drop_pair_constraints(definitions):
        """The state before the constraint, rebuilt: the two constraints away.

        The schema the old chain stood in below its dedupe node, taken from
        the chain itself rather than named, which the rebuild left no name
        for.
        """
        with connection.cursor() as cursor:
            for name in definitions:
                cursor.execute(
                    'ALTER TABLE "%s" DROP CONSTRAINT "%s"'
                    % (MetadataRelation._meta.db_table, name))

    @staticmethod
    def drop_repeated_couplings():
        """The dedupe statement of the upgrade, carried here.

        The old chain removed the repetitions in the migration which added
        the constraints; the rebuilt chain had no repetitions to remove -- it
        created the empty table constrained -- so the statement of that node
        stands in here as the node answered it: of every couple the row with
        the lowest primary key stands, because that is the row every writer
        of the couple would have re-used, and rows of a different kind of the
        same pair are couplings of their own and stay untouched.
        """
        for element in ELEMENTS:
            earlier_of_the_same_couple = MetadataRelation.objects.filter(
                **{
                    'pk__lt': OuterRef('pk'),
                    'is_internal': OuterRef('is_internal'),
                    'origin': OuterRef('origin'),
                    f'{element}_id': OuterRef(f'{element}_id'),
                    'dataset_metadata_id': OuterRef('dataset_metadata_id'),
                })
            MetadataRelation.objects.filter(
                Exists(earlier_of_the_same_couple),
                **{
                    f'{element}_id__isnull': False,
                    'dataset_metadata_id__isnull': False,
                }).delete()

    @staticmethod
    def add_pair_constraints(definitions):
        """The second half of the upgrade: the constraints of the chain again.

        Added from the definition the chain itself created, so that what
        refuses the next repetition below is the constraint of
        ``0001_initial``. The foreign keys of a table built by a migration
        come up ``DEFERRABLE INITIALLY DEFERRED``, and the repetitions queued
        their check of existence; the upgrade of the old chain ran in a
        migration transaction of its own over rows which were committed
        already, and forcing the pending checks answers that boundary here --
        all the rows of the couple still reference rows which are there.
        """
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            for name, definition in definitions.items():
                cursor.execute(
                    'ALTER TABLE "%s" ADD CONSTRAINT "%s" %s'
                    % (MetadataRelation._meta.db_table, name, definition))

    def seed_and_upgrade(self):
        """The upgrade of #1483 on the rebuilt chain, once, returning the seed.

        The state before the constraint, the repetitions written into it and
        the statements which removed them and answered the constraints again
        -- in the order the executor ran them over a deployment while the
        dedupe node still stood.
        """
        self.rebuilt_chain()
        definitions = self.chain_pair_constraint_definitions()
        self.drop_pair_constraints(definitions)
        seeded = self.repetitions()
        self.drop_repeated_couplings()
        self.add_pair_constraints(definitions)
        return seeded

    def repetitions(self):
        """The rows a deployment carries under the schema which allowed them.

        Written while the pair constraints of the chain stand taken away,
        which is the schema that let them in: three rows of one couple and
        one kind - the first of them is what the dedupe has to leave behind,
        the two after it are what it has to remove - beside a row of the very
        same pair of every other kind, which is a coupling of its own and has
        to survive, beside a row which names no element at all, which is no
        pair and has to survive too.

        Returns:
            dict: per element the primary key of the first row of
                ``FIRST_KIND`` and of the row of every other kind, plus the
                key of the row which names no element
        """
        written = {}
        for element in ELEMENTS:
            origin, is_internal = KINDS[FIRST_KIND]
            rows = [MetadataRelation.objects.create(
                dataset_metadata=self.dataset,
                **{element: self.element(element)},
                origin=origin, is_internal=is_internal)
                for _ in range(3)]
            others = {
                kind: MetadataRelation.objects.create(
                    dataset_metadata=self.dataset,
                    **{element: self.element(element)},
                    origin=kind_origin, is_internal=kind_internal).pk
                for kind, (kind_origin, kind_internal) in KINDS.items()
                if kind != FIRST_KIND}
            written[element] = {'first': rows[0].pk, 'others': others}
        written['without_element'] = MetadataRelation.objects.create(
            dataset_metadata=self.dataset,
            origin=MetadataOriginEnum.CATALOGUE.value).pk
        return written

    def rows_per_couple(self):
        """The rows the upgrade left behind, grouped by the coupling they form.

        Grouped by what the pair constraint compares - the element, the origin
        and the flag - and answered as the primary keys of the rows, so an
        assertion about a survivor names the row it means.

        Returns:
            dict: per (element, kind) the primary keys of its rows, in the
                order they were written
        """
        couples = {}
        for element in ELEMENTS:
            for kind, (origin, is_internal) in KINDS.items():
                couples[(element, kind)] = list(
                    MetadataRelation.objects.filter(
                        dataset_metadata=self.dataset, origin=origin,
                        is_internal=is_internal,
                        **{element: self.element(element)}).order_by('pk')
                    .values_list('pk', flat=True))
        return couples

    def test_the_upgrade_keeps_one_row_per_coupling(self):
        """The oldest row of a coupling stands, its repetitions are gone.

        The oldest one stands because that is the row every writer of the
        coupling would have re-used: ``get_or_create`` returns the row it finds,
        and before the constraint existed it found the first one written. Every
        other kind of the very same pair is a coupling of its own and keeps its
        row, which is why the assertion reads per kind and not per pair.
        """
        seeded = self.seed_and_upgrade()

        survivors = self.rows_per_couple()
        for element in ELEMENTS:
            with self.subTest(element=element):
                self.assertEqual(
                    survivors[(element, FIRST_KIND)],
                    [seeded[element]['first']],
                    'the dedupe kept a repetition of the imported coupling, or '
                    'dropped its first row')
                for kind, pk in seeded[element]['others'].items():
                    self.assertEqual(
                        survivors[(element, kind)], [pk],
                        f'the dedupe treated the {kind} of a pair as a '
                        'repetition of another kind')

        self.assertTrue(
            MetadataRelation.objects.filter(
                pk=seeded['without_element']).exists(),
            'the dedupe compared a row which names no element to a repetition')

    def test_the_upgraded_schema_refuses_a_new_repetition(self):
        """After the upgrade it is the constraint which answers the race.

        The constraint is the one of the rebuilt chain: the upgrade put its
        very definition back, which the test had read from the schema
        ``0001_initial`` created.
        """
        self.seed_and_upgrade()

        for element in ELEMENTS:
            origin, is_internal = KINDS[FIRST_KIND]
            with self.subTest(element=element):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        MetadataRelation.objects.create(
                            dataset_metadata=self.dataset,
                            **{element: self.element(element)},
                            origin=origin, is_internal=is_internal)
