"""Measure and pin the database query behaviour of the JSON:API endpoints.

The JSON:API endpoints answer with a lot of related resources, so the interesting
question is not only *how many* queries a request makes, but whether that number
grows with the number of rows in the response. ``backend/tests/AGENTS.md``
describes the two properties that are asserted here: a relation that is loaded
once for every row of the answer, and the measured budget of a request.
"""
import itertools
import json
import re
from collections import Counter
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connections
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import resolve
from django.utils.timezone import now
from registry.enums.harvesting import HarvestingPhaseEnum as Phase
from registry.models.harvest import HarvestingJob, TemporaryMdMetadataFile
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.viewsets import GenericViewSet

from extras.viewsets import ObjectPermissionCheckerViewSetMixin
from registry.enums.harvesting import CollectingStatenEnum as State
from registry.managers.havesting import (METADATA_RECORD_COUNTS,
                                         metadata_count_annotation)
from registry.models.harvest import HarvestedMetadataRelation, HarvestingJob
from registry.models.metadata import (DatasetMetadataRecord, MetadataContact,
                                      ServiceMetadataRecord)
from registry.models.service import CatalogueService


JSONAPI = 'application/vnd.api+json'

TABLE_RE = re.compile(
    r'(?:FROM|JOIN|INSERT INTO|UPDATE|DELETE FROM)\s+"?([a-zA-Z_0-9]+)"?', re.IGNORECASE)

COUNT_RE = re.compile(r'COUNT\(\*\).*?FROM\s+"([a-zA-Z_0-9]+)"', re.IGNORECASE)

# the statement a paginator of DRF asks for the number of rows of an answer
COUNT = 'COUNT(*) AS "__count"'


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


def plan_scans(sql, table):
    """Every node of the plan of ``sql`` which reads ``table``."""
    with connections['default'].cursor() as cursor:
        cursor.execute('EXPLAIN (ANALYZE, FORMAT JSON) ' + sql)
        plan = cursor.fetchone()[0][0]['Plan']
    pending = [plan]
    scans = []
    while pending:
        node = pending.pop()
        pending.extend(node.get('Plans', []))
        if node.get('Relation Name') == table:
            scans.append(node)
    return scans


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

    def test_the_list_counts_its_rows_once(self):
        """The permission checker may not paginate the answer a second time.

        ``ObjectPermissionCheckerViewSetMixin`` used to filter and paginate the
        queryset again to learn which objects the answer shows, so every list
        answered the COUNT of its paginator twice (#1031).
        """
        _status, _body, queries = self.request('/api/registry/csw')
        counts = [q['sql'] for q in queries if COUNT in q['sql']]
        self.assertEqual(len(counts), 1,
                         [sql[:90] for sql in counts])

    def test_the_list_does_not_prefetch_the_harvested_records(self):
        """A relation no serializer answers must not be prefetched at all.

        The list prefetched the harvested records of every catalogue by their
        id although no field of the answer reads them - with the records of a
        big deployment hundreds of thousands of rows loaded for nothing
        (#1031). Only the page query itself may read them, for the harvesting
        statistics it answers.
        """
        from registry.views.service import CatalogueServiceViewSetMixin
        relations = [
            getattr(prefetch, 'prefetch_through', prefetch)
            for prefetches in CatalogueServiceViewSetMixin.prefetch_for_not_includes.values()
            for prefetch in prefetches]
        self.assertNotIn(
            'registry_datasetmetadatarecord_metadata_records', relations)

    def test_the_extent_is_aggregated_once_for_the_whole_page(self):
        """The coverage of the page is read by one grouped query per source.

        Aggregated as an annotation of the page query, the ``ST_Union`` and the
        ``COUNT(DISTINCT)`` of the coverage ran once per catalogue and were
        repeated by the permission checker a second time per page (#1031).
        """
        _status, _body, queries = self.request(
            '/api/registry/csw', user='user',
            **{'fields[CatalogueService]':
               'id,title,extent,element_count'})
        unions = [q['sql'] for q in queries if 'ST_Union' in q['sql']]
        # one grouped query per kind of harvested record, not one per row
        self.assertLessEqual(len(unions), 2, unions)
        self.assertFalse([sql for sql in unions if COUNT in sql],
                         'the count of the rows runs the coverage aggregation')
        self.assertEqual(
            1, len([q['sql'] for q in queries if COUNT in q['sql']]),
            'the page answers one count of its rows')


