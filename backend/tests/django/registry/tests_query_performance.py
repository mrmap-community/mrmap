"""Measure and pin the database query behaviour of the JSON:API endpoints.

The JSON:API endpoints answer with a lot of related resources, so the interesting
question is not only *how many* queries a request makes, but whether that number
grows with the number of rows in the response. ``backend/tests/AGENTS.md``
describes the two properties that are asserted here: a relation that is loaded
once for every row of the answer, and the measured budget of a request.
"""
import json
import re
from collections import Counter
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connections
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import resolve
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.viewsets import GenericViewSet

from extras.viewsets import ObjectPermissionCheckerViewSetMixin


JSONAPI = 'application/vnd.api+json'

TABLE_RE = re.compile(
    r'(?:FROM|JOIN|INSERT INTO|UPDATE|DELETE FROM)\s+"?([a-zA-Z_0-9]+)"?', re.IGNORECASE)

COUNT_RE = re.compile(r'COUNT\(\*\).*?FROM\s+"([a-zA-Z_0-9]+)"', re.IGNORECASE)


def table_counter(queries):
    """Count the captured sql by the main table it touches.

    Used in the failure messages so a red test names the table that is queried
    over and over again, instead of only complaining about a number.
    """
    counter = Counter()
    for query in queries:
        tables = TABLE_RE.findall(query['sql'])
        counter[tables[0] if tables else query['sql'][:32]] += 1
    return counter


