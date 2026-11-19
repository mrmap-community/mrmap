"""The COUNT statements of the annotated list endpoints (#1478).

The audit (API-15/API-16) suspected that the paginator's COUNT re-executes an
expensive derivation behind an annotated list. Measured on the current
develop with the requests of this module, the answer differs per shape and
this module pins each measured answer, so a later change cannot silently
regrow the pathology the audit feared:

* The services' alert DISPLAY, SORT and SEARCH: the COUNT carries no
  derivation at all. ``QuerySet.count`` drops the SELECT annotations (which
  is what #1424's ``defer_alert_annotations`` docstring already states), so
  the COALESCE subqueries over the monitoring runs and update jobs appear in
  the page only, where the LIMIT bounds them. A cached count
  (``with_cached_count`` of #885) is therefore not needed for these shapes.
* The alert FILTER legitimately carries the derivation in the COUNT's WHERE:
  ``filter[has_alert]`` IS the derivation asked as a condition. Pinned as
  exactly one COUNT, so the filter answers the number once instead of
  re-evaluating the subqueries per row or per page.
* The cross-service alert list reads the STORED projection of the rules
  (#1030), so its COUNT names the alert table only and its queries do not
  grow with the number of alert rows.
* The metadata relation search COUNT spans the five LEFT OUTER JOINs of its
  ``search_fields`` - but every one of them joins a primary key of the
  pointed table, so there is no fan-out to deduplicate and the answer is one
  COUNT plus at most one page. An EXISTS rewrite measured cost-neutral by
  construction (same five joins, one more wrapper); vectorizing the search is
  schema work owned by the scale family #1424/#1426, not this COUNT half.
"""
from django.test import TestCase
from guardian.shortcuts import assign_perm
from registry.models.alerts import ServiceAlert
from registry.models.service import WebMapService

from tests.django.registry.tests_query_performance import (
    QueryMeasurementMixin, table_counter)

#: the tables the alert derivation is built from - none of them belongs in a
#: COUNT which only answers the number of services or of stored alert rows
DERIVATION_TABLES = ('monitoringrun', 'updatejob', 'harvestingjob')

WMS_ONE = 'cd16cc1f-3abb-4625-bb96-fbe80dbe23e3'
WMS_TWO = '1b195589-dcfa-403f-9e66-e7e1c0a67024'

DATASET_RELATION = 'd8b50d33-2ad7-4a41-bd0d-2d518ea10fd4'

#: the five primary key joins of MetadataRelationViewSet.search_fields
RELATION_SEARCH_JOINS = (
    ('layer_id', 'registry_layer'),
    ('feature_type_id', 'registry_featuretype'),
    ('wms_id', 'registry_webmapservice'),
    ('wfs_id', 'registry_webfeatureservice'),
    ('csw_id', 'registry_catalogueservice'),
)


def count_statements(queries, table):
    """The captured COUNT statements whose main FROM table is ``table``."""
    return [
        query['sql'] for query in queries
        if query['sql'].lstrip().lower().startswith('select count')
        and f'from "{table}"' in query['sql'].lower()]


def page_statements(queries, table):
    """The captured paged SELECT statements reading ``table`` (LIMIT)."""
    return [
        query['sql'] for query in queries
        if query['sql'].lstrip().lower().startswith('select')
        and f'from "{table}"' in query['sql'].lower()
        and ' limit ' in query['sql'].lower()]


class AlertCountShapeTest(QueryMeasurementMixin, TestCase):
    """What the paginator's COUNT of the alert-annotated service list carries."""

    fixtures = ['test_users.json', 'test_keywords.json', 'test_crs.json',
                'test_wms.json']

    def counts(self, params):
        status, _body, queries = self.request(
            '/api/registry/wms', user='user', **params)
        self.assertEqual(status, 200)
        counts = count_statements(queries, 'registry_webmapservice')
        self.assertTrue(
            counts,
            f'the paginator asked no COUNT over the services; queries per '
            f'table: {table_counter(queries)}')
        return counts

    def assertNoDerivation(self, sqls):
        for sql in sqls:
            for table in DERIVATION_TABLES:
                self.assertNotIn(
                    table, sql.lower(),
                    msg='the COUNT re-executes the alert derivation '
                        f'(names {table}); count of a derivation-free answer '
                        f'is plain by #1424: {sql[:400]}')

    def test_displaying_alerts_keeps_the_derivation_out_of_the_count(self):
        # QuerySet.count drops the SELECT annotations, so the subqueries of
        # the shown attributes never reach the paginator's COUNT
        self.assertNoDerivation(
            self.counts({'fields[WebMapService]': 'title,has_alert'}))

    def test_sorting_by_an_alert_keeps_the_derivation_out_of_the_count(self):
        # the sort column IS a derivation, so the page orders by the
        # subqueries - the COUNT of the same queryset stays free of them
        self.assertNoDerivation(self.counts({
            'fields[WebMapService]': 'title,has_alert',
            'sort': 'has_alert'}))

    def test_searching_with_alerts_displayed_keeps_the_count_free(self):
        # the search answers through its own EXISTS, which joins the keyword
        # relation and the text columns - no monitoring or update table
        counts = self.counts({
            'fields[WebMapService]': 'title,has_alert',
            'filter[search]': 'map'})
        self.assertNoDerivation(counts)

    def test_filtering_by_an_alert_asks_the_derivation_exactly_once(self):
        # filter[has_alert] IS the derivation as a condition, so the COUNT's
        # WHERE legitimately carries the subqueries - pinned present, and
        # pinned as ONE statement: the number is answered once over the
        # whole filtered set, never re-evaluated per row or per page
        counts = self.counts({
            'fields[WebMapService]': 'title,has_alert',
            'filter[has_alert]': 'true'})
        self.assertEqual(
            len(counts), 1,
            f'the alert filter answered {len(counts)} COUNT statements; the '
            'derivation in the WHERE may be asked exactly once')
        self.assertTrue(
            any(table in counts[0].lower() for table in DERIVATION_TABLES),
            'the alert filter COUNT lost the derivation which is the '
            f'meaning of the filter: {counts[0][:400]}')


