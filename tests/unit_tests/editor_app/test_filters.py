"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 24.04.20

"""
from django.test import TestCase

from editor.filters import EditorAccessFilter
from service.filters import MetadataWmsFilter, MetadataWfsFilter
from service.helper.enums import OGCServiceEnum
from service.models import Metadata
from tests.baker_recipes.db_setup import create_superadminuser, create_wms_service, create_wfs_service
from tests.utils import check_filtering


class EditorFiltersTestCase(TestCase):

    def setUp(self):
        self.user = create_superadminuser()

        self.user_groups = self.user.get_groups()

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

    def test_editor_access_group_filtering(self):
        """ Tests the EditorAccessFilter functionality

        Returns:

        """
        result = check_filtering(
            EditorAccessFilter,
            "q",
            "name",
            self.user_groups
        )
        self.assertTrue(result, msg="EditorAccessFilter not filtered properly")