class QueryMeasurementMixin:
    """Sends requests through the resolved view and counts the queries."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.get(username='User1')
        # an anonymous request is mapped to the user named "AnonymousUser", which a
        # TransactionTestCase running earlier in the same process has flushed, see
        # backend/tests/AGENTS.md
        get_user_model().objects.get_or_create(username='AnonymousUser')

    def request(self, path, user='anonymous', **params):
        """Call the view behind ``path``, return (status, body, queries).

        The view is resolved and called directly so that the session and login
        queries of the test client are not part of the measurement.
        """
        request = APIRequestFactory().get(path, params, HTTP_ACCEPT=JSONAPI)
        if user == 'user':
            force_authenticate(request, user=self.user)
        elif user != 'anonymous':
            raise ValueError(user)
        callback, _, kwargs = resolve(path)
        with CaptureQueriesContext(connections['default']) as context:
            response = callback(request, **kwargs)
            if not response.is_rendered:
                response.render()
        body = json.loads(response.content) if response.content else {}
        return response.status_code, body, context

    def ids_of(self, body):
        return [row['id'] for row in (body.get('data') or [])]

    def assertQueriesIndependentOfRows(self, path, user='user', single=None,
                                       **params):
        """A relation may not be loaded once for every row of the answer.

        The same endpoint is measured once with all rows of the fixture and once
        with a single row. A table that is queried in the big answer as often as
        the big answer has more rows than the small one is loaded per object.

        The table of the resource of the endpoint is not looked at: the query that
        counts the rows of the answer and the queries that collect the ids for the
        permission checker are made for the resource itself and their number does
        not say anything about relations. The absolute number of queries of a
        request is pinned by ``assertQueriesDoNotExceed``.
        """
        _status, body, many = self.request(path, user=user, **params)
        ids = self.ids_of(body)
        if len(ids) < 2:
            self.fail(
                f'{path} answers with {len(ids)} rows; at least two are needed '
                'to see a query that is made for every row')
        single_params = dict(params, **(single or {'filter[id]': ids[0]}))
        _status, single_body, one = self.request(path, user=user, **single_params)
        if len(self.ids_of(single_body)) != 1:
            self.fail(
                f'{single_params} did not reduce {path} to one row but to '
                f'{len(self.ids_of(single_body))}; choose another param for single')
        many_tables = table_counter(many)
        one_tables = table_counter(one)
        resource_table = next((
            COUNT_RE.search(query['sql']).group(1) for query in many
            if COUNT_RE.search(query['sql'])), None)
        per_row = [(table, times, times - one_tables.get(table, 0))
                   for table, times in many_tables.most_common()
                   if table != resource_table
                   and times - one_tables.get(table, 0) >= len(ids) - 1]
        self.assertFalse(
            per_row,
            msg=(f'{path} made {len(many)} queries for {len(ids)} rows while one '
                 f'row made {len(one)}. These tables are queried once for nearly '
                 f'every row (table, queries, added queries): {per_row}. Queries '
                 f'per table of one row: {one_tables.most_common()}'))

    def assertQueriesDoNotExceed(self, expected, path, user='user', **params):
        """Pin the absolute number of queries one request of an endpoint makes."""
        _status, _body, queries = self.request(path, user=user, **params)
        self.assertLessEqual(
            len(queries), expected,
            msg=(f'{path} made {len(queries)} queries, {expected} allowed. '
                 f'Queries per table: {table_counter(queries)}'))

    def assertIncludeAddsAtMost(self, extra, include, path, user='user'):
        """An include may add queries, but a fixed number and not per row."""
        _status, _body, plain = self.request(path, user=user)
        _status, _body, included = self.request(
            path, user=user, **{'include': include})
        self.assertLessEqual(
            len(included) - len(plain), extra,
            msg=(f'{path}?include={include} made {len(included)} queries while '
                 f'without include {len(plain)} were made, at most {extra} more '
                 f'were allowed. Queries per table: '
                 f'{table_counter(included)}'))

    def assertNoSlowObjectPermissions(self, path, user='user', **params):
        """No object may fall back to the per object permission check.

        ``extras.serializers.ObjectPermissionCheckerSerializer`` warns when the
        view did not hand it a prefetched permission checker; every object that
        reaches the fallback costs at least one query.
        """
        with self.assertNoLogs('MrMap.root', level='WARNING'):
            self.request(path, user=user, **params)


class SchemaPermissionContextTest(SimpleTestCase):
    def test_schema_view_skips_object_permission_prefetch(self):
        class PermissionViewSet(ObjectPermissionCheckerViewSetMixin, GenericViewSet):
            queryset = get_user_model().objects.all()

        view = PermissionViewSet()
        view.request = APIRequestFactory().get('/')
        view.format_kwarg = None
        view.swagger_fake_view = True

        with patch('extras.viewsets.ObjectPermissionChecker') as checker, \
                patch.object(view, 'filter_queryset') as filter_queryset:
            context = view.get_serializer_context()

        checker.assert_not_called()
        filter_queryset.assert_not_called()
        self.assertNotIn('perm_checker', context)


SERVICES = ["test_users.json", "test_keywords.json", "test_crs.json",
            "test_wms.json", "test_wfs.json", "test_allowed_wms_operation.json"]


class ServiceListQueryPerformance(QueryMeasurementMixin, TestCase):
    """The lists of the registry must not answer with one query per row."""

    fixtures = SERVICES

    def test_webmapservice_list_does_not_grow_with_rows(self):
        self.assertQueriesIndependentOfRows('/api/registry/wms')

    def test_layer_list_does_not_grow_with_rows(self):
        self.assertQueriesIndependentOfRows('/api/registry/layers')

    def test_webfeatureservice_list_does_not_grow_with_rows(self):
        self.assertQueriesIndependentOfRows('/api/registry/wfs')

    def test_featuretype_list_does_not_grow_with_rows(self):
        self.assertQueriesIndependentOfRows('/api/registry/featuretypes')

    def test_sparse_fieldset_of_last_modified_by_answers(self):
        """A sparse fieldset that only asks for the history of an object.

        ``extras.viewsets.HistoryInformationViewSetMixin`` built the prefetch for
        ``last_modified_by`` out of the variables of the ``created_by`` prefetch,
        which is not even defined when only the last one runs.
        """
        for path, resource in (
                ('/api/registry/wms', 'WebMapService'),
                ('/api/registry/layers', 'Layer'),
                ('/api/registry/wfs', 'WebFeatureService'),
                ('/api/registry/featuretypes', 'FeatureType')):
            with self.subTest(path=path):
                status, _body, _queries = self.request(
                    path, **{'fields[%s]' % resource: 'lastModifiedBy'})
                self.assertEqual(status, 200)

    def test_sparse_fieldset_of_a_relation_stays_prefetched(self):
        """Asking for one relation must not turn its prefetch into per row work.

        ``extras.viewsets.PreloadNotIncludesMixin`` compares the sparse fieldset
        with the keys of ``prefetch_for_not_includes``, so a relation that is
        named in the fieldset has to keep its narrow prefetch.
        """
        self.assertQueriesIndependentOfRows(
            '/api/registry/wms',
            **{'fields[WebMapService]': 'title,webMapServiceMonitoringSettings'})


class IncludedServiceQueryPerformance(QueryMeasurementMixin, TestCase):
    """An included service is serialized with the serializer of the service."""

    fixtures = SERVICES

    def test_layer_list_with_service_does_not_grow_with_rows(self):
        self.assertQueriesIndependentOfRows(
            '/api/registry/layers', **{'include': 'service'})

    def test_layer_list_with_service_and_operation_urls_grows_not(self):
        self.assertQueriesIndependentOfRows(
            '/api/registry/layers', **{'include': 'service.operationUrls'})

    def test_layer_list_has_a_prefetched_permission_checker(self):
        """The lists hand their prefetched checker to the serializer.

        ``extras.viewsets.ObjectPermissionCheckerViewSetMixin`` builds one checker
        for the objects of the page, so no object of the answer may fall back to
        the per object permission check of
        ``extras.serializers.ObjectPermissionCheckerSerializer``.
        """
        self.assertNoSlowObjectPermissions('/api/registry/layers')
        self.assertNoSlowObjectPermissions('/api/registry/wms')

    def test_included_service_is_accessible(self):
        """An included resource still answers whether the user may see it.

        The json:api renderer creates the serializers of included resources with
        the context of the renderer, which knows the view but not the permission
        checker that the view added to the serializer context.
        ``extras.serializers.ObjectPermissionCheckerSerializer`` falls back to a
        checker that is shared for the whole request. It is still slower than the
        prefetched checker of the view, because it determines the permissions of
        every included object once, but it does not repeat the check for every
        row that refers to the same service.
        """
        status, body, _queries = self.request(
            '/api/registry/layers', **{'include': 'service'})
        self.assertEqual(status, 200)
        included = [resource for resource in body.get('included', [])
                    if resource['type'] == 'WebMapService']
        self.assertTrue(included, msg=f'no included service in {body}')
        for resource in included:
            self.assertIn('isAccessible', resource['attributes'])

    def test_included_service_still_answers_its_relations(self):
        """Narrowing a relation to its ids must not remove it from the answer.

        The relations of an included service are answered as related resources, so
        they are prefetched with only their id and the column that points back to the
        service. The service itself is answered with its attributes.
        """
        _status, body, _queries = self.request(
            '/api/registry/layers', **{'include': 'service'})
        services = [resource for resource in body.get('included', [])
                    if resource['type'] == 'WebMapService']
        self.assertTrue(services, msg=f'no included service in {body}')
        for service in services:
            self.assertTrue(service['attributes']['title'])
        for relation in ('keywords', 'operationUrls', 'layers'):
            # not every service of the fixture has every relation, so at least one of
            # them must answer it
            answered = [service['id'] for service in services
                        if service.get('relationships', {}).get(
                            relation, {}).get('data')]
            self.assertTrue(
                answered,
                msg=f'no included service answers {relation} of '
                    f'{[service["id"] for service in services]}: '
                    f'{[service.get("relationships") for service in services]}')

    def test_included_operation_url_is_answered_in_full(self):
        """An operation url that is asked for is serialized, not only linked.

        Under the key "service" the operation urls are prefetched by their id only,
        under the key "service.operation_urls" they are prefetched in full. A second
        prefetch of the same relation name would override the full one, so the
        attributes of an included operation url are asserted here.
        """
        _status, body, _queries = self.request(
            '/api/registry/layers', **{'include': 'service.operationUrls'})
        operation_urls = [
            resource for resource in body.get('included', [])
            if resource['type'] == 'WebMapServiceOperationUrl']
        self.assertTrue(
            operation_urls, msg=f'no included operation urls in {body}')
        with_mime_types = []
        for operation_url in operation_urls:
            self.assertTrue(operation_url['attributes']['url'])
            mime_types = operation_url.get('relationships', {}).get(
                'mimeTypes', {}).get('data')
            if mime_types:
                with_mime_types.append(operation_url)
        self.assertTrue(
            with_mime_types,
            msg='no included operation url answers a mime type; the mime types are '
                'prefetched by id only, so this is where a broken prefetch shows up')

    def test_included_feature_type_service_still_answers_its_relations(self):
        """The same narrowing as for a layer, for the relations of a web feature service.

        The list of relations that are only linked is written twice, once for the web
        map service and once for the web feature service, so it is asserted for both.
        """
        _status, body, _queries = self.request(
            '/api/registry/featuretypes', **{'include': 'service'})
        services = [resource for resource in body.get('included', [])
                    if resource['type'] == 'WebFeatureService']
        self.assertTrue(services, msg=f'no included service in {body}')
        for service in services:
            self.assertTrue(service['attributes']['title'])
        for relation in ('featuretypes', 'operationUrls'):
            answered = [service['id'] for service in services
                        if service.get('relationships', {}).get(
                            relation, {}).get('data')]
            self.assertTrue(
                answered,
                msg=f'no included service answers {relation} of '
                    f'{[service["id"] for service in services]}')

    def test_include_of_service_adds_a_fixed_number_of_queries(self):
        """An included service costs a fixed number of queries per service.

        The measured twelve are the relations the serializer of the service
        answers: its keywords, languages, layers, operation urls, allowed
        operations, proxy setting, monitoring and update settings, its contacts,
        its history for ``createdAt`` and ``lastModifiedAt`` and the object
        permissions of the two services of the fixture.
        """
        self.assertIncludeAddsAtMost(
            12, 'service', '/api/registry/layers')


class CatalogueServiceQueryPerformance(QueryMeasurementMixin, TestCase):
    """The CSW list serializes the harvesting state of every service."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_csw.json"]

    def test_csw_list_does_not_grow_with_rows(self):
        self.assertQueriesIndependentOfRows('/api/registry/csw')

    def test_csw_list_with_keywords_does_not_grow_with_rows(self):
        self.assertQueriesIndependentOfRows(
            '/api/registry/csw', **{'include': 'keywords'})

    def test_include_of_harvesting_jobs_answers(self):
        """``include=harvestingJobs`` used to answer with a server error.

        The relation was prefetched twice with two different querysets, which
        django rejects while building the queryset of the request.
        """
        status, _body, _queries = self.request(
            '/api/registry/csw', **{'include': 'harvestingJobs'})
        self.assertEqual(status, 200)

    def test_sparse_fieldset_of_last_modified_by_answers(self):
        status, _body, _queries = self.request(
            '/api/registry/csw',
            **{'fields[CatalogueService]': 'lastModifiedBy'})
        self.assertEqual(status, 200)


