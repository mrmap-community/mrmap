"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.05.20

"""
import json
from json import JSONDecodeError

from django.test import TestCase, Client
from django.urls import reverse

from api.settings import SUGGESTIONS_MAX_RESULTS
from service.models import Metadata, Keyword, Category, Service, Layer
from structure.models import Organization, MrMapGroup
from tests.baker_recipes.db_setup import create_superadminuser, create_wms_service
from tests.baker_recipes.structure_app.baker_recipes import PASSWORD

INVALID_STATUS_CODE_TEMPLATE = "Response returned with status code `{}`"
JSON_LOADS_FAILED_TEMPLATE = "Response could not be loaded into json! Exception was: {}"
DEFAULT_ELEMENT_NOT_FOUND_TEMPLATE = "Default element was not found in response: {}"


class ApiViewTestCase(TestCase):
    def setUp(self):
        # requires services
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        create_wms_service(group=self.user.get_groups().first(), how_much_services=10)

        # Default elements of json response
        self.default_response_elements = [
            "count",
            "next",
            "previous",
            "results",
        ]

        # 'name-list' | 'name-detail' is the naming convention of DRF
        # The values declare what we expect from a simple request for this API without further parameters
        self.available_apis = {
            "catalogue-list": Metadata.objects.filter(is_active=True),
            "metadata-list": Metadata.objects.filter(is_active=True),
            "suggestion-list": Keyword.objects.all()[:SUGGESTIONS_MAX_RESULTS],
            "category-list": Category.objects.all(),
            "organization-list": Organization.objects.filter(),
            "service-list": Service.objects.filter(parent_service=None, metadata__is_active=True),
            "layer-list": Layer.objects.filter(metadata__is_active=True),
            "group-list": MrMapGroup.objects.filter(),
        }

    def test_overview_menu(self):
        """ Tests whether the menu returns valid json

        Returns:

        """
        response = self.client.get(
            reverse("api:api-root"),
            data={
                "format": "json"
            }
        )
        try:
            response_json = json.loads(response.content)
        except JSONDecodeError as e:
            self.fail(msg=JSON_LOADS_FAILED_TEMPLATE.format(e))
        self.assertEqual(response.status_code, 200, msg=INVALID_STATUS_CODE_TEMPLATE.format(response.status_code))

        # Check that json is not empty
        for key, val in response_json.items():
            self.assertGreater(len(key), 0, msg="API key invalid: {}".format(key))
            self.assertGreater(len(val), 0, msg="API link invalid: {}".format(val))

    def _run_checks(self, response_json: dict, api_key: str):
        """ Runs checks for each API

        Args:
            response_json (dict): The API response as a dict (json)
            api_key (str): The API identifier
        Returns:

        """
        # expect default elements in response
        for elem in self.default_response_elements:
            self.assertTrue(elem in response_json, msg=DEFAULT_ELEMENT_NOT_FOUND_TEMPLATE.format(elem))

        # expect correct count
        count = response_json["count"]
        count_existing_elems = len(self.available_apis[api_key])
        self.assertEqual(count_existing_elems, count, msg="Wrong count: {} but {} returned for {}".format(count_existing_elems, count, api_key))

    def test_views(self):
        """ Tests whether the catalogue view returns valid json

        Returns:

        """
        for api in self.available_apis:
            response = self.client.get(
                reverse("api:{}".format(api)),
                data={
                    "format": "json"
                }
            )
            try:
                response_json = json.loads(response.content)
            except JSONDecodeError as e:
                self.fail(msg=JSON_LOADS_FAILED_TEMPLATE.format(e))
            self.assertEqual(response.status_code, 200, msg=INVALID_STATUS_CODE_TEMPLATE.format(response.status_code))

            # Run all checks
            self._run_checks(response_json, api_key=api)