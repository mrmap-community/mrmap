from datetime import datetime, timedelta, timezone
from uuid import uuid4

from django.test import TestCase
from django.urls import path, reverse
from drf_spectacular.generators import SchemaGenerator
from registry.models.service import FeatureType
from registry.views.statistical import StatisticalFeatureTypePerServiceListView
from rest_framework.test import APIClient


JSONAPI = 'application/vnd.api+json'


class FeatureTypeStatisticsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.service_id = uuid4()
        cls.other_service_id = uuid4()
        start = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        model = FeatureType.change_log.model

        # Create audit records directly: the statistics must also work after a
        # feature type or its service has been deleted from the live tables.
        for service_id, snapshots in (
            (cls.service_id, (
                (0, '+', 'Original'),
                (0, '~', 'Original'),
                (1, '~', 'Changed'),
                (2, '~', 'Changed'),
                (3, '-', 'Changed'),
            )),
            (cls.service_id, (
                (0, '+', 'Second feature type'),
                (1, '-', 'Second feature type'),
            )),
            (cls.other_service_id, (
                (0, '+', 'Other service'),
                (1, '~', 'Other service changed'),
            )),
        ):
            feature_id = uuid4()
            for index, (day, history_type, title) in enumerate(snapshots):
                model.objects.create(
                    id=feature_id, history_relation_id=feature_id,
                    service_id=service_id, default_reference_system_id=1,
                    file_identifier=str(feature_id), title=title,
                    history_type=history_type,
                    history_date=start + timedelta(days=day, minutes=index),
                )

    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_ACCEPT=JSONAPI)
        self.url = reverse('registry:statistical-featuretype-per-service')

    def request(self, **params):
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_counts_are_grouped_by_day_and_service(self):
        body = self.request(**{'filter[service]': str(self.service_id), 'sort': 'id'})
        self.assertEqual(body['meta']['pagination']['count'], 3)
        self.assertEqual(
            [(row['id'], row['type'], row['attributes']) for row in body['data']],
            [
                ('2026-01-01', 'StatisticalFeatureTypePerService', {
                    'day': '2026-01-01', 'service': str(self.service_id),
                    'new': 2, 'updated': 0, 'deleted': 0,
                }),
                ('2026-01-02', 'StatisticalFeatureTypePerService', {
                    'day': '2026-01-02', 'service': str(self.service_id),
                    'new': 0, 'updated': 1, 'deleted': 1,
                }),
                ('2026-01-04', 'StatisticalFeatureTypePerService', {
                    'day': '2026-01-04', 'service': str(self.service_id),
                    'new': 0, 'updated': 0, 'deleted': 1,
                }),
            ],
        )

    def test_unfiltered_statistics_keep_services_separate(self):
        body = self.request()
        self.assertEqual(body['meta']['pagination']['count'], 5)
        other_rows = [row['attributes'] for row in body['data']
                      if row['attributes']['service'] == str(self.other_service_id)]
        self.assertEqual(other_rows, [
            {'day': '2026-01-01', 'service': str(self.other_service_id),
             'new': 1, 'updated': 0, 'deleted': 0},
            {'day': '2026-01-02', 'service': str(self.other_service_id),
             'new': 0, 'updated': 1, 'deleted': 0},
        ])

    def test_sorting_and_pagination_use_the_statistical_day(self):
        body = self.request(**{
            'filter[service]': str(self.service_id),
            'sort': '-id', 'page[size]': '1', 'page[number]': '2',
        })
        self.assertEqual(body['meta']['pagination']['count'], 3)
        self.assertEqual([row['id'] for row in body['data']], ['2026-01-02'])

    def test_first_update_without_a_predecessor_counts_as_new(self):
        feature_id = uuid4()
        FeatureType.change_log.model.objects.create(
            id=feature_id, history_relation_id=feature_id,
            service_id=self.service_id, default_reference_system_id=1,
            history_type='~', history_date=datetime(2026, 1, 5, 12, tzinfo=timezone.utc),
        )
        body = self.request(**{'filter[service]': str(self.service_id), 'sort': '-id'})
        self.assertEqual(body['data'][0]['attributes'], {
            'day': '2026-01-05', 'service': str(self.service_id),
            'new': 1, 'updated': 0, 'deleted': 0,
        })

    def test_unknown_service_returns_empty_statistics(self):
        body = self.request(**{'filter[service]': str(uuid4())})
        self.assertEqual(body['data'], [])
        self.assertEqual(body['meta']['pagination']['count'], 0)

    def test_invalid_uuid_is_rejected(self):
        response = self.client.get(self.url, {'filter[service]': 'invalid'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('errors', response.json())

    def test_schema_discovers_the_resource_and_uuid_service_filter(self):
        generator = SchemaGenerator(patterns=[path(
            self.url.lstrip('/'), StatisticalFeatureTypePerServiceListView.as_view(),
        )])
        schema = generator.get_schema(public=True)
        operation = schema['paths'][self.url]['get']
        self.assertEqual(operation['operationId'], 'list_StatisticalFeatureTypePerService')
        service_filter = next(parameter for parameter in operation['parameters']
                              if parameter['name'] == 'filter[service]')
        self.assertEqual(service_filter['schema'], {'type': 'string', 'format': 'uuid'})
