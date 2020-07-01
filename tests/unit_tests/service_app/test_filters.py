"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.04.20

"""
from django.test import TestCase

from service.filters import MetadataWmsFilter, MetadataWfsFilter
from service.helper.enums import OGCServiceEnum
from service.models import Metadata
from tests.baker_recipes.db_setup import create_superadminuser, create_wms_service
from tests.baker_recipes.structure_app.baker_recipes import PASSWORD
from tests.utils import check_filtering


class ServiceFiltersTestCase(TestCase):

    def setUp(self):
        self.user_password = PASSWORD
        self.user = create_superadminuser()
        create_wms_service(group=self.user.get_groups().first(), how_much_services=10)
        create_wms_service(group=self.user.get_groups().first(), how_much_services=10)

        self.wms_metadatas = Metadata.objects.filter(
            service__service_type__name=OGCServiceEnum.WMS.value
        )
        self.wfs_metadatas = Metadata.objects.filter(
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
            self.wms_metadatas
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
            self.wfs_metadatas
        )
        self.assertTrue(result, msg="MetadataWfsFilter not filtered properly")
