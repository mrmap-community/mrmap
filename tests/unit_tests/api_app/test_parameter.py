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

from service.models import Metadata
from tests.baker_recipes.db_setup import create_superadminuser, create_wms_service
from tests.baker_recipes.structure_app.baker_recipes import PASSWORD
from tests.unit_tests.api_app.test_views import INVALID_STATUS_CODE_TEMPLATE


class ApiParameterTestCase(TestCase):
    """ ALl parameter checks are performed on the catalogue API since this is the most requested one

    """

    def setUp(self):
        # requires services
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        create_wms_service(group=self.user.groups.first(), how_much_services=10)
        self.api_catalogue_uri = reverse("api:catalogue-list")

        # Get some fragment from a metadata title as value for parameter q
        self.q_param = Metadata.objects.all().first().title
        self.q_param = self.q_param[int(len(self.q_param)/2):-1]

    def test_q(self):
        """ Tests the functionality of parameter 'q'

        Returns:

        """
        params = {
            "q": self.q_param,
            "format": "json",
            "q-test": True
        }
        response = self.client.get(
            self.api_catalogue_uri,
            data=params
        )
        self.assertEqual(200, response.status_code)

        try:
            response_json = json.loads(response.content)
        except JSONDecodeError as e:
            self.fail(INVALID_STATUS_CODE_TEMPLATE.format(e))

        results = response_json["results"]
        valid_results = [self.q_param in result["title"] or self.q_param in result["abstract"] or (self.q_param in kw for kw in result["keywords"]) for result in results]

        # Assert true at least ones!
        self.assertIn(True, valid_results, msg="Results were returned which should not have been returned! q: {}, results: {}".format(self.q_param, results))

    # ToDo: Add better test data to add more useful tests