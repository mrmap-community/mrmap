"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 14.07.20

"""
from celery import Task

from service.helper import xml_helper
from service.helper.ogc.ows import OGCWebService
from service.models import ExternalAuthentication
from structure.models import MrMapUser


class OGCCatalogueService(OGCWebService):
    def __init__(self, service_connect_url, service_version, service_type, external_auth: ExternalAuthentication):
        super().__init__(
            service_connect_url=service_connect_url,
            service_version=service_version,
            service_type=service_type,
            external_auth=external_auth
        )

    def create_from_capabilities(self, metadata_only: bool = False, async_task: Task = None):
        # get xml as iterable object
        xml_obj = xml_helper.parse_xml(xml=self.service_capabilities_xml)

    def create_service_model_instance(self, user: MrMapUser, register_group, register_for_organization):
        pass

    def get_service_metadata_from_capabilities(self, xml_obj, async_task: Task = None):
        pass

    def get_version_specific_metadata(self, xml_obj):
        pass

    def get_service_dataset_metadata(self, xml_obj):
        pass

    def get_service_operations(self, xml_obj):
        pass

