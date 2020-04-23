"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 22.04.20

"""
from django.test import TestCase, RequestFactory

from MapSkinner.consts import STRUCTURE_INDEX_GROUP
from structure.filters import GroupFilter
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
        self.url_path_name = STRUCTURE_INDEX_GROUP
        self.filter_param = "gsearch"
        self.sorting_param = "sg"

    def test_group_table_sorting(self):
        """ Run test to check the sorting functionality of the group tables

        Return:

        """
        # Get all groups, make sure the initial set is ordered by random
        groups = MrMapGroup.objects.all().order_by("?")
        table = GroupTable(
            groups,
            order_by_field=self.sorting_param,
            user=self.user
        )
        # Check table sorting
        sorting_implementation_failed, sorting_results = utils.check_table_sorting(
            table=table,
            url_path_name=self.url_path_name,
            sorting_parameter=self.sorting_param
        )

        for key, val in sorting_results.items():
            self.assertTrue(val, msg="Group table sorting not correct for column '{}'".format(key))
        for key, val in sorting_implementation_failed.items():
            self.assertFalse(val, msg="Group table sorting leads to error for column '{}'".format(key))

    def test_group_table_filtering(self):
        """ Run test to check the filtering functionality of the group tables

        Return:

        """
        groups = MrMapGroup.objects.all()
        table = GroupTable(
            groups,
            order_by_field=self.sorting_param,
            user=self.user
        )

        filter_results = utils.check_table_filtering(
            table=table,
            filter_parameter=self.filter_param,
            queryset=groups,
            filter_class=GroupFilter,
            table_class=GroupTable,
            user=self.user,
        )

        for key, val in filter_results.items():
            self.assertTrue(val, msg="Group table filtering not correct for column '{}'".format(key))
