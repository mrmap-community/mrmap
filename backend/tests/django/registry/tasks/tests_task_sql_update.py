"""Task-side SQL guards for the service-update family (#1393).

Audit page: ``docs/source/development/celery-task-orm-audit.rst`` ("Family:
update jobs"). What this pins, per the #1395 coverage checklist:

*   The read plan of ``old_service``/``new_service`` is config-driven:
    ``QuerySet.for_update_diff(update_config)`` carries the element ROWS for
    the mapping phase and exactly the service relations the update config
    names - never the breadth of ``prefetch_whole_service``, and never an
    element's M2M or reverse relations, which ride the mapping reads of
    ``update_layers``/``update_featuretypes`` per relation (#1393).
*   The apply phase of a WMS update over 1/10/100 mapped layer pairs costs
    the same statements: the comparison reads the configured element
    relations once per relation, not once per layer and relation.
*   The same shape for the WFS apply phase over mapped feature types.

Two update configs of the same service make the plan width observable: a
narrow one (no service relations) and a wide one (two service relations);
the difference in statements must be exactly those two relation reads.

The numbers below are statements and rows, not runtime (V1 scope; #1396 owns
timings).
"""
from django.test import TestCase
from mptt2.models import Tree
from registry.enums.update import UpdateModeEnum
from registry.managers.service import configured_relation_fields
from registry.models.metadata import Keyword, ReferenceSystem
from registry.models.service import (FeatureType, Layer, WebFeatureService,
                                     WebMapService)
from registry.models.update import (FeatureTypeMapping, LayerMapping,
                                    WebFeatureServiceUpdateConfig,
                                    WebFeatureServiceUpdateJob,
                                    WebMapServiceUpdateConfig,
                                    WebMapServiceUpdateJob)
from tests.django.sql_guard import SqlGuardMixin, statements_of

WMS_PK = 'cd16cc1f-3abb-4625-bb96-fbe80dbe23e3'
WFS_PK = '9cc4889d-0cd4-4c3b-8975-58de6d30db41'

# the WMS config without service relations: the plan is the service row plus
# the layer rows ("NARROW"); the WIDE one names two service relations
NARROW_WMS_CONFIG = {
    "WebMapService": {"title": UpdateModeEnum.OVERWRITE},
    "Layer": {"title": UpdateModeEnum.OVERWRITE},
}
WIDE_WMS_CONFIG = {
    "WebMapService": {
        "title": UpdateModeEnum.OVERWRITE,
        "keywords": UpdateModeEnum.OVERWRITE,
        "operation_urls": UpdateModeEnum.OVERWRITE,
    },
    "Layer": {"title": UpdateModeEnum.OVERWRITE},
}
# the config of the apply-phase guards: element relations which old and
# candidate element share, so the comparison reads them but writes nothing
COMPARE_WMS_CONFIG = {
    "WebMapService": {"title": UpdateModeEnum.OVERWRITE},
    "Layer": {
        "title": UpdateModeEnum.OVERWRITE,
        "identifier": UpdateModeEnum.OVERWRITE,
        "keywords": UpdateModeEnum.OVERWRITE,
        "reference_systems": UpdateModeEnum.OVERWRITE,
    },
}
COMPARE_WFS_CONFIG = {
    "WebFeatureService": {"title": UpdateModeEnum.OVERWRITE},
    "FeatureType": {
        "title": UpdateModeEnum.OVERWRITE,
        "identifier": UpdateModeEnum.OVERWRITE,
        "keywords": UpdateModeEnum.OVERWRITE,
        "reference_systems": UpdateModeEnum.OVERWRITE,
    },
}


def through_table(model, field_name):
    """The database table behind one M2M of a model."""
    return model._meta.get_field(
        field_name).remote_field.through._meta.db_table


