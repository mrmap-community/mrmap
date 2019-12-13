# common classes for handling of OWS (OGC Webservices)
# for naming conventions see http://portal.opengeospatial.org/files/?artifact_id=38867

from abc import abstractmethod

from celery import Task
from django.contrib.gis.geos import Polygon
from django.db import transaction
from requests import ReadTimeout

from MapSkinner.messages import SERVICE_REGISTRATION_TIMEOUT
from service.helper import xml_helper
from service.helper.common_connector import CommonConnector
from service.helper.enums import ConnectionEnum, VersionEnum, ServiceEnum
from service.helper.iso.iso_metadata import ISOMetadata
from service.models import RequestOperation
from structure.models import User


class OGCWebService:
    """ The base class for all derived web services

    """
    def __init__(self, service_connect_url=None, service_type=ServiceEnum.WMS, service_version=VersionEnum.V_1_1_1, auth=None, service_capabilities_xml=None):
        self.service_connect_url = service_connect_url
        self.service_type = service_type  # wms, wfs, wcs, ...
        self.service_version = service_version  # 1.0.0, 1.1.0, ...
        self.service_capabilities_xml = service_capabilities_xml
        self.auth = auth
        self.descriptive_document_encoding = None
        self.connect_duration = None
        self.service_object = None
        
        # service_metadata
        self.service_file_identifier = None
        self.service_file_iso_identifier = None
        self.service_preview_image = None
        self.service_iso_md_uri = None
        self.service_identification_title = None
        self.service_identification_abstract = None
        self.service_identification_keywords = []
        self.service_identification_fees = None
        self.service_identification_accessconstraints = None

        self.service_last_change = None
        self.service_create_date = None
        self.service_bounding_box = None

        # service_provider
        self.service_provider_providername = None
        self.service_provider_url = None
        
        self.service_provider_responsibleparty_individualname = None
        self.service_provider_responsibleparty_positionname = None
        self.service_provider_responsibleparty_role = None
        
        self.service_provider_contact_hoursofservice = None
        self.service_provider_contact_contactinstructions = None
        self.service_provider_onlineresource_linkage = None
        
        self.service_provider_address = []
        self.service_provider_address_city = None
        self.service_provider_address_state_or_province = None
        self.service_provider_address_postalcode = []
        self.service_provider_address_country = []
        self.service_provider_address_electronicmailaddress = []
        
        self.service_provider_telephone_voice = []
        self.service_provider_telephone_facsimile = []

        # other
        self.linked_service_metadata = None

        # Capability
        self.get_capabilities_uri = None
        self.get_map_uri = None
        self.get_feature_info_uri = None
        self.describe_layer_uri = None
        self.get_legend_graphic_uri = None
        self.get_styles_uri = None

        class Meta:
            abstract = True

    def get_capabilities(self):
        """ Start a network call to retrieve the original capabilities xml document.

        Using the connector class, this function will GET the capabilities xml document as string.
        No file will be downloaded and stored on the storage. The string will be stored in the OGCWebService instance.

        Returns:
             nothing
        """
        self.service_connect_url = self.service_connect_url + \
                                   '&REQUEST=GetCapabilities' + '&VERSION=' + self.service_version.value + \
                                   '&SERVICE=' + self.service_type.value
        ows_connector = CommonConnector(url=self.service_connect_url,
                                        auth=self.auth,
                                        connection_type=ConnectionEnum.REQUESTS)
        ows_connector.http_method = 'GET'
        try:
            ows_connector.load()
            if ows_connector.status_code != 200:
                raise ConnectionError(ows_connector.status_code)
        except ReadTimeout:
            raise ConnectionError(SERVICE_REGISTRATION_TIMEOUT.format(self.service_connect_url))
        if ows_connector.encoding is not None:
            tmp = ows_connector.content.decode(ows_connector.encoding)
            # check if tmp really contains an xml file
            xml = xml_helper.parse_xml(tmp)
            if xml is None:
                raise Exception(tmp)
            self.service_capabilities_xml = tmp
        else:
            self.service_capabilities_xml = ows_connector.text
            
        self.connect_duration = ows_connector.run_time
        self.descriptive_document_encoding = ows_connector.encoding
    
    def check_ogc_exception(self):
        pass

    def has_iso_metadata(self, xml):
        """ Checks whether the xml element has an iso 19115 metadata record or not

        Args:
            xml: The xml etree object
        Returns:
             True if element has iso metadata, false otherwise
        """
        iso_metadata = xml_helper.try_get_element_from_xml(xml_elem=xml, elem="./MetadataURL")
        if len(iso_metadata) == 0:
            iso_metadata = xml_helper.try_get_element_from_xml(xml_elem=xml, elem="./wfs:MetadataURL")
        return len(iso_metadata) != 0


    """
    Methods that have to be implemented in the sub classes
    """
    @abstractmethod
    def get_service_operations(self, xml_obj, prefix: str):
        """ Creates table records from <Capability><Request></Request></Capability contents

        Args:
            xml_obj: The xml document object
            prefix: The prefix for the service type ('wms'/'wfs')
        Returns:

        """
        cap_request = xml_helper.try_get_single_element_from_xml("//{}Capability/{}Request".format(prefix, prefix), xml_obj)
        operations = cap_request.getchildren()
        for operation in operations:
            RequestOperation.objects.get_or_create(
                operation_name=operation.tag,
            )

    @abstractmethod
    def get_parser_prefix(self):
        pass

    @abstractmethod
    def create_from_capabilities(self, metadata_only: bool = False, async_task: Task = None):
        pass

    @abstractmethod
    def get_service_metadata_from_capabilities(self, xml_obj, async_task: Task = None):
        pass

    def get_service_metadata(self, uri: str, async_task: Task = None):
        """ Parses all service related information from the linked metadata document

        This does not fill the information into the main metadata record, but creates a new one, which will be linked
        using a MetadataRelation later.

        Args:
            uri (str): The service metadata uri
            async_task: The task object
        Returns:
            Nothing
        """
        iso_md = ISOMetadata(uri)
        iso_md.parse_xml()
        self.linked_service_metadata = iso_md

    @abstractmethod
    def get_version_specific_metadata(self, xml_obj):
        pass

    @abstractmethod
    def get_service_dataset_metadata(self, xml_obj):
        """

        Args:
            xml_obj: The xml etree object which is used for parsing
        Returns:
             nothing
        """
        # Must parse metadata document and merge metadata into this metadata object
        elem = "//inspire_common:URL"  # for wms by default
        if self.service_type is ServiceEnum.WFS:
            elem = "//wfs:MetadataURL"
        service_md_link = xml_helper.try_get_text_from_xml_element(elem=elem, xml_elem=xml_obj)
        # get iso metadata xml object
        if service_md_link is None:
            # no iso metadata provided
            return
        iso_metadata = ISOMetadata(uri=service_md_link)
        # add keywords
        for keyword in iso_metadata.keywords:
            self.service_identification_keywords.append(keyword)
        # add multiple other data that can not be found in the capabilities document
        self.service_create_date = iso_metadata.create_date
        self.service_last_change = iso_metadata.last_change_date
        self.service_iso_md_uri = iso_metadata.uri
        self.service_file_iso_identifier = iso_metadata.file_identifier
        self.service_identification_title = iso_metadata.title
        self.service_identification_abstract = iso_metadata.abstract
        bounding_points = (
            (float(iso_metadata.bounding_box["min_x"]), float(iso_metadata.bounding_box["min_y"])),
            (float(iso_metadata.bounding_box["min_x"]), float(iso_metadata.bounding_box["max_y"])),
            (float(iso_metadata.bounding_box["max_x"]), float(iso_metadata.bounding_box["max_y"])),
            (float(iso_metadata.bounding_box["max_x"]), float(iso_metadata.bounding_box["min_y"])),
            (float(iso_metadata.bounding_box["min_x"]), float(iso_metadata.bounding_box["min_y"]))
        )
        bbox = Polygon(bounding_points)
        self.service_bounding_box = bbox

    @abstractmethod
    def create_service_model_instance(self, user: User, register_group, register_for_organization):
        pass

    @transaction.atomic
    @abstractmethod
    def persist_service_model(self, service):
        pass


class OWSRequestHandler:
    def built_request(self):
        pass

    def do_request(self):
        pass

    def parse_result(self):
        pass

    # def get_section(self):
    #    pass

