"""The verbs the update mapping endpoints answer (#1479).

Both mapping endpoints refuse PUT by leaving it out of ``http_method_names``
- which once also took HEAD and OPTIONS away, although both are verbs of the
request itself: HEAD answers the headers of the GET (drf delegates it to the
GET handler in setup) and OPTIONS answers the ``Allow`` header the api
declares. This module pins the whole verb policy - the refusal of PUT as
well as the two answers that were missing - so neither can silently change.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

JSONAPI = 'application/vnd.api+json'

MAPPING_ENDPOINTS = (
    '/api/registry/update/layer-mappings',
    '/api/registry/update/featuretype-mappings',
)


class MappingEndpointVerbsTest(TestCase):
    """GET and PATCH are answered, HEAD and OPTIONS are, PUT is not."""

    fixtures = ['test_users.json']

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # the PUT arm must reach the verb decision, not the permission
        # decision of the object - the superuser passes both
        cls.admin = get_user_model().objects.create(username='verbs-admin')
        cls.admin.is_superuser = True
        cls.admin.is_staff = True
        cls.admin.save()

    def api_client(self, user=None):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user=user)
        return client

    def test_put_stays_refused_and_names_the_allowed_verbs(self):
        for path in MAPPING_ENDPOINTS:
            with self.subTest(path=path):
                response = self.api_client(self.admin).put(
                    path, data={}, format='vnd.api+json',
                    HTTP_ACCEPT=JSONAPI)
                self.assertEqual(response.status_code, 405, response.data)
                allowed = {
                    verb.strip().lower()
                    for verb in response['Allow'].split(',')}
                self.assertNotIn('put', allowed)
                # the detail route is where PATCH is a bound action at all:
                # refusing PUT must not have narrowed this route below the
                # verbs the viewset declares for it (#1479)
                response = self.api_client(self.admin).put(
                    path + '/0', data={}, format='vnd.api+json',
                    HTTP_ACCEPT=JSONAPI)
                self.assertEqual(response.status_code, 405)
                allowed = {
                    verb.strip().lower()
                    for verb in response['Allow'].split(',')}
                self.assertEqual(allowed,
                                 {'get', 'patch', 'head', 'options'})

    def test_head_and_options_are_answered(self):
        for path in MAPPING_ENDPOINTS:
            with self.subTest(path=path):
                response = self.api_client().options(path, HTTP_ACCEPT=JSONAPI)
                self.assertEqual(response.status_code, 200, response.data)
                allowed = {
                    verb.strip().lower()
                    for verb in response['Allow'].split(',')}
                # the LIST route binds no PATCH action - a mapping is updated
                # at its own url - but the verbs of the request itself are
                # answered since #1479, and PUT stays out
                self.assertEqual(allowed, {'get', 'head', 'options'},
                                 'the endpoint answers a different verb set '
                                 'than the api declares for it')
                response = self.api_client().head(path, HTTP_ACCEPT=JSONAPI)
                self.assertEqual(response.status_code, 200)