def statements_touching(context, table, verb=None):
    """The captured statements which name TABLE anywhere (FROM or JOIN).

    ``statements_of`` attributes a statement to its first table, but an M2M
    prefetch names the target model there and only JOINs the through table -
    which is the table the relation-read count is about.
    """
    needle = f'"{table.lower()}"'
    matched = []
    for query in context.captured_queries:
        sql = query['sql']
        if verb and not sql.lstrip().lower().startswith(verb):
            continue
        if needle in sql.lower():
            matched.append(query)
    return matched


# The history-attribution receiver (``ServiceHistoricalRecords.
# create_historical_record``, registry/models/service.py) answers whether an
# element belongs to a candidate by asking its service - one single-column
# EXISTS on the CONCRETE service row per candidate element the delete
# collector collects at the end of the apply phase. That per-element read
# predates #1393; what #1482 narrowed is its WIDTH - the question is the
# one column ``update_candidate_of_id``, not the whole service row, and the
# question is skipped entirely whenever the caller already holds the
# service. The scaling guards run with the pairs' configured relations
# equal, so this read - and only it - is allowed to grow with the pairs,
# named by fingerprint and pinned to exactly one statement per pair.
WMS_HISTORY_NEEDLE = ('from "registry_webmapservice" where '
                      '("registry_webmapservice"."id" = ?::uuid and '
                      '"registry_webmapservice"."update_candidate_of_id" '
                      'is not null)')
WFS_HISTORY_NEEDLE = ('from "registry_webfeatureservice" where '
                      '("registry_webfeatureservice"."id" = ?::uuid and '
                      '"registry_webfeatureservice".'
                      '"update_candidate_of_id" is not null)')

# One single-column EXISTS per deleted candidate element is the standing
# shape of the history attribution (see the comment above): the scaling
# guards therefore allow exactly one statement per pair (``per_row`` 1) and
# name it; the fingerprint guards exclude the same fingerprint. The
# for_update_diff plan reads of the old service are constant statements and
# ride within the ``extra`` slack.


class WmsUpdateReadPlanTest(SqlGuardMixin, TestCase):
    """The width of the ``old_service``/``new_service`` plan is the config.

    ``for_update_diff`` replaced ``prefetch_whole_service`` on these reads
    (#1393): what the plan carries besides the element rows is exactly the
    service relations the update config names - a second, wider config must
    therefore cost exactly its own relation reads and nothing else.
    """

    fixtures = ['test_users.json', 'test_keywords.json', 'test_wms.json']

    def setUp(self):
        self.wms = WebMapService.objects.get(pk=WMS_PK)
        self.config = WebMapServiceUpdateConfig.objects.create(
            service=self.wms, config=NARROW_WMS_CONFIG)
        self.job = WebMapServiceUpdateJob.objects.create(service=self.wms)

    def _read_plan(self):
        """The plan read the way the update consumes it: the service row,
        the layer rows and one touch per configured service relation (that
        is what ``update_metadata`` does per configured field; a plain
        ``.get()`` would never fire the prefetches)."""
        def read():
            service = WebMapService.objects.for_update_diff(
                config).get(pk=self.wms.pk)
            list(service.layers.all())
            for name in configured_relation_fields(
                    WebMapService, config.get('WebMapService', {})):
                list(getattr(service, name).all())
            return service
        config = self.job.update_config  # cache the config row out of capture
        return read

    def _plan_read(self):
        return self.capture(self._read_plan())

    def test_plan_width_follows_the_update_config(self):
        """Narrow config: the service row and the layer rows - two reads.

        Wide config (same service, one stored row apart): the same two plus
        exactly one read per service relation the config names now.
        """
        _, narrow = self._plan_read()
        self.assertEqual(len(narrow.captured_queries), 2,
                         msg='one service SELECT plus the layer rows; '
                             'the narrow plan carries no relation reads')

        self.config.config = WIDE_WMS_CONFIG
        self.config.save()
        self.job = WebMapServiceUpdateJob.objects.get(pk=self.job.pk)
        _, wide = self._plan_read()
        self.assertEqual(len(wide.captured_queries),
                         len(narrow.captured_queries) + 2,
                         msg='exactly the two configured service relations '
                             'widen the plan, nothing else')
        keyword_reads = statements_touching(
            wide, through_table(WebMapService, 'keywords'), verb='select')
        self.assertEqual(len(keyword_reads), 1,
                         'keywords is configured: exactly one relation read')
        url_reads = statements_of(
            wide, verb='select', table='registry_webmapserviceoperationurl')
        self.assertEqual(len(url_reads), 1,
                         'operation_urls is configured: exactly one read')

    def test_element_relations_never_ride_the_service_plan(self):
        """A config naming element relations keeps them off the service read.

        ``Layer`` relations are read per relation on the mapping rows of
        ``update_layers``, never as a second prefetch of the service plan -
        that split is the #1393 read plan; before it ``prefetch_whole_service``
        read every element relation here.
        """
        self.config.config = {
            "WebMapService": {"title": UpdateModeEnum.OVERWRITE},
            "Layer": {
                "title": UpdateModeEnum.OVERWRITE,
                "styles": UpdateModeEnum.OVERWRITE,
                "keywords": UpdateModeEnum.OVERWRITE,
                "reference_systems": UpdateModeEnum.OVERWRITE,
                "time_extents": UpdateModeEnum.OVERWRITE,
            },
        }
        self.config.save()
        self.job = WebMapServiceUpdateJob.objects.get(pk=self.job.pk)
        self.assertStatementTouchesNo(
            self._read_plan(),
            forbidden_tables=[
                'registry_style',
                through_table(Layer, 'keywords'),
                through_table(Layer, 'reference_systems'),
                through_table(Layer, 'time_extents')],
            label='the WMS update service plan')


