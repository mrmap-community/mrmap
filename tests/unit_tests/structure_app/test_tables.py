"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 22.04.20

"""
from django.test import TestCase, RequestFactory

from MrMap.consts import STRUCTURE_INDEX_ORGANIZATION
from structure.models import Organization
from structure.tables.tables import OrganizationTable
from tests import utils
from tests.baker_recipes.db_setup import create_superadminuser, create_non_autogenerated_orgas
from tests.baker_recipes.structure_app.baker_recipes import PASSWORD


class StructureTablesTestCase(TestCase):

    def setUp(self):
        # creates user object in db
        self.user_password = PASSWORD
        self.user = create_superadminuser()
        self.orgas = create_non_autogenerated_orgas(
            user=self.user,
            how_much_orgas=10
        )

        self.user.organization = self.orgas[0]
        self.user.save()
        self.user.refresh_from_db()

        self.request_factory = RequestFactory()
        # Create an instance of a GET request.
        self.request = self.request_factory.get('/')
        # Recall that middleware are not supported. You can simulate a
        # logged-in user by setting request.user manually.
        self.request.user = self.user

        self.orgs_url_path_name = STRUCTURE_INDEX_ORGANIZATION

    def test_organization_table_sorting(self):
        """ Run test to check the sorting functionality of the group tables

        Return:

        """
        # Get all groups, make sure the initial set is ordered by random
        orgs = Organization.objects.all().order_by("?")
        sorting_param = "sort"
        table = OrganizationTable(
            data=orgs,
            order_by_field=sorting_param,
            request=self.request
        )
        # Check table sorting
        sorting_implementation_failed, sorting_results = utils.check_table_sorting(
            table=table,
            url_path_name=self.orgs_url_path_name,
        )

        for key, val in sorting_results.items():
            self.assertTrue(val, msg="Organization table sorting not correct for column '{}'".format(key))
        for key, val in sorting_implementation_failed.items():
            self.assertFalse(val, msg="Organization table sorting leads to error for column '{}'".format(key))