class HarvestingQueryPerformance(QueryMeasurementMixin, TestCase):
    """The harvesting jobs know the service and the schedule they belong to."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_csw.json"]

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.job = HarvestingJob.objects.order_by('pk').first()
        HarvestingJob.objects.filter(pk=cls.job.pk).update(
            total_records=4, max_step_size=1, phase=Phase.RECORDS_TO_DB)
        # Recovery files of an older job of this same catalogue must also stay
        # outside the work done for a single page, not just other catalogues.
        backlog = HarvestingJob(service_id=cls.job.service_id,
                                phase=Phase.ABORTED, done_at=now())
        HarvestingJob.objects.bulk_create([backlog])
        TemporaryMdMetadataFile.objects.bulk_create([
            TemporaryMdMetadataFile(job=backlog) for _ in range(2048)
        ] + [
            TemporaryMdMetadataFile(job=cls.job, has_import_error=False),
            TemporaryMdMetadataFile(job=cls.job, has_import_error=True),
            TemporaryMdMetadataFile(job=None),
        ])
        with connections['default'].cursor() as cursor:
            cursor.execute('ANALYZE registry_temporarymdmetadatafile')

    def assertTemporaryFileScansAreBounded(self, sql):
        """Query counts alone cannot detect one query aggregating the backlog."""
        scans = self.temporaryFileScans(sql)
        self.assertTrue(scans, sql)
        for node in scans:
            condition = node.get('Index Cond', node.get('Recheck Cond', ''))
            self.assertIn('job_id', condition, node)
            self.assertLessEqual(node['Actual Rows'], 2, node)
            self.assertLessEqual(node['Actual Loops'], 1, node)

    def test_process_info_counts_only_the_selected_job(self):
        with CaptureQueriesContext(connections['default']) as queries:
            job = HarvestingJob.objects.with_process_info().get(pk=self.job.pk)
        self.assertEqual(job.unhandled_records_count, 1)
        self.assertEqual(job.import_error_count, 1)
        self.assertEqual(job.records_count, 2)
        self.assertEqual(job.total_steps, 9)
        self.assertEqual(job.done_steps, 7)
        self.assertEqual(job.progress, 77.78)
        self.assertEqual(len(queries), 1)
        self.assertTemporaryFileScansAreBounded(queries[0]['sql'])

    def countSubquery(self, sql, name):
        """The subquery of the statement which answers one count of a job."""
        marker = f'AS "{name}" FROM "registry_temporarymdmetadatafile"'
        start = sql.index(marker) + len(marker)
        return sql[sql.index('WHERE', start):sql.index(' GROUP BY', start)]

    def test_each_count_is_answered_by_the_files_it_counts(self):
        """The property a count is about narrows the range of its own subquery.

        The progress of a job asked the files of that job three times: for all of
        them, for the ones without an error and for the ones with one. Each of the
        two counts which are about some of the files put its ``COUNT(...) FILTER``
        in front of the range of *all* files of the job, so a job whose recovery
        backlog is the whole table read the entries of all 411,518 files it had
        left behind to answer how many of them had failed - ~200 ms of the 564 ms
        of the detail request which reported this, again on every poll of the job
        screen (#886).

        A filter which selects files is a range and so is answered by the new index
        over the job and its error flag; a FILTER in front of a range is not, it is
        applied to every entry of it. The number of aggregations is not asserted:
        the steps of the progress re-inline the count of all files and how often
        the planner folds those sublinks is its own decision. That every scan which
        runs stays inside the files of the selected job is what
        ``assertTemporaryFileScansAreBounded`` keeps, and the values of the three
        counts are asserted in every phase by
        ``test_sparse_progress_fields_and_manager_agree_in_each_phase``.
        """
        with CaptureQueriesContext(connections['default']) as queries:
            HarvestingJob.objects.with_process_info().get(pk=self.job.pk)
        sql = queries[0]['sql']
        self.assertNotIn('FILTER (WHERE', sql,
                         'a count aggregates all files of the job and picks the '
                         'ones it is about out of the aggregation')
        for name, negated in [('unhandled_records_count', True),
                              ('import_error_count', False)]:
            where = self.countSubquery(sql, name)
            self.assertIn('"has_import_error"', where, name)
            self.assertEqual('NOT' in where, negated, where)

    def test_the_failed_files_of_a_job_have_an_index_of_their_own(self):
        """The count of the files which failed is answered out of their entries."""
        with connections['default'].cursor() as cursor:
            cursor.execute(
                "SELECT indexdef FROM pg_indexes WHERE tablename = "
                "'registry_temporarymdmetadatafile'")
            definitions = [row[0] for row in cursor.fetchall()]
        self.assertTrue(
            [definition for definition in definitions
             if definition.endswith('(job_id, has_import_error)')],
            'the files of a job which failed to import are no range of their own, '
            'so their count reads every file of the job (#886)')

    def temporaryFileScans(self, sql):
        """Every node of the plan which reads the files of a job."""
        return plan_scans(sql, 'registry_temporarymdmetadatafile')

    def test_paginated_progress_does_not_aggregate_recovery_files(self):
        for path, filters in [
            ('/api/registry/harvesting/harvesting-jobs',
             {'filter[service.id]': str(self.job.service_id)}),
            (f'/api/registry/csw/{self.job.service_id}/harvesting-jobs', {}),
        ]:
            with self.subTest(path=path):
                status, body, queries = self.request(path, **filters, **{
                    'page[size]': 1, 'sort': 'id',
                    'fields[HarvestingJob]':
                        'id,progress,totalSteps,doneSteps,unhandledRecordsCount,importErrorCount',
                })
                self.assertEqual(status, 200, body)
                self.assertEqual(self.ids_of(body), [str(self.job.pk)])
                self.assertEqual(body['data'][0]['attributes'], {
                    'progress': 77.78, 'totalSteps': 9, 'doneSteps': 7,
                    'unhandledRecordsCount': 1, 'importErrorCount': 1,
                })
                file_queries = [q['sql'] for q in queries
                                if 'registry_temporarymdmetadatafile' in q['sql']]
                self.assertEqual(len(file_queries), 1)
                self.assertTemporaryFileScansAreBounded(file_queries[0])

    def test_the_order_of_the_answer_does_not_count_files(self):
        """The number of rows of an answer is read without the progress of a run.

        The progress joined the sort offer of #1130 and it is no column of the row:
        it is read from the files a run left behind. The paginator asks for the number
        of rows before it takes the page, and an answer which orders its runs by that
        progress must not read the recovery backlog of every run it filters only to
        say how many there are - the order changes nothing about the number, and a run
        which was interrupted keeps its files for the recovery (#870, #885, #1130).

        The request names a statistics field as well, because it is the ``sums`` CTE
        which makes the view read the number of rows itself.
        """
        for path, filters in [
            ('/api/registry/harvesting/harvesting-jobs',
             {'filter[service.id]': str(self.job.service_id)}),
            (f'/api/registry/csw/{self.job.service_id}/harvesting-jobs', {}),
        ]:
            with self.subTest(path=path):
                status, body, queries = self.request(path, **filters, **{
                    'page[size]': 1, 'sort': '-progress',
                    'fields[HarvestingJob]': 'id,progress,newDatasetMetadataCount',
                })
                self.assertEqual(status, 200, body)
                self.assertEqual(self.ids_of(body), [str(self.job.pk)])
                self.assertEqual(body['meta']['pagination']['count'], 2)
                file_queries = [q['sql'] for q in queries
                                if 'registry_temporarymdmetadatafile' in q['sql']]
                self.assertEqual(
                    len(file_queries), 1,
                    'the number of rows reads the files of every run it counts, '
                    'although the order it was asked for is not part of that number')
                self.assertTemporaryFileScansAreBounded(file_queries[0])

    def test_sparse_progress_fields_and_manager_agree_in_each_phase(self):
        path = f'/api/registry/harvesting/harvesting-jobs/{self.job.pk}'
        fields = ['totalSteps', 'doneSteps', 'progress',
                  'unhandledRecordsCount', 'importErrorCount']
        for phase, done_steps, progress in [
            (Phase.PENDING, 0, 0.0),
            (Phase.GET_TOTAL_RECORDS_COUNT, 0, 0.0),
            (Phase.DOWNLOAD_RECORDS, 3, 33.33),
            (Phase.RECORDS_TO_DB, 7, 77.78),
            (Phase.COMPLETED, 9, 100.0),
            (Phase.ABORTED, 9, 100.0),
        ]:
            HarvestingJob.objects.filter(pk=self.job.pk).update(
                phase=phase, done_at=now() if phase >= Phase.COMPLETED else None)
            expected = dict(zip(fields, [9, done_steps, progress, 1, 1]))
            job = HarvestingJob.objects.with_process_info().get(pk=self.job.pk)
            self.assertEqual(job.done_steps, done_steps)
            self.assertEqual(job.progress, progress)
            for field in fields:
                with self.subTest(phase=phase, field=field):
                    status, body, queries = self.request(
                        path, **{'fields[HarvestingJob]': field})
                    self.assertEqual(status, 200, body)
                    self.assertEqual(body['data']['attributes'], {field: expected[field]})
                    if field == 'totalSteps':
                        self.assertFalse(any('registry_temporarymdmetadatafile' in q['sql']
                                             for q in queries))

    def test_job_without_files_answers_zero_counts(self):
        TemporaryMdMetadataFile.objects.filter(job=self.job).delete()
        path = f'/api/registry/harvesting/harvesting-jobs/{self.job.pk}'
        for total_records, phase, progress in [
            (None, Phase.PENDING, 0.0), (0, Phase.COMPLETED, 100.0),
        ]:
            with self.subTest(total_records=total_records):
                HarvestingJob.objects.filter(pk=self.job.pk).update(
                    total_records=total_records, phase=phase)
                job = HarvestingJob.objects.with_process_info().get(pk=self.job.pk)
                self.assertEqual(job.records_count, 0)
                self.assertEqual(job.unhandled_records_count, 0)
                self.assertEqual(job.import_error_count, 0)
                self.assertEqual(job.progress, progress)
                status, body, _queries = self.request(path, **{
                    'fields[HarvestingJob]': 'progress,unhandledRecordsCount,importErrorCount'})
                self.assertEqual(status, 200, body)
                self.assertEqual(body['data']['attributes'], {
                    'progress': progress, 'unhandledRecordsCount': 0, 'importErrorCount': 0})

    def test_a_count_whose_files_are_all_of_the_other_kind_answers_zero(self):
        """The empty range of a filtered count is the 0 its FILTER had counted.

        Moving the condition of a count into the WHERE of its subquery leaves a
        group without a single matching file with no row at all, where the
        aggregation of the whole range answered a 0. Both numbers of the progress
        are therefore answered for a job which only has files of one kind.
        """
        path = f'/api/registry/harvesting/harvesting-jobs/{self.job.pk}'
        for has_import_error, counts in [
            (True, {'unhandledRecordsCount': 0, 'importErrorCount': 2}),
            (False, {'unhandledRecordsCount': 2, 'importErrorCount': 0}),
        ]:
            TemporaryMdMetadataFile.objects.filter(
                job=self.job).update(has_import_error=has_import_error)
            with self.subTest(has_import_error=has_import_error):
                status, body, _queries = self.request(
                    path, **{'fields[HarvestingJob]':
                             'unhandledRecordsCount,importErrorCount'})
                self.assertEqual(status, 200, body)
                self.assertEqual(body['data']['attributes'], counts)

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

    def test_statistics_are_aggregated_once_per_request(self):
        """The number of rows of the answer may not materialize the statistics.

        The statistics of a job are bounded by the ``sums`` CTE, which aggregates the
        whole table of the harvested metadata relations into one row per job, and that
        row is joined ``LEFT OUTER``: it cannot answer more or fewer rows than the job
        table. The paginator asked the annotated queryset for its count, so the
        aggregation of the whole table cost two materializations per request - one
        overview of the deployment which reported this ran over 259,377 rows twice,
        1,081 ms and 12,222 ms of the 14 s the request logged (#885).
        """
        fields = 'id,newDatasetMetadataCount,recordsPerMinute,progress'
        status, page, queries = self.request(
            '/api/registry/harvesting/harvesting-jobs', **{
                'page[size]': 1, 'sort': 'id',
                'fields[HarvestingJob]': fields})
        self.assertEqual(status, 200, page)
        aggregated = [q['sql'] for q in queries if '"sums"' in q['sql']]
        self.assertEqual(len(aggregated), 1, [
            q['sql'][:90] for q in queries])
        self.assertNotIn(COUNT, aggregated[0],
                         'the statistics are materialized for the count')
        counts = [q['sql'] for q in queries if COUNT in q['sql']]
        self.assertTrue(counts, 'the page answers a count of its rows')
        self.assertFalse([q for q in counts if '"sums"' in q],
                         'the count runs the statistics aggregation')
        _status, all_of_them, _queries = self.request(
            '/api/registry/harvesting/harvesting-jobs',
            **{'fields[HarvestingJob]': fields})
        self.assertEqual(page['meta']['pagination']['count'],
                         len(all_of_them['data']),
                         'the count is the number of rows of the answer')

    def test_the_count_of_a_page_is_the_same_with_and_without_statistics(self):
        """The statistics of the jobs do not change how many of them there are."""
        answers = {}
        for fields in ('id',
                       'id,newDatasetMetadataCount,recordsPerMinute,progress'):
            status, body, _queries = self.request(
                '/api/registry/harvesting/harvesting-jobs', **{
                    'page[size]': 1, 'sort': 'id',
                    'fields[HarvestingJob]': fields})
            self.assertEqual(status, 200, body)
            # the links are not compared: they echo the fields of the request
            # they belong to and differ by design
            answers[fields] = (body['meta']['pagination'],
                               self.ids_of(body))
        without, with_ = answers['id'], answers[
            'id,newDatasetMetadataCount,recordsPerMinute,progress']
        self.assertGreater(without[0]['count'], 1,
                           'the page is smaller than the answer it belongs to')
        self.assertEqual(without[0], with_[0],
                         'the statistics answer a different number of jobs')
        self.assertEqual(without[1], with_[1],
                         'the page answers the same jobs with and without '
                         'the statistics')


class HarvestingRunCountersQueryPerformance(QueryMeasurementMixin, TestCase):
    """One run answers its record counters from the rows each counter counts.

    The screen of a run shows how many records it found new, updated, already
    existing and delivered twice, per kind of record, and it asks again every few
    seconds while the import of that very run writes those records. Answered as a
    ``COUNT(...) FILTER`` over the rows of the run, every one of those counters
    walked all of them: the detail request of a run with 411,633 relations logged
    5.85 s, and the same statement reached 12.2 s while the harvest was still
    writing the table - the screen which watches a harvest got slower the further
    the harvest had come (#1037).
    """

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_csw.json"]

    COUNTERS = ('newDatasetMetadataCount', 'updatedDatasetMetadataCount',
                'existingDatasetMetadataCount', 'duplicatedDatasetMetadataCount',
                'newServiceMetadataCount', 'updatedServiceMetadataCount',
                'existingServiceMetadataCount',
                'duplicatedServiceMetadataCount')

    # The records the measured run collected, per kind and state. `existing` of the
    # service records is answered by no row at all, because the empty range of a
    # counter is one of the answers a screen has to get.
    NEW = 12
    UPDATED = 7
    EXISTING = 5
    DUPLICATED = 3
    SERVICE_NEW = 2
    SERVICE_UPDATED = 1
    SERVICE_DUPLICATED = 1
    # A second run keeps the relation table bigger than the counters of the
    # measured one, as it is while a harvest writes it.
    OTHER_RUN_RELATIONS = 4_000
    # what one record of the measured run measured: the throughput of a run is
    # its records against the time they measured, so a minute of it is 20 records
    DOWNLOAD_DURATION = timedelta(seconds=1)
    PROCESSING_DURATION = timedelta(seconds=2)

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        service = CatalogueService.objects.order_by('pk').first()
        # bulk_create instead of save(): the save of a job of a catalogue starts
        # the harvest of that catalogue. All three carry a done_at because only one
        # unfinished job is allowed per catalogue, and the fixture's catalogue
        # already has one of its own.
        cls.job, cls.other, cls.empty = HarvestingJob.objects.bulk_create([
            HarvestingJob(service=service, phase=Phase.COMPLETED, done_at=now()),
            HarvestingJob(service=service, phase=Phase.ABORTED, done_at=now()),
            HarvestingJob(service=service, phase=Phase.COMPLETED, done_at=now()),
        ])
        contact = MetadataContact.objects.first()
        datasets = DatasetMetadataRecord.objects.bulk_create([
            DatasetMetadataRecord(
                title=f'Counter dataset {i}', metadata_contact=contact,
                dataset_contact=contact)
            for i in range(cls.NEW + cls.UPDATED + cls.EXISTING)
        ])
        services = ServiceMetadataRecord.objects.bulk_create([
            ServiceMetadataRecord(title=f'Counter service {i}',
                                  metadata_contact=contact)
            for i in range(cls.SERVICE_NEW + cls.SERVICE_UPDATED)
        ])
        # which records the run found in which state; a DUPLICATED relation may
        # name a record the run collected in another state as well
        states = {
            State.NEW: (datasets[:cls.NEW], services[:cls.SERVICE_NEW]),
            State.UPDATED: (datasets[cls.NEW:cls.NEW + cls.UPDATED],
                            services[cls.SERVICE_NEW:
                                     cls.SERVICE_NEW + cls.SERVICE_UPDATED]),
            State.EXISTING: (datasets[cls.NEW + cls.UPDATED:
                                      cls.NEW + cls.UPDATED + cls.EXISTING], ()),
            State.DUPLICATED: (datasets[:cls.DUPLICATED],
                               services[:cls.SERVICE_DUPLICATED]),
        }
        cls.expected = {
            'newDatasetMetadataCount': cls.NEW,
            'updatedDatasetMetadataCount': cls.UPDATED,
            'existingDatasetMetadataCount': cls.EXISTING,
            'duplicatedDatasetMetadataCount': cls.DUPLICATED,
            'newServiceMetadataCount': cls.SERVICE_NEW,
            'updatedServiceMetadataCount': cls.SERVICE_UPDATED,
            # the run collected no service record which the registry already had:
            # the range of that counter is empty and the counter answers its 0
            'existingServiceMetadataCount': 0,
            'duplicatedServiceMetadataCount': cls.SERVICE_DUPLICATED,
        }
        relations = [
            HarvestedMetadataRelation(
                harvesting_job=cls.job, collecting_state=state,
                download_duration=cls.DOWNLOAD_DURATION,
                processing_duration=cls.PROCESSING_DURATION,
                **{f'{kind}_metadata_record': record})
            for state, (found_datasets, found_services) in states.items()
            for kind, found in (('dataset', found_datasets),
                                ('service', found_services))
            for record in found
        ]
        filler = [
            HarvestedMetadataRelation(
                harvesting_job=cls.other, collecting_state=State.DUPLICATED,
                dataset_metadata_record=record)
            for record in itertools.islice(
                itertools.cycle(datasets), cls.OTHER_RUN_RELATIONS)
        ]
        HarvestedMetadataRelation.objects.bulk_create(relations + filler)
        with connections['default'].cursor() as cursor:
            cursor.execute('ANALYZE registry_harvestedmetadatarelation')

    def path(self, job=None):
        return f'/api/registry/harvesting/harvesting-jobs/{(job or self.job).pk}'

    def counterSubquery(self, sql, annotation):
        """The subquery of the statement which answers one counter of a run."""
        marker = f'AS "{annotation}" FROM "registry_harvestedmetadatarelation"'
        start = sql.index(marker)
        return sql[sql.rindex('(SELECT ', 0, start):sql.index(' GROUP BY', start)]

    def countersQuery(self, queries):
        """The one statement of the request which reads the harvested relations."""
        relation_queries = [query['sql'] for query in queries
                            if 'registry_harvestedmetadatarelation' in query['sql']]
        self.assertEqual(
            len(relation_queries), 1,
            'the counters of a run are answered by one statement, not once per '
            'counter: ' + str([sql[:90] for sql in relation_queries]))
        return relation_queries[0]

    def test_the_counters_answer_the_records_the_run_collected(self):
        status, body, _queries = self.request(
            self.path(), **{'fields[HarvestingJob]': ','.join(self.COUNTERS)})
        self.assertEqual(status, 200, body)
        self.assertEqual(body['data']['attributes'], self.expected)
        # the list of the runs of the catalogue answers the same numbers for the
        # same run - from the aggregation of the relation table, because a list
        # cannot answer the ranges of many runs at once (#1037)
        status, body, _queries = self.request(
            f'/api/registry/csw/{self.job.service_id}/harvesting-jobs',
            user='user',
            **{'fields[HarvestingJob]': ','.join(self.COUNTERS),
               'filter[id]': str(self.job.pk)})
        self.assertEqual(status, 200, body)
        rows = body.get('data') or []
        self.assertEqual(len(rows), 1, body)
        self.assertEqual(rows[0]['attributes'], self.expected)

    def test_a_run_without_records_answers_zero_counters(self):
        """The range of a counter may be empty, and then the counter answers 0."""
        status, body, _queries = self.request(
            self.path(self.empty),
            **{'fields[HarvestingJob]': ','.join(self.COUNTERS)})
        self.assertEqual(status, 200, body)
        self.assertEqual(body['data']['attributes'],
                         {name: 0 for name in self.COUNTERS})

    def test_each_counter_is_answered_by_the_rows_it_counts(self):
        """No counter of a run picks its records out of an aggregation of them all.

        The statement which answers the counters of one run holds one subquery per
        counter, and the WHERE of each of them is the range the counter is about:
        the job, the state the import decided and the column which carries the kind
        of record. The count itself is over ``*``, so nothing outside that range is
        read - which is what lets the database answer the counter from the index
        over the range and leave the table alone while its rows are being written.
        """
        _status, _body, queries = self.request(
            self.path(), **{'fields[HarvestingJob]': ','.join(self.COUNTERS)})
        sql = self.countersQuery(queries)
        self.assertNotIn('"sums"', sql,
                         'the counters of one run materialize the aggregation of '
                         'the relations of every run')
        for name, (kind, state) in METADATA_RECORD_COUNTS.items():
            subquery = self.counterSubquery(
                sql, metadata_count_annotation(kind, state))
            self.assertIn('COUNT(*)', subquery, name)
            self.assertNotIn('COUNT("id")', subquery, name)
            self.assertNotIn('FILTER (WHERE', subquery, name)
            self.assertIn('"harvesting_job_id" =', subquery, name)
            self.assertIn(f'"collecting_state" = {state.value}', subquery, name)
            self.assertIn(f'"{kind}_metadata_record_id" IS NOT NULL', subquery, name)

    def test_the_counters_are_answered_out_of_an_index_of_their_own(self):
        """Every read of the relations which answers a counter is a range of it."""
        _status, _body, queries = self.request(
            self.path(), **{'fields[HarvestingJob]': ','.join(self.COUNTERS)})
        scans = plan_scans(self.countersQuery(queries),
                           'registry_harvestedmetadatarelation')
        self.assertTrue(
            scans, 'the statement which answers the counters reads no relation '
                   'table at all: ' + self.countersQuery(queries))
        for node in scans:
            self.assertTrue(node['Node Type'].startswith('Index'), node)
            # Which index answers the range is the planner's choice, and a
            # TestCase has not committed the rows it seeded, so the statistics it
            # can read are not those of a table a harvest wrote (the index of the
            # counters itself is pinned by
            # `test_the_partial_indexes_of_the_counters_exist`). What the plan may
            # never do is read the relations other than as an index range of this
            # run with its state applied inside that scan.
            applied = (node.get('Index Cond', node.get('Recheck Cond', ''))
                       + ' ' + node.get('Filter', ''))
            self.assertIn('harvesting_job_id', applied, node)
            self.assertIn('collecting_state', applied, node)
            self.assertLess(node['Actual Loops'], 2, node)

    def test_the_partial_indexes_of_the_counters_exist(self):
        """The records of one kind of a job, by their state, are a range of their own."""
        with connections['default'].cursor() as cursor:
            cursor.execute(
                "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = "
                "'registry_harvestedmetadatarelation'")
            definitions = dict(cursor.fetchall())
        for kind in ('dataset', 'service'):
            name = f'harvested_{kind}_job_state'
            definition = definitions.get(name)
            self.assertIsNotNone(
                definition,
                f'the {kind} records of a job are no range of their own by state, '
                f'so their counters read every relation of the job (#1037): '
                f'{sorted(definitions)}')
            # pg renders an identifier unquoted when it does not need quotes, so
            # the quotes are taken out instead of guessed
            definition = definition.replace('"', '')
            self.assertIn('(harvesting_job_id, collecting_state)', definition,
                          'the index is not the range of the job by state: '
                          + definition)
            self.assertIn(f'{kind}_metadata_record_id IS NOT NULL', definition,
                          'the index is not partial on the kind of record: '
                          + definition)

    def test_the_measurements_of_a_run_still_come_from_the_aggregation(self):
        """The durations of a run are read from its records, the counters are not.

        The throughput of a run is the time its records measured, and that is an
        aggregation over them which no index of the counters answers. Asking both
        together therefore still builds the ``sums`` aggregation - once, and without
        the counters in it.
        """
        fields = 'newDatasetMetadataCount,existingServiceMetadataCount,recordsPerMinute'
        status, body, queries = self.request(
            self.path(), **{'fields[HarvestingJob]': fields})
        self.assertEqual(status, 200, body)
        self.assertEqual(
            body['data']['attributes'],
            {'newDatasetMetadataCount': self.NEW,
             'existingServiceMetadataCount': 0,
             # every record of the run measured one second of download and two of
             # the database, so a minute of measured work is 20 records
             'recordsPerMinute': 20.0})
        aggregated = [query['sql'] for query in queries if '"sums"' in query['sql']]
        self.assertEqual(len(aggregated), 1, aggregated)
        # the aggregation is what stands before the outer select; the counters of
        # the run are answered beside it, as subqueries of the outer select
        aggregation, found, _outer = aggregated[0].partition(') SELECT')
        self.assertTrue(found, 'no statement of the request aggregates: '
                               + aggregated[0])
        self.assertIn('harvested_records', aggregation, aggregation)
        self.assertIn('measured_seconds', aggregation, aggregation)
        for name, (kind, state) in METADATA_RECORD_COUNTS.items():
            self.assertNotIn(
                metadata_count_annotation(kind, state), aggregation,
                f'the counter {name} is aggregated although the run names it and '
                f'has its own range: {aggregation}')


class HarvestedMetadataQueryPerformance(QueryMeasurementMixin, TestCase):
    """Harvest history loads relationships once for the whole page (#869)."""

    fixtures = HarvestingQueryPerformance.fixtures
    path = '/api/registry/harvesting/harvested-metadata-records'

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        contact = MetadataContact.objects.first()
        dataset = DatasetMetadataRecord(
            title='Harvested dataset', metadata_contact=contact,
            dataset_contact=contact)
        metadata = ServiceMetadataRecord(
            title='Harvested service', metadata_contact=contact)
        DatasetMetadataRecord.objects.bulk_create([dataset])
        ServiceMetadataRecord.objects.bulk_create([metadata])
        cls.job = HarvestingJob.objects.order_by('pk').first()
        cls.relations = [
            HarvestedMetadataRelation(
                harvesting_job=job, collecting_state=state, **{field: record})
            for job in HarvestingJob.objects.order_by('pk')
            for state in (State.NEW, State.UPDATED, State.REMOVED)
            for field, record in (
                ('dataset_metadata_record', dataset),
                ('service_metadata_record', metadata))
        ]
        HarvestedMetadataRelation.objects.bulk_create(cls.relations)

    def test_list_queries_do_not_grow_with_rows(self):
        for params in ({}, {
            'sort': '-historyDate',
            'filter[harvesting_job__service]': str(self.job.service_id),
            'filter[collecting_state__in]': '1,2,4',
        }):
            with self.subTest(params=params):
                self.assertQueriesIndependentOfRows(
                    self.path, **params, **{'page[size]': 100})

    def test_nested_list_queries_do_not_grow_with_rows(self):
        self.assertQueriesIndependentOfRows(
            f'/api/registry/harvesting/harvesting-jobs/{self.job.pk}'
            '/harvested-metadata-records')

    def test_list_preserves_relationships_and_loads_them_once(self):
        status, body, queries = self.request(
            self.path, user='user', **{'page[size]': 100})
        self.assertEqual(status, 200)
        expected = {str(row.pk): row for row in self.relations}
        self.assertEqual(set(self.ids_of(body)), set(expected))
        for row in body['data']:
            relation = expected[row['id']]
            self.assertEqual(
                row['attributes']['collectingState'], relation.collecting_state)
            for name, resource_type, pk in (
                ('harvestingJob', 'HarvestingJob', relation.harvesting_job_id),
                ('datasetMetadataRecord', 'DatasetMetadataRecord',
                 relation.dataset_metadata_record_id),
                ('serviceMetadataRecord', 'ServiceMetadataRecord',
                 relation.service_metadata_record_id),
            ):
                self.assertEqual(
                    row['relationships'][name]['data'],
                    {'type': resource_type, 'id': str(pk)} if pk else None)
        counts = table_counter(queries)
        for table in ('registry_harvestingjob', 'registry_datasetmetadatarecord',
                      'registry_servicemetadatarecord'):
            self.assertEqual(counts[table], 1, msg=counts)


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