class WmsLayerApplyPhaseTest(SqlGuardMixin, TestCase):
    """``update_layers`` over 1/10/100 confirmed layer pairs.

    The compare config names ``keywords`` and ``reference_systems`` for a
    Layer and every pair shares the same keyword and reference-system rows,
    so the apply phase compares, writes nothing and its statements must not
    grow with the pairs: the configured relations ride the mapping read once
    per relation (#1393) - before it, every layer paid its own relation reads
    and the service plan rode ``prefetch_whole_service``.
    """

    fixtures = ['test_users.json', 'test_keywords.json', 'test_wms.json']

    def setUp(self):
        self.wms = WebMapService.objects.get(pk=WMS_PK)
        WebMapServiceUpdateConfig.objects.create(
            service=self.wms, config=COMPARE_WMS_CONFIG)
        self.job = WebMapServiceUpdateJob.objects.create(service=self.wms)
        self.keywords = list(Keyword.objects.all()[:2])
        self.reference = ReferenceSystem.objects.first()

    def root(self):
        """The published root; every other published layer is cleaned by
        ``_seed``, so exactly this one root answers in every measured round."""
        return Layer.objects.get(service=self.wms, mptt_parent=None)

    def _seed(self, size):
        """One candidate with a root clone plus ``size`` guard pairs with
        equal configured relations - the same world in every round, so the
        measured statement counts are directly comparable."""
        WebMapService.objects.filter(update_candidate_of=self.wms).delete()
        self.job.mappings.all().delete()
        Layer.objects.filter(service=self.wms).exclude(
            mptt_parent__isnull=True).delete()
        candidate = WebMapService.objects.create(
            title="Update candidate", service_url=self.wms.service_url,
            version=self.wms.version, origin=self.wms.origin,
            update_candidate_of=self.wms,
            metadata_contact=self.wms.metadata_contact,
            service_contact=self.wms.service_contact)
        old_root = self.root()
        new_root = Layer.objects.create(
            service=candidate, title=old_root.title,
            identifier=old_root.identifier,
            mptt_tree=Tree.objects.create(), mptt_lft=1, mptt_rgt=2,
            mptt_depth=0)
        pairs = [(old_root, new_root)]
        for index in range(size):
            old = Layer.objects.create(
                service=self.wms, title=f"guard {index}",
                identifier=f"guard-{index}", mptt_parent=old_root,
                mptt_tree=old_root.mptt_tree, mptt_lft=2, mptt_rgt=3,
                mptt_depth=1)
            new = Layer.objects.create(
                service=candidate, title=f"guard {index}",
                identifier=f"guard-{index}", mptt_parent=new_root,
                mptt_tree=new_root.mptt_tree, mptt_lft=2, mptt_rgt=3,
                mptt_depth=1)
            pairs.append((old, new))
        for old, new in pairs:
            old.keywords.set(self.keywords)
            new.keywords.set(self.keywords)
            old.reference_systems.set([self.reference])
            new.reference_systems.set([self.reference])
            LayerMapping.objects.create(
                job=self.job, new_layer=new, old_layer=old,
                is_confirmed=True)

    def _apply(self):
        """The apply phase with the state a worker would hold: a fresh job."""
        return WebMapServiceUpdateJob.objects.get(
            pk=self.job.pk).update_layers()

    def test_the_apply_phase_does_not_grow_with_the_layer_pairs(self):
        # one statement per pair is the named history-attribution read (see
        # the module comment); everything else of the apply phase stays at
        # the constant of the smallest measurement.
        self.assertQueryCountIndependent(
            sizes=(1, 10, 100),
            seed=self._seed,
            run=self._apply,
            per_row=1,
            extra=6,
            label='the WMS layer apply phase')

    def test_each_configured_relation_is_read_once_per_side(self):
        """At 100 pairs: two IN reads per configured relation, none else.

        Old and candidate side are one prefetch each - the prefetch names the
        target table and JOINs the through table, which is what
        ``statements_touching`` counts; an unconfigured element relation is
        never prefetched at all (``configured_relation_fields`` answers only
        the configured names - pinned as a unit fact by the plan test), and
        no relation is read per layer - that is the shape #1393 established.
        """
        self._seed(100)
        _, context = self.capture(self._apply)
        for table in ('registry_keyword', 'registry_referencesystem'):
            reads = statements_touching(context, table, verb='select')
            self.assertEqual(
                len(reads), 2,
                msg=f'{table}: one IN read for the mapped new layers and '
                    f'one for the old, not one per layer')

    def test_no_statement_repeats_per_pair_at_the_largest_shape(self):
        """The fingerprint guard on the same 100-pair world.

        Sanctioned: each configured relation is prefetched once per side
        (old and new read the same tables and share a fingerprint), so two
        repeats per relation table are the plan, a third is a regression.
        The remote-metadata delete is sanctioned at two: the update's own
        take-back of the stale advertised references (#1413) and the
        candidate deletion's cascade over the same table are one statement
        each, constant over the pairs, and share the fingerprint.
        """
        self._seed(100)
        self.assertNoNPlusOne(
            self._apply,
            exclude=[WMS_HISTORY_NEEDLE],
            sanctioned={
                'from "registry_keyword"': 2,
                'from "registry_referencesystem"': 2,
                'left outer join "registry_layer" t3': 2,
                'delete from "registry_layerremotemetadata"': 2,
                # the job's own deferred old/new service FK reads on the
                # for_update_diff plan: constant two statements over any
                # number of pairs (#1482 detached them from the excluded
                # attribution fingerprint, which is now a narrow EXISTS)
                'from "registry_webmapservice" where '
                '"registry_webmapservice"."id" = ?::uuid limit ?': 2},
            label='the WMS layer apply phase at 100 pairs')