class HarvestingQueryPerformance(QueryMeasurementMixin, TestCase):
    """The harvesting jobs know the service and the schedule they belong to."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_csw.json"]

    def test_harvesting_job_list_does_not_grow_with_rows(self):
        self.assertQueriesIndependentOfRows(
            '/api/registry/harvesting/harvesting-jobs')

    def test_harvesting_job_list_with_service_does_not_grow_with_rows(self):
        self.assertQueriesIndependentOfRows(
            '/api/registry/harvesting/harvesting-jobs',
            **{'include': 'service'})

    def test_harvesting_job_throughput_does_not_grow_with_rows(self):
        """the throughput of a run is summed by the aggregation of its durations

        The records of a run are aggregated once for the durations of the run
        already, so the records per minute which #692 answers out of them add no
        second aggregation of the harvested records.
        """
        self.assertQueriesIndependentOfRows(
            '/api/registry/harvesting/harvesting-jobs',
            **{'fields[HarvestingJob]': 'id,max_step_size,records_per_minute'})


class MetadataQueryPerformance(QueryMeasurementMixin, TestCase):
    """A metadata record serializes a dozen relations at once."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_csw.json", "test_datasetmetadata.json"]

    def test_dataset_metadata_list_does_not_grow_with_rows(self):
        self.assertQueriesIndependentOfRows('/api/registry/dataset-metadata')

    def test_dataset_metadata_list_with_keywords_does_not_grow(self):
        self.assertQueriesIndependentOfRows(
            '/api/registry/dataset-metadata', **{'include': 'keywords'})


