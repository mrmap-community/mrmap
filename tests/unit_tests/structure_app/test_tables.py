"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 22.04.20

"""
from django.test import TestCase, RequestFactory
from structure.models import MrMapGroup
from structure.tables import GroupTable
from tests import utils
from tests.baker_recipes.db_setup import create_guest_groups, create_superadminuser, \
    create_public_organization, create_random_named_orgas
from tests.baker_recipes.structure_app.baker_recipes import PASSWORD


class StructureTablesTestCase(TestCase):

    def setUp(self):
        # creates user object in db
        self.user_password = PASSWORD
        self.groups = create_guest_groups(how_much_groups=9)
        self.user = create_superadminuser(groups=self.groups)
        self.orgas = create_random_named_orgas(
            user=self.user,
            how_much_orgas=10
        )
        # Set individual organization for each group
        i = 0
        for group in self.groups:
            group.organization = self.orgas[i]
            group.save()
            i = i+1

        # Public group needs an organization for this test
        public_orga = create_public_organization(
            user=self.user,
        )[0]
        public_group = MrMapGroup.objects.get(is_public_group=True)
        public_group.organization = public_orga
        public_group.save()

        self.user.organization = self.orgas[0]
        self.user.save()
        self.user.refresh_from_db()

        self.request_factory = RequestFactory()

    def test_group_table_sorting(self):
        """ Run test to check the sorting functionality of the group tables

        Return:

        """
        # Get all groups, make sure the initial set is ordered by random
        groups = MrMapGroup.objects.all().order_by("?")

        # Then create a table using the queryset, which orders by group description
        group_table = GroupTable(
            groups,
            order_by_field="sg",
            user=None
        )

        # Check table sorting
        sorting_implementation_failed, sorting_results = utils.check_table_sorting(
            table=group_table,
            url_path_name="structure:groups-index",
            sorting_parameter="sg"
        )

        for key, val in sorting_results.items():
            self.assertTrue(val, msg="Group table sorting not correct for column '{}'".format(key))
        for key, val in sorting_implementation_failed.items():
            self.assertFalse(val, msg="Group table sorting leads to error for column '{}'".format(key))

