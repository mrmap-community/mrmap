from datetime import timedelta

from django.test import TestCase
from django.utils.dateparse import parse_datetime
from registry.models.service import FeatureType, Layer
from tests.django.registry.tests_query_performance import (
    SERVICES, QueryMeasurementMixin)


class CreationHistoryApiTest(QueryMeasurementMixin, TestCase):
    fixtures = SERVICES
    resources = (
        (Layer, '/api/registry/layers', 'wms'),
        (FeatureType, '/api/registry/featuretypes', 'wfs'),
    )

    def child_with_history(self, model):
        record = model.change_log.filter(history_type='+').first()
        return model.objects.get(pk=record.history_relation_id)

    def get_row(self, path, **params):
        status, body, _queries = self.request(path, user='user', **params)
        self.assertEqual(status, 200, body)
        return body['data']

    def test_child_creation_timestamp_takes_precedence(self):
        for model, path, _service_path in self.resources:
            with self.subTest(resource=model.__name__):
                child = self.child_with_history(model)
                service_date = child.service.change_log.filter(history_type='+').earliest('history_date').history_date
                expected = service_date + timedelta(days=3)
                child.change_log.filter(history_type='+').update(history_date=expected)
                row = self.get_row(f'{path}/{child.pk}')
                self.assertEqual(parse_datetime(row['attributes']['createdAt']), expected)

    def test_missing_child_creation_uses_service_date_without_writing_history(self):
        for model, path, service_path in self.resources:
            with self.subTest(resource=model.__name__):
                child = self.child_with_history(model)
                expected = child.service.change_log.filter(history_type='+').earliest('history_date').history_date
                child.change_log.filter(history_type='+').delete()
                history_count = model.change_log.count()
                for params in ({}, {f'fields[{model.__name__}]': 'createdAt'}):
                    row = self.get_row(f'{path}/{child.pk}', **params)
                    self.assertEqual(parse_datetime(row['attributes']['createdAt']), expected)
                    nested_path = f'/api/registry/{service_path}/{child.service_id}/{path.rsplit("/", 1)[1]}'
                    rows = self.get_row(nested_path, **{'filter[id]': str(child.pk), **params})
                    self.assertEqual(len(rows), 1)
                    self.assertEqual(parse_datetime(rows[0]['attributes']['createdAt']), expected)
                self.assertEqual(model.change_log.count(), history_count)

    def test_missing_service_and_child_creation_remains_null(self):
        for model, path, _service_path in self.resources:
            with self.subTest(resource=model.__name__):
                child = self.child_with_history(model)
                child.change_log.filter(history_type='+').delete()
                child.service.change_log.filter(history_type='+').delete()
                row = self.get_row(f'{path}/{child.pk}')
                self.assertIsNone(row['attributes']['createdAt'])

    def test_legacy_lists_do_not_query_history_per_row(self):
        for model, path, _service_path in self.resources:
            with self.subTest(resource=model.__name__):
                model.change_log.filter(history_type='+').delete()
                self.assertQueriesIndependentOfRows(path, **{
                    f'fields[{model.__name__}]': 'createdAt',
                })

    def test_sparse_timestamps_and_relationships_have_content(self):
        for model, path, _service_path in self.resources:
            with self.subTest(resource=model.__name__):
                child = self.child_with_history(model)
                creation = child.change_log.filter(history_type='+').first()
                latest = child.change_log.first()
                row = self.get_row(f'{path}/{child.pk}', **{
                    f'fields[{model.__name__}]': 'createdAt,lastModifiedAt,createdBy,service',
                })
                self.assertEqual(set(row['attributes']), {'createdAt', 'lastModifiedAt'})
                self.assertEqual(parse_datetime(row['attributes']['createdAt']), creation.history_date)
                self.assertEqual(parse_datetime(row['attributes']['lastModifiedAt']), latest.history_date)
                self.assertEqual(row['relationships']['service']['data']['id'], str(child.service_id))
                self.assertEqual(row['relationships']['createdBy']['data']['id'], str(creation.history_user_id))
                self.assertIn('self', row['links'])

    def test_sparse_fields_apply_to_included_resources(self):
        for model, path, _service_path in self.resources:
            with self.subTest(resource=model.__name__):
                child = self.child_with_history(model)
                status, body, _queries = self.request(f'{path}/{child.pk}', user='user', **{
                    'include': 'service',
                    f'fields[{model.__name__}]': 'service',
                    f'fields[{child.service._meta.object_name}]': 'serviceUrl',
                })
                self.assertEqual(status, 200, body)
                self.assertNotIn('attributes', body['data'])
                service = next(row for row in body['included'] if row['id'] == str(child.service_id))
                self.assertEqual(service['attributes'], {'serviceUrl': child.service.service_url})
                self.assertNotIn('relationships', service)

    def test_empty_sparse_fieldset_preserves_identity_and_self_link(self):
        for model, path, _service_path in self.resources:
            with self.subTest(resource=model.__name__):
                child = self.child_with_history(model)
                row = self.get_row(f'{path}/{child.pk}', **{f'fields[{model.__name__}]': ''})
                self.assertEqual(row['id'], str(child.pk))
                self.assertEqual(row['type'], model.__name__)
                self.assertIn('self', row['links'])
                self.assertNotIn('attributes', row)
                self.assertNotIn('relationships', row)