class ServiceAlertListCountShapeTest(QueryMeasurementMixin, TestCase):
    """The cross-service list reads the stored projection of the alerts (#1030)."""

    fixtures = ['test_users.json', 'test_keywords.json', 'test_crs.json',
                'test_wms.json']

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # the scoped read: the caller has to see the services behind the
        # alert rows (collect_service_alerts asks the view permission per
        # kind of service), and rows the caller may not see must not inflate
        # the answer either - both are the shape this endpoint counts over
        for pk in (WMS_ONE, WMS_TWO):
            assign_perm('registry.view_webmapservice', cls.user,
                        WebMapService.objects.get(pk=pk))
        # the stored rows, in the shape the refresh writes them; the ids
        # name this module so a reuse of a committed row is impossible
        cls.seed_alert('1478-list-one', WMS_ONE, 'error')
        cls.seed_alert('1478-list-two-a', WMS_TWO, 'error')
        cls.seed_alert('1478-list-two-b', WMS_TWO, 'warning')

    @classmethod
    def seed_alert(cls, alert_id, service, severity):
        return ServiceAlert.objects.update_or_create(
            id=alert_id,
            defaults=dict(
                severity=severity,
                category='monitoring_failed',
                message=f'agent {alert_id}',
                service_type='WebMapService',
                service=service,
                service_title='WMS of #1478',
                resource_type='WebMapServiceMonitoringRun',
                resource_id='1',
                target_path=f'/api/registry/wms/{service}'))

    def test_the_count_names_the_stored_rows_only(self):
        status, _body, queries = self.request(
            '/api/registry/service-alerts', user='user')
        self.assertEqual(status, 200)
        counts = count_statements(queries, 'registry_servicealert')
        self.assertTrue(
            counts,
            f'the paginator asked no COUNT over the alert rows; queries per '
            f'table: {table_counter(queries)}')
        for sql in counts:
            for table in DERIVATION_TABLES:
                self.assertNotIn(
                    table, sql.lower(),
                    msg='the alert list re-derived the alerts instead of '
                        f'reading the stored rows ({table}): {sql[:400]}')

    def test_the_answer_does_not_grow_with_alert_rows(self):
        # one service holds two alert rows, the other one - the reduction
        # asks the smaller answer over the same statements. The scope of
        # collect_service_alerts resolves the ContentType of every service
        # kind once per process (guardian caches it), so the FIRST request
        # of the test pays three django_content_type queries which the
        # second one never sees: without this unmeasured warm-up the
        # two-request comparison would attribute those three queries to the
        # rows of the first arm, red or green by suite order
        self.request('/api/registry/service-alerts', user='user')
        self.assertQueriesIndependentOfRows(
            '/api/registry/service-alerts', user='user',
            single={'filter[service]': WMS_ONE})


class MetadataRelationSearchCountShapeTest(QueryMeasurementMixin, TestCase):
    """What the five LIKE joins of the relation search do to the COUNT."""

    fixtures = ['test_users.json', 'test_keywords.json', 'test_crs.json',
                'test_csw.json', 'test_datasetmetadata.json']

    def test_the_search_count_is_one_statement_of_primary_key_joins(self):
        status, _body, queries = self.request(
            '/api/registry/metadata-relations', user='user',
            **{'filter[search]': 'niederschlag'})
        self.assertEqual(status, 200)
        counts = count_statements(queries, 'registry_metadatarelation')
        self.assertEqual(
            len(counts), 1,
            f'the relation search answered {len(counts)} COUNT statements; '
            'one over the five joined titles is the measured shape')
        sql = counts[0].lower()
        self.assertNotIn(
            'distinct', sql,
            'the relation COUNT gained a DISTINCT - the five joins are '
            f"primary key joins, there is nothing to deduplicate: {sql[:400]}")
        for column, table in RELATION_SEARCH_JOINS:
            self.assertIn(
                f'left outer join "{table}"', sql)
            self.assertIn(
                f'"registry_metadatarelation"."{column}" = "{table}"."id"',
                sql,
                msg=f'the join over {table} is no longer the one-to-one '
                    'primary key join the measured cost verdict rests on')
        self.assertLessEqual(
            len(page_statements(queries, 'registry_metadatarelation')), 1,
            'the relation search asked more than one page of the joins')

    def test_the_list_does_not_grow_with_rows(self):
        # the endpoint's own shape stays free of per-row reads - reduced
        # through the dataset relation, which the filters answer while the
        # id is not a filter of this endpoint. Warm-up for the same
        # ContentType cache reason as in the alert list test above
        self.request('/api/registry/metadata-relations', user='user')
        self.assertQueriesIndependentOfRows(
            '/api/registry/metadata-relations', user='user',
            single={'filter[dataset_metadata]': DATASET_RELATION})