class MapContextQueryPerformance(QueryMeasurementMixin, TestCase):
    """A mapcontext layer knows its mapcontext, its tree and its parent."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json", "test_mapcontext.json"]

    def test_mapcontext_list_does_not_grow_with_rows(self):
        self.assertQueriesIndependentOfRows('/api/registry/mapcontexts')

    def test_mapcontextlayer_list_does_not_grow_with_rows(self):
        self.assertQueriesIndependentOfRows('/api/registry/mapcontextlayers')

    def test_mapcontextlayer_list_with_rendering_layer_does_not_grow(self):
        self.assertQueriesIndependentOfRows(
            '/api/registry/mapcontextlayers', **{'include': 'renderingLayer'})


class HistoryQueryPerformance(QueryMeasurementMixin, TestCase):
    """The historical endpoints answer the changes of a service.

    How many history rows a service has depends on what other tests did with it,
    so the cost of these endpoints is only meaningful relative to the number of
    rows the answer has. The ``id`` of a history record in the answer is its
    ``history_id``, while the ``id`` filter of the endpoint filters the id of the
    changed object, so the single row is asked for with the page size.
    """

    fixtures = SERVICES

    ONE_ROW = {'page[size]': '1'}

    def test_historical_wms_list_does_not_grow_with_rows(self):
        self.assertQueriesIndependentOfRows(
            '/api/registry/historical-wms', single=self.ONE_ROW)

    def test_historical_wms_include_history_relation_does_not_grow(self):
        self.assertQueriesIndependentOfRows(
            '/api/registry/historical-wms', single=self.ONE_ROW,
            **{'include': 'historyRelation'})

    def test_historical_wms_include_history_user_does_not_grow(self):
        self.assertQueriesIndependentOfRows(
            '/api/registry/historical-wms', single=self.ONE_ROW,
            **{'include': 'historyUser'})
