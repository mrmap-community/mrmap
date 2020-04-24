"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 24.04.20

"""
from django.test import TestCase

from MapSkinner import utils
from structure.filters import GroupFilter, OrganizationFilter
from structure.models import Organization, MrMapGroup
from tests.baker_recipes.db_setup import create_superadminuser, create_random_named_orgas, create_guest_groups
from tests.baker_recipes.structure_app.baker_recipes import PASSWORD
from tests.utils import check_filtering


class StructureFiltersTestCase(TestCase):

    def setUp(self):
        self.user_password = PASSWORD
        self.groups = create_guest_groups(how_much_groups=9)
        self.user = create_superadminuser(groups=self.groups)
        self.orgas = create_random_named_orgas(
            user=self.user,
            how_much_orgas=10
        )
        self.orgas = Organization.objects.all().order_by("?")
        self.groups = MrMapGroup.objects.all().order_by("?")

    def test_group_filtering(self):
        """ Tests the GroupFilter functionality

        Returns:

        """
        result = check_filtering(
            GroupFilter,
            "gsearch",
            "name",
            self.groups
        )
        self.assertTrue(result, msg="GroupFilter not filtered properly")

    def test_organization_filtering(self):
        """ Tests the GroupFilter functionality

        Returns:

        """
        result = check_filtering(
            OrganizationFilter,
            "osearch",
            "organization_name",
            self.orgas
        )
        self.assertTrue(result, msg="OrganizationFilter not filtered properly")
