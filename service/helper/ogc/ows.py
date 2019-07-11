# common classes for handling of OWS (OGC Webservices)
# for naming conventions see http://portal.opengeospatial.org/files/?artifact_id=38867

from abc import abstractmethod

from django.contrib.gis.geos import Polygon
from django.db import transaction

from service.helper import service_helper
from service.helper.common_connector import CommonConnector
from service.helper.enums import ConnectionType, VersionTypes, ServiceTypes
from service.helper.iso.isoMetadata import ISOMetadata
from structure.models import User


class OGCWebService:
    """ The base class for all derived web services

    """
    def __init__(self, service_connect_url=None, service_type=ServiceTypes.WMS, service_version=VersionTypes.V_1_1_1, auth=None, service_capabilities_xml=None):
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


        # initialize service from url
        # if service_capabilities_xml is not None:
        #     # load from given xml
        #     print("try to load from given xml document")
        # else:
        #     # load from url
        #     self.get_capabilities()

        class Meta:
            abstract = True


    def get_capabilities(self):
        """ Start a network call to retrieve the original capabilities xml document.

        Using the connector class, this function will GET the capabilities xml document as string.
        No file will be downloaded and stored on the storage. The string will be stored in the OGCWebService instance.

        Returns:
             nothing
        """
        # if (self.auth != None and self.auth.auth_user != None and self.auth.auth_password != None):
        #    auth = {"auth_user":self.auth_user, "auth_password":self.auth_password, "auth_type":self.auth_type}
        # auth = self.auth
        # else:
        #    auth = None
        self.service_connect_url = self.service_connect_url + \
                                   '&REQUEST=GetCapabilities' + '&VERSION=' + self.service_version.value + \
                                   '&SERVICE=' + self.service_type.value
        ows_connector = CommonConnector(url=self.service_connect_url,
                                        auth=self.auth,
                                        connection_type=ConnectionType.REQUESTS)
        ows_connector.http_method = 'GET'
        ows_connector.load()
        if ows_connector.status_code != 200:
            raise ConnectionError(ows_connector.status_code)
        if ows_connector.encoding is not None:
            self.service_capabilities_xml = ows_connector.content.decode(ows_connector.encoding)
        else:
            self.service_capabilities_xml = ows_connector.text
            
        self.connect_duration = ows_connector.load_time
        self.descriptive_document_encoding = ows_connector.encoding
    # def invoke_operation(self, operation_name, dcp_type, dcp_method):
    #    pass
    
    # def list_operations(self, dcp_type='http'):
    #    pass
    
    def check_ogc_exception(self):
        pass

    """
    Methods that have to be implemented in the sub classes
    """
    @abstractmethod
    def create_from_capabilities(self, metadata_only: bool = False):
        pass

    @abstractmethod
    def get_service_metadata(self, xml_obj):
        pass

    @abstractmethod
    def get_version_specific_metadata(self, xml_obj):
        pass

    @abstractmethod
    def get_service_iso_metadata(self, xml_obj):
        """ Parse iso metadata for the whole service and merge the data with the capabilities service metadata.

        Since there might be differences between the ISO metadata and the capabilities metadata we need to declare
        a few best practices:
        1. Lists of information (e.g. keywords, spatial reference systems, ...) should be merged without duplicates
        2. If an information is already set...
            2.1. ... and the found information does not differ from the set one -> do nothing
            2.2. ... and the found information differs from the set one -> DO NOTHING! Yes this is strange but we have no way to qualify which

        Args:
            xml_obj: The xml etree object which is used for parsing
        Returns:
             nothing
        """
        # Must parse metadata document and merge metadata into this metadata object
        elem = "//inspire_common:URL"  # for wms by default
        if self.service_type is ServiceTypes.WFS:
            elem = "//wfs:MetadataURL"
        service_md_link = service_helper.try_get_text_from_xml_element(elem=elem, xml_elem=xml_obj)
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
        self.service_file_identifier = iso_metadata.file_identifier
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

