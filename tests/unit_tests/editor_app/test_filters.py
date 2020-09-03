"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 24.04.20

"""
from django.test import TestCase, RequestFactory

from editor.filters import EditorAccessFilter
from service.filters import MetadataWmsFilter, MetadataWfsFilter
from service.helper.enums import OGCServiceEnum
from service.models import Metadata
from structure.models import MrMapGroup
from tests.baker_recipes.db_setup import create_superadminuser, create_wms_service, create_wfs_service, \
    create_guest_groups
from tests.utils import check_filtering


class EditorFiltersTestCase(TestCase):

    def setUp(self):
        self.user = create_superadminuser()

        self.user_groups = self.user.get_groups()
        self.guest_groups = create_guest_groups(how_much_groups=10)

        create_wms_service(group=self.user.get_groups().first(), how_much_services=10)
        create_wfs_service(group=self.user.get_groups().first(), how_much_services=10)
        self.wms_service_metadatas = Metadata.objects.filter(
            service__service_type__name=OGCServiceEnum.WMS.value
        )
        self.wfs_service_metadatas = Metadata.objects.filter(
            service__service_type__name=OGCServiceEnum.WFS.value
        )

    def test_editor_wms_filtering(self):
        """ Tests the GroupFilter functionality

        Returns:

        """
        result = check_filtering(
            MetadataWmsFilter,
            "wms_search",
            "title",
            self.wms_service_metadatas
        )
        self.assertTrue(result, msg="MetadataWmsFilter not filtered properly")

    def test_editor_wfs_filtering(self):
        """ Tests the GroupFilter functionality

        Returns:

        """
        result = check_filtering(
            MetadataWfsFilter,
            "wfs_search",
            "title",
            self.wfs_service_metadatas
        )
        self.assertTrue(result, msg="MetadataWfsFilter not filtered properly")

    def test_editor_access_group_filtering_by_name(self):
        """ Tests the EditorAccessFilter functionality

        Returns:

        """
        # Check name filtering
        result = check_filtering(
            EditorAccessFilter,
            "q",
            "name",
            self.user_groups
        )
        self.assertTrue(result, msg="EditorAccessFilter not filtered properly")

    def test_editor_access_group_filtering_user_groups(self):
        """ Tests the EditorAccessFilter functionality

        Returns:

        """
        # Check user group filtering
        all_groups = MrMapGroup.objects.all()

        # Create an instance of a GET request.
        request_factory = RequestFactory()
        request = request_factory.get('/')
        request.user = self.user

        filtered_qs = EditorAccessFilter(
            {
                "mg": True
            },
            all_groups,
            request=request
        ).qs

        self.assertLess(filtered_qs.count(), all_groups.count())
        self.assertEqual(filtered_qs.count(), self.user_groups.count())

    def test_editor_access_group_filtering_user_org_groups(self):
        """ Tests the EditorAccessFilter functionality

        Returns:

        """
        # Check user group filtering
        all_groups = MrMapGroup.objects.all()

        # Create an instance of a GET request.
        request_factory = RequestFactory()
        request = request_factory.get('/')
        request.user = self.user

        filtered_qs = EditorAccessFilter(
            {
                "mog": True
            },
            all_groups,
            request=request
        ).qs
        org_groups = all_groups.filter(
            organization=self.user.organization
        )

        self.assertLess(filtered_qs.count(), all_groups.count())
        self.assertEqual(filtered_qs.count(), org_groups.count())