class WfsFeatureTypeApplyPhaseTest(SqlGuardMixin, TestCase):
    """``update_featuretypes`` over 1/10/100 confirmed feature-type pairs.

    The WFS counterpart of the WMS guard: same compare-by-shared-rows shape
    with the ``FeatureType`` relations of the WFS config (#1393).
    """

    fixtures = ['test_users.json', 'test_keywords.json',
                'test_crs.json', 'test_wfs.json']

    def setUp(self):
        self.wfs = WebFeatureService.objects.get(pk=WFS_PK)
        WebFeatureServiceUpdateConfig.objects.create(
            service=self.wfs, config=COMPARE_WFS_CONFIG)
        self.job = WebFeatureServiceUpdateJob.objects.create(service=self.wfs)
        self.keywords = list(Keyword.objects.all()[:2])
        self.reference = ReferenceSystem.objects.first()

    def _seed(self, size):
        """Only guard pairs on the published service - the same world in
        every round, so the measured statement counts are directly
        comparable (the WMS counterpart names its root)."""
        WebFeatureService.objects.filter(
            update_candidate_of=self.wfs).delete()
        self.job.mappings.all().delete()
        FeatureType.objects.filter(service=self.wfs).delete()
        candidate = WebFeatureService.objects.create(
            title="Update candidate", service_url=self.wfs.service_url,
            version=self.wfs.version, origin=self.wfs.origin,
            update_candidate_of=self.wfs,
            metadata_contact=self.wfs.metadata_contact,
            service_contact=self.wfs.service_contact)
        pairs = []
        for index in range(size):
            old = FeatureType.objects.create(
                service=self.wfs, title=f"guard {index}",
                identifier=f"guard-{index}",
                default_reference_system=self.reference)
            new = FeatureType.objects.create(
                service=candidate, title=f"guard {index}",
                identifier=f"guard-{index}",
                default_reference_system=self.reference)
            pairs.append((old, new))
        for old, new in pairs:
            old.keywords.set(self.keywords)
            new.keywords.set(self.keywords)
            old.reference_systems.set([self.reference])
            new.reference_systems.set([self.reference])
            FeatureTypeMapping.objects.create(
                job=self.job, new_featuretype=new, old_featuretype=old,
                is_confirmed=True)

    def _apply(self):
        return WebFeatureServiceUpdateJob.objects.get(
            pk=self.job.pk).update_featuretypes()

    def test_the_apply_phase_does_not_grow_with_the_featuretype_pairs(self):
        # the WMS counterpart names what the one statement per pair is.
        self.assertQueryCountIndependent(
            sizes=(1, 10, 100),
            seed=self._seed,
            run=self._apply,
            per_row=1,
            extra=6,
            label='the WFS feature-type apply phase')

    def test_each_configured_relation_is_read_once_per_side(self):
        self._seed(100)
        _, context = self.capture(self._apply)
        for table in ('registry_keyword', 'registry_referencesystem'):
            reads = statements_touching(context, table, verb='select')
            self.assertEqual(
                len(reads), 2,
                msg=f'{table}: one IN read for the mapped new feature types '
                    f'and one for the old, not one per feature type')

    def test_no_statement_repeats_per_pair_at_the_largest_shape(self):
        self._seed(100)
        self.assertNoNPlusOne(
            self._apply,
            exclude=[WFS_HISTORY_NEEDLE],
            sanctioned={
                'from "registry_keyword"': 2,
                'from "registry_referencesystem"': 2,
                # the element rows are read once per side (old, candidate,
                # and the mapped side the relations ride) - one fingerprint
                'from "registry_featuretype"': 3,
                # the update's own take-back of the stale advertised
                # references (#1413) and the candidate deletion's cascade
                # over the same table: one statement each, constant over
                # the pairs, one shared fingerprint
                'delete from "registry_featuretyperemotemetadata"': 2,
                # the job's own deferred old/new service FK reads on the
                # for_update_diff plan: constant two statements over any
                # number of pairs (#1482 detached them from the excluded
                # attribution fingerprint, which is now a narrow EXISTS)
                'from "registry_webfeatureservice" where '
                '"registry_webfeatureservice"."id" = ?::uuid limit ?': 2},
            label='the WFS feature-type apply phase at 100 pairs')
