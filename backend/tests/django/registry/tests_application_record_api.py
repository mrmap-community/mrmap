"""The application record answers like the dataset and the service record (#830).

The application record was harvested long before it had an endpoint of its own.
This module pins the parity it is promised with the two record endpoints that came
before it: the resource type, the answer of its relations, the permission fields
which the detail answers and the list does not, the nested routes of its own
relations, its filtering - including the spatial one - and the sparse fieldsets.

The permission assertions are the ones of ``tests_record_details.py`` for the
dataset record: an endpoint is only as open as the grants of the user asking it,
and the application record must not become the one record which forgets that.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import MultiPolygon, Polygon
from django.test import TestCase
from django.utils.timezone import now
from guardian.shortcuts import assign_perm
from registry.enums.harvesting import CollectingStatenEnum as State
from registry.enums.harvesting import HarvestingPhaseEnum as Phase
from registry.models.harvest import HarvestedMetadataRelation, HarvestingJob
from registry.models.metadata import (ApplicationMetadataRecord, IsoCategory,
                                      Keyword, Language, Licence,
                                      MetadataContact, ReferenceSystem,
                                      TimeExtent)
from registry.models.service import CatalogueService
from tests.django.registry.tests_query_performance import QueryMeasurementMixin

POLYGON_INSIDE = ('{"type": "Polygon", "coordinates": [[[6, 48], [14, 48],'
                  ' [14, 54], [6, 54], [6, 48]]]}')


class ApplicationRecordApiTests(QueryMeasurementMixin, TestCase):
    """The endpoint of the application record, pinned against the records of the
    fixtures and two application records this class adds beside them."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_csw.json", "test_datasetmetadata.json"]

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.contact = MetadataContact.objects.create(name='Application contact')
        cls.record = ApplicationMetadataRecord.objects.create(
            title='Application record', metadata_contact=cls.contact,
            application_contact=cls.contact)
        cls.other = ApplicationMetadataRecord.objects.create(
            title='Zebra application', metadata_contact=cls.contact,
            application_contact=cls.contact)
        cls.licence = Licence.objects.create(name='Open licence', identifier='test')
        cls.extent = TimeExtent.objects.create(
            begin='2020-01-01', end='2020-12-31', resolution=timedelta(days=1))
        for record in (cls.record, cls.other):
            record.licence = cls.licence
            record.save()
            record.time_extents.add(cls.extent)
            record.languages.add(Language.objects.first())
            record.keywords.add(*Keyword.objects.all()[:2])
            record.categories.add(*IsoCategory.objects.all()[:2])
            record.reference_systems.add(*ReferenceSystem.objects.all()[:2])
        cls.csw = CatalogueService.objects.first()
        cls.record.harvested_through.add(cls.csw)
        cls.record.bounding_geometry = MultiPolygon(
            Polygon.from_bbox((5, 47, 15, 55)), srid=4326)
        cls.record.save()

    def test_the_list_answers_the_application_resource_type(self):
        """the list names the application record and keeps its grants out of it

        ``RecordPermissionsSerializerMixin`` drops the permission fields of the
        list, where they would be asserted per row; the detail answers them.
        """
        status, body, _ = self.request('/api/registry/application-metadata', user='user')
        self.assertEqual(status, 200, body)
        self.assertEqual(
            [row['type'] for row in body['data']],
            ['ApplicationMetadataRecord'] * len(body['data']))
        for row in body['data']:
            self.assertNotIn('canEdit', row['attributes'])
            self.assertNotIn('canDelete', row['attributes'])

    def test_anonymous_may_read_the_application_records(self):
        """the endpoint is as open as the endpoints beside it (#830 measured it)"""
        status, body, _ = self.request('/api/registry/application-metadata')
        self.assertEqual(status, 200, body)
        status, body, _ = self.request(f'/api/registry/application-metadata/{self.record.pk}')
        self.assertEqual(status, 200, body)
        self.assertFalse(body['data']['attributes']['canEdit'])
        self.assertFalse(body['data']['attributes']['canDelete'])

    def test_detail_includes_the_relations_of_the_record(self):
        """the application record includes what the dataset record includes, with
        the providing contact named after the application"""
        include = ('metadataContact,applicationContact,licence,keywords,categories,'
                   'timeExtents,languages,createdBy,lastModifiedBy,harvestedThrough,'
                   'referenceSystems')
        status, body, queries = self.request(
            f'/api/registry/application-metadata/{self.record.pk}', include=include,
            **{"fields[CatalogueService]": "title,string_representation"})
        self.assertEqual(status, 200, body)
        types = {row['type'] for row in body['included']}
        self.assertTrue({'MetadataContact', 'Licence', 'TimeExtent', 'Language',
                         'Keyword', 'IsoCategory', 'CatalogueService'} <= types, types)
        licence = next(row for row in body['included'] if row['type'] == 'Licence')
        self.assertEqual(licence['attributes']['name'], 'Open licence')
        # the two contacts of the record answer as the same contact twice is not
        # what the include is about; both relations must be present at all
        contacts = [row for row in body['included'] if row['type'] == 'MetadataContact']
        self.assertIn(str(self.contact.pk), {row['id'] for row in contacts})
        self.assertLessEqual(len(queries), 30, queries)

    def test_edit_permission_requires_model_and_object_grants(self):
        """the application record is guarded like the record endpoints beside it"""
        reader = get_user_model().objects.create_user('application-reader', password='test')
        assign_perm('registry.change_applicationmetadatarecord', reader)
        self.user = reader
        path = f'/api/registry/application-metadata/{self.record.pk}'
        status, body, _ = self.request(path, user='user')
        self.assertEqual(status, 200, body)
        self.assertFalse(body['data']['attributes']['canEdit'])
        assign_perm('registry.change_applicationmetadatarecord', reader, self.record)
        status, body, _ = self.request(path, user='user')
        self.assertEqual(status, 200, body)
        self.assertTrue(body['data']['attributes']['canEdit'])
        self.assertFalse(body['data']['attributes']['canDelete'])

    def test_nested_record_lists_resolve(self):
        """every relation of the record answers its own nested list"""
        for relation in ('keywords', 'licence', 'metadata-contact',
                         'application-contact', 'referencesystems', 'csws'):
            with self.subTest(relation=relation):
                status, body, _ = self.request(
                    f'/api/registry/application-metadata/{self.record.pk}/{relation}')
                self.assertEqual(status, 200, body)

    def test_the_nested_csws_list_answers_only_the_catalogues_of_the_record(self):
        """the nested catalogue list is filtered by the parent record"""
        status, body, _ = self.request(
            f'/api/registry/application-metadata/{self.record.pk}/csws')
        self.assertEqual(status, 200, body)
        self.assertEqual([row['id'] for row in body['data']], [str(self.csw.pk)])

    def test_the_application_contact_answers_its_own_resource_type(self):
        """the contact which provides the application is named after the application"""
        status, body, _ = self.request(
            f'/api/registry/application-metadata/{self.record.pk}/application-contact')
        self.assertEqual(status, 200, body)
        self.assertEqual([row['type'] for row in body['data']], ['ApplicationContact'])

    def test_the_list_can_be_ordered_by_title_and_rejects_an_unknown_order(self):
        status, body, _ = self.request(
            '/api/registry/application-metadata',
            **{'fields[ApplicationMetadataRecord]': 'id,title', 'sort': 'title'})
        self.assertEqual(status, 200, body)
        titles = [row['attributes']['title'] for row in body['data']]
        self.assertEqual(titles, sorted(titles))
        self.assertIn('Application record', titles)
        status, body, _ = self.request('/api/registry/application-metadata', sort='nonexistent')
        self.assertEqual(status, 400, body)

    def test_the_list_can_be_filtered_by_title_state_and_geometry(self):
        """the filters of the dataset record are filters of the application record"""
        status, body, _ = self.request(
            '/api/registry/application-metadata',
            **{'filter[title__icontains]': 'application record'})
        self.assertEqual(status, 200, body)
        self.assertEqual([row['id'] for row in body['data']], [str(self.record.pk)])

        job = HarvestingJob.objects.create(
            service=CatalogueService.objects.exclude(pk=self.csw.pk).first(),
            phase=Phase.COMPLETED, total_records=1, done_at=now())
        HarvestedMetadataRelation.objects.create(
            harvesting_job=job, application_metadata_record=self.record,
            collecting_state=State.NEW)
        status, body, _ = self.request(
            '/api/registry/application-metadata',
            **{'filter[harvested_application_metadata_relation__harvesting_job]': str(job.pk)})
        self.assertEqual(status, 200, body)
        self.assertEqual([row['id'] for row in body['data']], [str(self.record.pk)])
        status, body, _ = self.request(
            '/api/registry/application-metadata',
            **{'filter[harvested_application_metadata_relation__collecting_state]': str(State.NEW.value)})
        self.assertEqual(status, 200, body)
        self.assertEqual([row['id'] for row in body['data']], [str(self.record.pk)])

        status, body, _ = self.request(
            '/api/registry/application-metadata',
            **{'filter[bounding_geometry__intersects]': POLYGON_INSIDE})
        self.assertEqual(status, 200, body)
        self.assertEqual([row['id'] for row in body['data']], [str(self.record.pk)])

    def test_sparse_fieldsets_keep_unasked_fields_out_of_the_answer(self):
        """a screen which only shows the title pays for the title"""
        status, body, _ = self.request(
            '/api/registry/application-metadata',
            **{'fields[ApplicationMetadataRecord]': 'title'})
        self.assertEqual(status, 200, body)
        for row in body['data']:
            self.assertEqual(list(row['attributes']), ['title'])

    def test_the_list_answers_independent_of_its_rows(self):
        """no relation of the application record is loaded per row"""
        self.assertQueriesIndependentOfRows('/api/registry/application-metadata')
