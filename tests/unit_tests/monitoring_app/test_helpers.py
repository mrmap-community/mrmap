"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG, Bonn, Germany
Contact: suleiman@terrestris.de
Created on: 26.02.2020

"""

import os

from django.contrib.auth.hashers import make_password
from django.test import TestCase
from django.utils import timezone

from monitoring.helper.urlHelper import UrlHelper
from monitoring.helper.wfsHelper import WfsHelper
from monitoring.helper.wmsHelper import WmsHelper
from service.helper import service_helper
from service.helper.enums import OGCServiceVersionEnum, OGCServiceEnum, MetadataEnum
from service.models import Metadata
from structure.models import Permission, Role, MrMapGroup, MrMapUser
from structure.permissionEnums import PermissionEnum


class MonitoringTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        # create superuser
        all_perm_choices = PermissionEnum.as_choices(drop_empty_choice=True)
        [Permission.objects.get_or_create(name=choice[1]) for choice in all_perm_choices]

        role = Role.objects.create(
            name="Testrole",
        )
        all_permissions = list(Permission.objects.all())
        role.permissions.add(*all_permissions)

        cls.pw = "test"
        salt = str(os.urandom(25).hex())
        pw = cls.pw
        cls.user = MrMapUser.objects.create(
            username="Testuser",
            is_active=True,
            salt=salt,
            password=make_password(pw, salt=salt),
            confirmed_dsgvo=timezone.now(),
        )

        cls.group = MrMapGroup.objects.create(
            name="Testgroup",
            role=role,
            created_by=cls.user,
        )

        cls.user.groups.add(cls.group)

        cls.wfs_base = "https://www.wfs.nrw.de/geobasis/wfs_nw_alkis_vereinfacht?"
        cls.test_wfs = {
            "title": "Nutzung",
            "version": OGCServiceVersionEnum.V_2_0_0,
            "type": OGCServiceEnum.WFS,
            "uri": cls.wfs_base
        }

        # Creating a new service model instance
        wfs_service = service_helper.create_service(
            cls.test_wfs["type"],
            cls.test_wfs["version"],
            cls.test_wfs["uri"],
            cls.user,
            cls.group
        )
        wfs_service.save()
        cls.wfs_service = wfs_service

        cls.wms_base = "https://www.wms.nrw.de/geobasis/wms_nw_dtk25?"
        cls.wms_layername = "WMS_NW_DTK25"
        cls.test_wms = {
            "title": "Karte RP",
            "version": OGCServiceVersionEnum.V_1_3_0,
            "type": OGCServiceEnum.WMS,
            "uri": cls.wms_base
        }

        # Creating a new service model instance
        wms_service = service_helper.create_service(
            cls.test_wms["type"],
            cls.test_wms["version"],
            cls.test_wms["uri"],
            cls.user,
            cls.group
        )
        wms_service.save()
        cls.wms_service = wms_service

        metadatas = Metadata.objects.all()
        wfs_services = [m for m in metadatas if m.metadata_type == MetadataEnum.SERVICE.value]
        wfs = [m for m in wfs_services if m.service.service_type.name == OGCServiceEnum.WFS.value]
        cls.metadata_wfs = wfs[0]
        cls.metadata_wms = Metadata.objects.filter(identifier=cls.wms_layername)[0]

    def test_wfs_get_capabilities_url(self):
        service = self.metadata_wfs.service
        wfs_helper = WfsHelper(service)
        expected_url = (
            'https://www.wfs.nrw.de/geobasis/wfs_nw_alkis_vereinfacht?'
            'REQUEST=GetCapabilities&VERSION=2.0.0&SERVICE=wfs'
        )
        self.assertURLEqual(wfs_helper.get_capabilities_url, expected_url)

    def test_wfs_get_list_stored_queries_url(self):
        service = self.metadata_wfs.service
        wfs_helper = WfsHelper(service)
        list_stored_queries_url = wfs_helper.get_list_stored_queries()
        expected_url = (
            'https://www.wfs.nrw.de/geobasis/wfs_nw_alkis_vereinfacht?'
            'REQUEST=ListStoredQueries&VERSION=2.0.0&SERVICE=wfs'
        )
        self.assertURLEqual(list_stored_queries_url, expected_url)

    # def test_wfs_get_describe_featuretype_url(self):
    #     service = self.metadata_wfs.service
    #     wfs_helper = WfsHelper(service)
    #     featuretype = service.featurtypes.all()[0]
    #     describe_featuretype_url = wfs_helper.get_describe_featuretype_url(str(featuretype))
    #     expected_url = (
    #         'https://www.wfs.nrw.de/geobasis/wfs_nw_alkis_vereinfacht?'
    #         'REQUEST=describeFeatureType&VERSION=2.0.0&SERVICE=wfs&typeNames=dvg:nw_dvg2_bld'
    #     )
    #     self.assertURLEqual(describe_featuretype_url, expected_url)

    # def test_wfs_get_get_feature_url(self):
    #     service = self.metadata_wfs.service
    #     wfs_helper = WfsHelper(service)
    #     featuretype = service.featurtypes.all()[0]
    #     get_feature_url = wfs_helper.get_get_feature_url(str(featuretype))
    #     expected_url = (
    #         'https://www.wfs.nrw.de/geobasis/wfs_nw_alkis_vereinfacht?'
    #         'REQUEST=getFeature&VERSION=2.0.0&SERVICE=wfs&typeNames=dvg:nw_dvg2_bld&COUNT=1'
    #     )
    #     self.assertURLEqual(get_feature_url, expected_url)

    def test_wms_get_capabilities_url(self):
        service = self.metadata_wms.service
        wms_helper = WmsHelper(service)
        expected_url = (
            'https://www.wms.nrw.de/geobasis/wms_nw_dtk25?'
            'REQUEST=GetCapabilities&VERSION=1.3.0&SERVICE=wms'
        )
        self.assertURLEqual(wms_helper.get_capabilities_url, expected_url)

    def test_wms_get_map_url(self):
        service = self.metadata_wms.service
        wms_helper = WmsHelper(service)
        get_map_url = wms_helper.get_get_map_url()
        expected_url = (
            'https://www.wms.nrw.de/geobasis/wms_nw_dtk25?'
            'REQUEST=GetMap&VERSION=1.3.0&SERVICE=wms&LAYERS=WMS_NW_DTK25'
            '&CRS=EPSG:4326&BBOX=5.72499,50.1506,9.53154,52.602'
            '&STYLES=&WIDTH=1&HEIGHT=1&FORMAT=None'
        )
        self.assertURLEqual(get_map_url, expected_url)

    def test_wms_get_feature_info_url(self):
        service = self.metadata_wms.service
        wms_helper = WmsHelper(service)
        get_feature_info_url = wms_helper.get_get_feature_info_url()
        expected_url = (
            'https://www.wms.nrw.de/geobasis/wms_nw_dtk25?'
            'REQUEST=GetFeatureInfo&VERSION=1.3.0&SERVICE=wms'
            '&LAYERS=WMS_NW_DTK25&CRS=EPSG:4326&BBOX=5.72499,50.1506,9.53154,52.602'
            '&STYLES=&WIDTH=1&HEIGHT=1&QUERY_LAYERS=WMS_NW_DTK25&I=0&J=0'
        )
        self.assertURLEqual(get_feature_info_url, expected_url)

    def test_wms_describe_layer_url(self):
        service = self.metadata_wms.service
        wms_helper = WmsHelper(service)
        describe_layer_url = wms_helper.get_describe_layer_url()
        expected_url = (
            'https://www.wms.nrw.de/geobasis/wms_nw_dtk25?'
            'HEIGHT=1&REQUEST=DescribeLayer&VERSION=1.1.1&SERVICE=wms&LAYERS=WMS_NW_DTK25&WIDTH=1'
        )
        self.assertURLEqual(describe_layer_url, expected_url)

    def test_wms_get_legend_graphic_url(self):
        return
        # ToDo: fix this test case
        service = self.metadata_wms.service
        wms_helper = WmsHelper(service)
        get_legend_graphic_url = wms_helper.get_get_legend_graphic_url()
        expected_url = (
            'https://www.wms.nrw.de/geobasis/wms_nw_dtk25?'
            'REQUEST=GetLegendGraphic&LAYER=WMS_NW_DTK25&FORMAT=image/png&SERVICE=wms&VERSION=1.3.0'
        )
        self.assertURLEqual(get_legend_graphic_url, expected_url)

    def test_wms_get_styles_url(self):
        service = self.metadata_wms.service
        wms_helper = WmsHelper(service)
        get_styles_url = wms_helper.get_get_styles_url()
        expected_url = (
            'https://www.wms.nrw.de/geobasis/wms_nw_dtk25?'
            'SERVICE=wms&REQUEST=GetStyles&VERSION=1.1.1&LAYERS=WMS_NW_DTK25'
        )
        self.assertURLEqual(get_styles_url, expected_url)

    def test_url_build(self):
        base_url = 'http://example.com'
        queries = [('q1', 'foo'), ('q2', 'bar'), ('q2', 'baz')]
        url_helper = UrlHelper()
        url = url_helper.build(base_url, queries)
        expected_url = 'http://example.com?q1=foo&q2=baz'
        self.assertURLEqual(url, expected_url)
