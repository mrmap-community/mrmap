"""The per-day statistics of the api answer their aggregation themselves.

#857 took the statistics out of the nine materialized views: the endpoints of
``registry/views/statistical.py`` answer the aggregation over the audit records
of a resource directly, so a change is counted the moment it is written and no
scheduled rebuild stands between the two. Which rows an endpoint answers and how
they are named must not change with that -- ``id`` and ``day`` are the day of the
changes, the counters are ``new``, ``updated`` and ``deleted`` (``existed`` for
what a harvesting job found), and the per-service endpoints keep their ``service``
filter -- because the dashboard and the charts of a service read exactly that.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from mptt2.models import Tree
from registry.enums.harvesting import CollectingStatenEnum
from registry.models.harvest import HarvestedMetadataRelation, HarvestingJob
from registry.models.metadata import DatasetMetadataRecord, MetadataContact
from registry.models.service import Layer
from rest_framework.test import APIClient

JSONAPI = 'application/vnd.api+json'

START = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
DAY = timedelta(days=1)

WMS1_ID = 'cd16cc1f-3abb-4625-bb96-fbe80dbe23e3'
WMS2_ID = '1b195589-dcfa-403f-9e66-e7e1c0a67024'
CSW2_ID = '3df586c6-b89b-4ce5-980a-12dc3ca23df2'


def layer_audit_row(layer_id, tree, service_id, day, history_type, title):
    """One audit row of a layer, written the way the statistics read it.

    The rows are written directly instead of by saving a layer, because the
    statistics also answer the changes of a layer whose service is gone. A layer
    is a node of a tree, so its audit row carries the position it had -- not what
    the statistics read, but what the table of audit rows answers.
    """
    return Layer.change_log.model.objects.create(
        id=layer_id, history_relation_id=layer_id, service_id=service_id,
        mptt_tree=tree, mptt_lft=1, mptt_rgt=2, mptt_depth=0,
        file_identifier=str(layer_id), title=title,
        history_type=history_type, history_date=day,
    )


class StatisticalListViewTestMixin:
    """The request plumbing every statistics endpoint shares."""

    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_ACCEPT=JSONAPI)

    def url(self, name):
        return reverse(f'registry:{name}')

    def request(self, name, **params):
        response = self.client.get(self.url(name), params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()


class LayerPerServiceStatisticsTest(StatisticalListViewTestMixin, TestCase):
    """The layers of one WMS per day, as the overview chart of that service asks."""

    fixtures = ['test_users.json', 'test_keywords.json', 'test_crs.json',
                'test_wms.json']

    @classmethod
    def setUpTestData(cls):
        # Proxy tests leave audit records after deleting their live services and
        # the fixtures write their own, so the unfiltered statistics of this
        # class are its own; the transaction of TestCase takes the rows out again.
        Layer.change_log.model.objects.all().delete()

        cls.first_layer = uuid4()
        cls.second_layer = uuid4()
        cls.other_layer = uuid4()
        cls.trees = {layer: Tree.objects.create() for layer in (
            cls.first_layer, cls.second_layer, cls.other_layer)}
        # minute by minute apart: a record is only compared against the row
        # whose moment is in front of its own, and two rows of one record which
        # answer the same second have no order the database could tell apart
        for index, (layer_id, service_id, day, change, title) in enumerate((
            (cls.first_layer, WMS1_ID, START, '+', 'Wasserversorgung'),
            (cls.second_layer, WMS1_ID, START, '+', 'Bodenrichtwerte'),
            (cls.other_layer, WMS2_ID, START + DAY, '+', 'Niederschlag'),
            (cls.first_layer, WMS1_ID, START + DAY, '~', 'Wasserversorgung NRW'),
            (cls.second_layer, WMS1_ID, START + DAY, '-', 'Bodenrichtwerte'),
        )):
            layer_audit_row(layer_id, cls.trees[layer_id], service_id,
                            day + timedelta(minutes=index), change, title)

    def per_service(self, service_id, **params):
        return self.request('statistical-layer-per-service',
                            **{'filter[service]': service_id, **params})

    def test_counts_are_grouped_by_day_for_one_service(self):
        body = self.per_service(WMS1_ID, sort='id')

        self.assertEqual(body['meta']['pagination']['count'], 2)
        self.assertEqual(
            [(row['id'], row['type'], row['attributes']) for row in body['data']],
            [
                ('2026-01-01', 'StatisticalLayerPerService', {
                    'day': '2026-01-01', 'service': WMS1_ID,
                    'new': 2, 'updated': 0, 'deleted': 0,
                }),
                ('2026-01-02', 'StatisticalLayerPerService', {
                    'day': '2026-01-02', 'service': WMS1_ID,
                    'new': 0, 'updated': 1, 'deleted': 1,
                }),
            ],
        )

    def test_sorting_and_pagination_use_the_statistical_day(self):
        body = self.per_service(WMS1_ID, **{
            'sort': '-id', 'page[size]': '1', 'page[number]': '2',
        })

        self.assertEqual(body['meta']['pagination']['count'], 2)
        self.assertEqual([row['id'] for row in body['data']], ['2026-01-01'])

    def test_a_change_is_counted_the_moment_it_is_written(self):
        """Nothing is rebuilt before the statistics answer a change.

        The answer used to come from a view which a task refreshed on a schedule,
        so a change appeared only after the next refresh; the aggregation answers
        it with the very next request.
        """
        before = self.per_service(WMS2_ID, sort='id')
        self.assertEqual(before['meta']['pagination']['count'], 1)

        layer_audit_row(self.other_layer, self.trees[self.other_layer],
                        WMS2_ID, START + DAY + timedelta(minutes=10), '~',
                        'Niederschlag NRW')

        after = self.per_service(WMS2_ID, sort='id')
        self.assertEqual(
            after['data'][0]['attributes'],
            {'day': '2026-01-02', 'service': WMS2_ID,
             'new': 1, 'updated': 1, 'deleted': 0},
        )

    def test_a_save_which_changed_nothing_is_no_change(self):
        """An audit row of a save which changed nothing is not an update.

        Whether a row changed a tracked field is what the database wrote into it
        (#856) and the endpoint has to keep that apart: a day which only saw such
        a row does not appear in the statistics at all.
        """
        layer_audit_row(self.other_layer, self.trees[self.other_layer],
                        WMS2_ID, START + timedelta(days=2, minutes=10), '~',
                        'Niederschlag')

        body = self.per_service(WMS2_ID, sort='id')

        self.assertEqual([row['id'] for row in body['data']], ['2026-01-02'])
        self.assertEqual(body['data'][0]['attributes']['updated'], 0)

    def test_the_unfiltered_statistics_keep_the_services_apart(self):
        body = self.request('statistical-layer', sort='id')

        self.assertEqual(body['meta']['pagination']['count'], 2)
        self.assertEqual(
            [(row['id'], row['attributes']) for row in body['data']],
            [
                ('2026-01-01', {'day': '2026-01-01',
                                'new': 2, 'updated': 0, 'deleted': 0}),
                ('2026-01-02', {'day': '2026-01-02',
                                'new': 1, 'updated': 1, 'deleted': 1}),
            ],
        )


class HarvestedMetadataRelationStatisticsTest(StatisticalListViewTestMixin, TestCase):
    """The days a harvesting job found records, as its activity card asks."""

    fixtures = ['test_users.json', 'test_keywords.json', 'test_crs.json',
                'test_csw.json']

    ENDPOINT = 'statistical-harvested-metadata-relations'

    @classmethod
    def setUpTestData(cls):
        HarvestedMetadataRelation.objects.all().delete()
        # the job of the harvesting fixture belongs to CSW2, which is the service
        # whose rows these tests ask for
        cls.job = HarvestingJob.objects.get(service_id=CSW2_ID)
        contact = MetadataContact.objects.create(name='Harvesting contact')
        cls.records = [
            DatasetMetadataRecord.objects.create(
                metadata_contact=contact, dataset_contact=contact,
                title='Wasserversorgung %d' % number)
            for number in range(3)]

    def harvest(self, record, state, day):
        """What the job found of one record on one day.

        The day of a relation is the day it was created, which is what the
        endpoint groups by; backdating it is how the days a harvest ran on are
        told apart without waiting for them.
        """
        relation = HarvestedMetadataRelation.objects.create(
            harvesting_job=self.job,
            dataset_metadata_record=record,
            collecting_state=state.value,
        )
        HarvestedMetadataRelation.objects.filter(pk=relation.pk).update(
            history_date=day)
        return relation

    def attributes(self, day, new=0, updated=0, existed=0):
        """One row the endpoint answers for this test's job of CSW2."""
        return {'day': day, 'service': CSW2_ID, 'harvestingJob': self.job.pk,
                'new': new, 'updated': updated, 'existed': existed}

    def test_counts_answer_the_collecting_states_per_day(self):
        self.harvest(self.records[0], CollectingStatenEnum.NEW, START)
        self.harvest(self.records[1], CollectingStatenEnum.UPDATED, START)
        self.harvest(self.records[2], CollectingStatenEnum.EXISTING, START + DAY)

        body = self.request(self.ENDPOINT, sort='id')

        self.assertEqual(body['meta']['pagination']['count'], 3)
        self.assertEqual({row['type'] for row in body['data']},
                         {'StatisticalHarvestedMetadataRelation'})
        self.assertEqual(
            [(row['id'], row['attributes']['service'], row['attributes']['harvestingJob'])
             for row in body['data']],
            [('2026-01-01', CSW2_ID, self.job.pk)] * 2
            + [('2026-01-02', CSW2_ID, self.job.pk)],
        )
        # a day on which the job found new records *and* updated ones is two rows,
        # one per collecting state, which is what the aggregation groups by -- and
        # in which order the two come is nothing the endpoint promises
        self.assertEqual(
            sorted((row['attributes']['new'], row['attributes']['updated'],
                    row['attributes']['existed'])
                   for row in body['data'] if row['id'] == '2026-01-01'),
            [(0, 1, 0), (1, 0, 0)],
        )
        self.assertEqual(
            [row['attributes'] for row in body['data'] if row['id'] == '2026-01-02'],
            [self.attributes('2026-01-02', existed=1)],
        )

    def test_a_service_and_a_job_filter_answer_their_rows(self):
        self.harvest(self.records[0], CollectingStatenEnum.NEW, START)

        by_service = self.request(self.ENDPOINT, **{'filter[service]': CSW2_ID})
        self.assertEqual(by_service['meta']['pagination']['count'], 1)
        # the JSON:API layer camelizes the field names, which is what the
        # activity card of a service reads
        self.assertEqual(by_service['data'][0]['attributes'],
                         {'day': '2026-01-01', 'service': CSW2_ID,
                          'harvestingJob': self.job.pk,
                          'new': 1, 'updated': 0, 'existed': 0})

        by_job = self.request(self.ENDPOINT,
                              **{'filter[harvesting_job]': self.job.pk})
        self.assertEqual(by_job['meta']['pagination']['count'], 1)

    def test_a_service_or_job_which_is_not_there_answers_no_rows(self):
        """A filter naming what is not there answers nothing, not a refusal.

        Both filters keep the plain value filters the endpoint had while the
        statistics were read from a view which carried the service and the job as
        its own columns: the auto generated filter of a foreign key would refuse
        an id it does not know with ``invalid_choice`` instead.
        """
        for param, value in (('filter[service]', str(uuid4())),
                             ('filter[harvesting_job]', 999_999)):
            with self.subTest(param=param):
                body = self.request(self.ENDPOINT, **{param: value})
                self.assertEqual(body['data'], [])
                self.assertEqual(body['meta']['pagination']['count'], 0)

    def test_a_value_which_is_neither_a_uuid_nor_a_number_is_refused(self):
        for param, value in (('filter[service]', 'not-a-uuid'),
                             ('filter[harvesting_job]', 'not-a-number')):
            with self.subTest(param=param):
                response = self.client.get(self.url(self.ENDPOINT),
                                           {param: value})
                self.assertEqual(response.status_code, 400)
                self.assertIn('errors', response.json())


class HarvestedMetadataRelationGroupsTest(StatisticalListViewTestMixin,
                                          TestCase):
    """Many days, two jobs and every collecting state of one harvesting view.

    #1316 answered the total of this endpoint from the number of distinct
    grouping tuples instead of letting the paginator wrap the whole
    aggregation in a second COUNT. Which rows, which totals and which pages
    the endpoint answers must not change with that, and no total may go
    stale: every expectation below is counted from the fixture's relations
    in Python, so it pins what the database aggregation has to answer
    without computing the same answer a second time with SQL.
    """

    fixtures = ['test_users.json', 'test_keywords.json', 'test_crs.json',
                'test_csw.json']

    ENDPOINT = 'statistical-harvested-metadata-relations'

    # day offset, job, collecting state, how many relations the harvest wrote
    WAVES = [
        (0, 'catalogue', CollectingStatenEnum.NEW, 3),
        (0, 'catalogue', CollectingStatenEnum.UPDATED, 1),
        # the states which no counter of the answer names keep their own day:
        # such a group answers all three counters with 0 and still counts
        # towards the total of the card
        (0, 'catalogue', CollectingStatenEnum.DUPLICATED, 2),
        (1, 'catalogue', CollectingStatenEnum.EXISTING, 2),
        (1, 'file_import', CollectingStatenEnum.NEW, 4),
        (2, 'file_import', CollectingStatenEnum.REMOVED, 1),
    ]

    COUNTER_OF = {  # which counter of the answer one collecting state feeds
        CollectingStatenEnum.NEW: 'new',
        CollectingStatenEnum.UPDATED: 'updated',
        CollectingStatenEnum.EXISTING: 'existed',
    }

    ROW_KEY = ('day', 'new', 'updated', 'existed')

    @classmethod
    def setUpTestData(cls):
        HarvestedMetadataRelation.objects.all().delete()
        cls.jobs = {
            'catalogue': HarvestingJob.objects.get(service_id=CSW2_ID),
            # a file import job belongs to no service: its groups answer
            # `service: null` and must keep both their rows and their total
            'file_import': HarvestingJob.objects.create(),
        }
        contact = MetadataContact.objects.create(name='Harvesting contact')
        relations = []
        for day, job_key, state, number in cls.WAVES:
            for _ in range(number):
                relations.append((
                    HarvestedMetadataRelation.objects.create(
                        harvesting_job=cls.jobs[job_key],
                        dataset_metadata_record=(
                            DatasetMetadataRecord.objects.create(
                                metadata_contact=contact,
                                dataset_contact=contact,
                                title='Group relation %d' % len(relations))),
                        collecting_state=state.value),
                    day))
        for relation, day in relations:
            HarvestedMetadataRelation.objects.filter(pk=relation.pk).update(
                history_date=START + timedelta(days=day))
        cls.written = relations

    def expected(self):
        """One row per (day, job, state) group, counted without SQL."""
        rows = []
        for day, job_key, state, number in self.WAVES:
            job = self.jobs[job_key]
            attributes = {
                'day': (START + timedelta(days=day)).date().isoformat(),
                'service': str(job.service_id) if job.service_id else None,
                'harvestingJob': job.pk,
                'new': 0, 'updated': 0, 'existed': 0,
            }
            counter = self.COUNTER_OF.get(state)
            if counter:
                attributes[counter] = number
            rows.append(attributes)
        return sorted(rows, key=lambda row: [
            row[name] for name in self.ROW_KEY])

    def sorted_rows(self, body):
        return sorted((row['attributes'] for row in body['data']),
                      key=lambda row: [row[name] for name in self.ROW_KEY])

    def test_the_groups_their_counters_and_their_total_answer_the_relations(self):
        body = self.request(self.ENDPOINT, sort='id', **{'page[size]': '100'})
        expected = self.expected()

        self.assertEqual({row['type'] for row in body['data']},
                         {'StatisticalHarvestedMetadataRelation'})
        self.assertEqual(body['meta']['pagination']['count'], len(expected))
        self.assertEqual(self.sorted_rows(body), expected)
        self.assertEqual([row['id'] for row in body['data']],
                         [row['attributes']['day'] for row in body['data']])
        # no relation is counted twice and none is lost: the counters add up
        # to the relations of the states which feed them
        self.assertEqual(
            [sum(row['attributes'][name] for row in body['data'])
             for name in ('new', 'updated', 'existed')],
            [7, 1, 2])
        # the groups of the states without a counter are there, answering 0
        # and counted in the total
        self.assertEqual(
            sum(not any(row['attributes'][name]
                        for name in ('new', 'updated', 'existed'))
                for row in body['data']),
            2)

    def test_paging_walks_the_groups_without_loss_or_repeat(self):
        # the page size 3 lets the pages break with the days, whose groups
        # follow each other without an order the endpoint promises
        expected = self.expected()
        walked = []
        for page in (1, 2):
            body = self.request(self.ENDPOINT, sort='id', **{
                'page[size]': '3', 'page[number]': str(page)})
            self.assertEqual(body['meta']['pagination']['count'],
                             len(expected), 'every page knows the whole total')
            walked.extend(body['data'])

        self.assertEqual(len(walked), len(expected))
        self.assertEqual(sorted((row['attributes'] for row in walked),
                                key=lambda row: [row[name] for name in
                                                 self.ROW_KEY]),
                         expected)

    def test_a_written_relation_is_answered_immediately(self):
        """Nothing is cached between requests: the next one has the new row.

        The total is answered from the relations themselves, so neither a
        group whose counter grows nor a group which appears for the first
        time has to wait for anything.
        """
        before = self.request(self.ENDPOINT, sort='id',
                              **{'page[size]': '100'})
        self.assertEqual(before['meta']['pagination']['count'],
                         len(self.expected()))

        contact = MetadataContact.objects.create(name='Second contact')

        def harvest(day, state):
            relation = HarvestedMetadataRelation.objects.create(
                harvesting_job=self.jobs['catalogue'],
                dataset_metadata_record=DatasetMetadataRecord.objects.create(
                    metadata_contact=contact, dataset_contact=contact,
                    title='Late relation'),
                collecting_state=state.value)
            HarvestedMetadataRelation.objects.filter(pk=relation.pk).update(
                history_date=START + timedelta(days=day))
            return relation

        # one more relation of a group which is already there: the counter
        # grows, the total of the groups stays
        harvest(0, CollectingStatenEnum.NEW)
        same_groups = self.request(self.ENDPOINT, sort='id',
                                   **{'page[size]': '100'})
        self.assertEqual(same_groups['meta']['pagination']['count'],
                         len(self.expected()))
        self.assertEqual(
            sum(row['attributes']['new'] for row in same_groups['data']
                if row['id'] == '2026-01-01'), 4)

        # a relation of a day which had none opens its own group at once
        harvest(3, CollectingStatenEnum.NEW)
        grown = self.request(self.ENDPOINT, sort='id',
                             **{'page[size]': '100'})
        self.assertEqual(grown['meta']['pagination']['count'],
                         len(self.expected()) + 1)
        self.assertEqual([row['id'] for row in grown['data']
                          if row['id'] == '2026-01-04'], ['2026-01-04'])

    def test_the_filters_keep_rows_and_total_together(self):
        by_service = self.request(self.ENDPOINT, **{
            'filter[service]': CSW2_ID, 'page[size]': '100'})
        self.assertEqual(by_service['meta']['pagination']['count'], 4)
        self.assertEqual({row['attributes']['service']
                          for row in by_service['data']}, {CSW2_ID})

        file_job = self.jobs['file_import']
        by_job = self.request(self.ENDPOINT, **{
            'filter[harvesting_job]': file_job.pk, 'page[size]': '100'})
        self.assertEqual(by_job['meta']['pagination']['count'], 2)
        self.assertEqual({row['attributes']['service']
                          for row in by_job['data']}, {None})

    def test_an_authenticated_request_answers_the_same_as_an_anonymous_one(self):
        """The card is open without a login, and a login changes nothing."""
        anonymous = self.request(self.ENDPOINT, sort='id')

        client = APIClient()
        client.credentials(HTTP_ACCEPT=JSONAPI)
        client.force_authenticate(
            user=get_user_model().objects.get(username='User1'))
        response = client.get(self.url(self.ENDPOINT), {'sort': 'id'})

        self.assertEqual(response.status_code, 200, response.content)
        authenticated = response.json()
        # the answer stamps the time of its own request into its meta, and
        # two requests never answer that with the same microseconds - so
        # everything the meta says beside its stamp is compared
        self.assertEqual(
            {name: value for name, value in authenticated['meta'].items()
             if name != 'systemTime'},
            {name: value for name, value in anonymous['meta'].items()
             if name != 'systemTime'})
        # the answer groups rows within a day in an order it promises
        # nothing, so the rows are compared sorted
        self.assertEqual(self.sorted_rows(authenticated),
                         self.sorted_rows(anonymous))
