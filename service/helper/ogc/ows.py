# common classes for handling of OWS (OGC Webservices)
# for naming conventions see http://portal.opengeospatial.org/files/?artifact_id=38867
from abc import abstractmethod
from xml.dom.minidom import Text

from service.helper.common_connector import CommonConnector
from service.helper.enums import ConnectionType, VersionTypes, ServiceTypes
from service.helper import service_helper


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
        self.service_identification_title = None
        self.service_identification_abstract = None
        self.service_identification_keywords = []
        self.service_identification_fees = None
        self.service_identification_accessconstraints = None
        
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

        # v.1.3.0.0
        self.layer_limit = None
        self.max_width = None
        self.max_height = None


        # initialize service from url
        if service_capabilities_xml is not None:
            # load from given xml
            print("try to load from given xml document")
        else:
            # load from url
            self.get_capabilities()
        # Parse capabilities - depending on service_type and service_version
        if self.service_type is ServiceTypes.WMS and self.service_version is VersionTypes.V_1_1_1:
                # self.service_object = OGCWebMapService_1_1_1(self.service_capabilities_xml)
                pass

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

    def get_service_metadata_wfs(self, xml_obj):
        ############    SERVICE     ############
        service_node = xml_obj.getElementsByTagName("Service")
        # TITLE
        title_node = service_helper.get_node_from_node_list(service_node, "Title")
        self.service_identification_title = service_helper.get_text_from_node(title_node)

        # ABSTRACT
        abstract_node = service_helper.get_node_from_node_list(service_node, "Abstract")
        self.service_identification_abstract = service_helper.get_text_from_node(abstract_node)

        # FEES
        fees_node = service_helper.get_node_from_node_list(service_node, "Fees")
        self.service_identification_fees = service_helper.get_text_from_node(fees_node)

        # ACCESS CONSTRAINTS
        ac_node = service_helper.get_node_from_node_list(service_node, "AccessConstraints")
        self.service_identification_accessconstraints = service_helper.get_text_from_node(ac_node)

        # KEYWORDS
        keywords_node = service_helper.get_node_from_node_list(service_node, "Keywords")
        keywords_str = service_helper.get_text_from_node(keywords_node)
        self.service_identification_keywords = service_helper.resolve_keywords_array_string(keywords_str)

        # ONLINE RESOURCE
        or_node = service_helper.get_node_from_node_list(service_node, "OnlineResource")
        self.service_provider_onlineresource_linkage = service_helper.get_text_from_node(or_node)

        ############    CAPABILITY     ############
        cap_node = xml_obj.getElementsByTagName("Capability")
        # GET CAPABILITIES
        get_cap_node = service_helper.find_node_recursive(cap_node, "Get")

    def _get_service_metadata_wms(self, xml_obj):
        """ This private function holds the main parsable elements which are part of every wms specification starting at 1.0.0

        Args:
            xml_obj: The iterable xml object tree
        Returns:
            Nothing
        """
        # Since it may be possible that data providers do not put information where they have to be, we need to
        # build these ugly try catches and always check for list structures where lists could happen
        try:
            self.service_identification_abstract = xml_obj.xpath("//Service/Abstract")[0].text
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_identification_title = xml_obj.xpath("//Service/Title")[0].text
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_identification_fees = xml_obj.xpath("//Service/Fees")[0].text
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_identification_accessconstraints = xml_obj.xpath("//Service/AccessConstraints")[0].text
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_provider_providername = xml_obj.xpath("//Service/ContactInformation/ContactPersonPrimary/ContactOrganization")[0].text
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_provider_url = xml_obj.xpath("//AuthorityURL")[0].get("xlink:href")
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_provider_contact_contactinstructions = xml_obj.xpath("//Service/ContactInformation")[0]
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_provider_responsibleparty_individualname = xml_obj.xpath("//Service/ContactInformation/ContactPersonPrimary/ContactPerson")[0].text
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_provider_responsibleparty_positionname = xml_obj.xpath("//Service/ContactInformation/ContactPersonPrimary/ContactPosition")[0].text
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_provider_telephone_voice = xml_obj.xpath("//Service/ContactInformation/ContactVoiceTelephone")[0].text
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_provider_telephone_facsimile = xml_obj.xpath("//Service/ContactInformation/ContactFacsimileTelephone")[0].text
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_provider_address_electronicmailaddress = xml_obj.xpath("//Service/ContactInformation/ContactElectronicMailAddress")[0].text
        except (IndexError, AttributeError) as error:
            pass
        try:
            keywords = xml_obj.xpath("//Service/KeywordList/Keyword")
            kw = []
            for keyword in keywords:
                kw.append(keyword.text)
            self.service_identification_keywords = kw
        except (IndexError, AttributeError) as error:
            pass
        try:
            elements = xml_obj.xpath("//Service/OnlineResource")
            ors = []
            for element in elements:
                ors.append(element.get("{http://www.w3.org/1999/xlink}href"))
            self.service_provider_onlineresource_linkage = ors
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_provider_address_country = xml_obj.xpath("//Service/ContactInformation/ContactAddress/Country")[0].text
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_provider_address_postalcode = xml_obj.xpath("//Service/ContactInformation/ContactAddress/PostCode")[0].text
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_provider_address_city = xml_obj.xpath("//Service/ContactInformation/ContactAddress/City")[0].text
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_provider_address_state_or_province = xml_obj.xpath("//Service/ContactInformation/ContactAddress/StateOrProvince")[0].text
        except (IndexError, AttributeError) as error:
            pass
        try:
            self.service_provider_address = xml_obj.xpath("//Service/ContactInformation/ContactAddress/Address")[0].text
        except (IndexError, AttributeError) as error:
            pass


    def get_service_metadata_v100(self, xml_obj, service_type):
        """ This function calls the main parser function and adds version specific parsing

        Args:
            xml_obj: The iterable xml object tree
        Returns:
             Nothing
        """
        # the general structures of WMS and WFS are too different.
        # we need to distinguish between them and use own functions on each
        if service_type is ServiceTypes.WMS:
            self._get_service_metadata_wms(xml_obj)
        elif service_type is ServiceTypes.WFS:
            self.get_service_metadata_wfs(xml_obj)
        else:
            pass

    def get_service_metadata_v110(self, xml_obj, service_type):
        """ This function calls the main parser function and adds version specific parsing

        Args:
            xml_obj: The iterable xml object tree
        Returns:
             Nothing
        """
        # the general structures of WMS and WFS are too different.
        # we need to distinguish between them and use own functions on each
        if service_type is ServiceTypes.WMS:
            self._get_service_metadata_wms(xml_obj)
        elif service_type is ServiceTypes.WFS:
            self.get_service_metadata_wfs(xml_obj)
        else:
            pass

    def get_service_metadata_v111(self, xml_obj, service_type):
        """ This function calls the main parser function and adds version specific parsing

        Args:
            xml_obj: The iterable xml object tree
        Returns:
             Nothing
        """
        # the general structures of WMS and WFS are too different.
        # we need to distinguish between them and use own functions on each
        if service_type is ServiceTypes.WMS:
            self._get_service_metadata_wms(xml_obj)
        elif service_type is ServiceTypes.WFS:
            self.get_service_metadata_wfs(xml_obj)
        else:
            pass

    def get_service_metadata_v130(self, xml_obj, service_type):
        """ This function calls the main parser function and adds version specific parsing

        Args:
            xml_obj: The iterable xml object tree
        Returns:
             Nothing
        """
        # first try to parse all default elements
        # the general structures of WMS and WFS are too different.
        # we need to distinguish between them and use own functions on each
        if service_type is ServiceTypes.WMS:
            self._get_service_metadata_wms(xml_obj)
        elif service_type is ServiceTypes.WFS:
            self.get_service_metadata_wfs(xml_obj)
        else:
            pass
        # layer limit is new
        try:
            layer_limit = xml_obj.xpath("//LayerLimit")[0].text
            self.layer_limit = layer_limit
        except (IndexError, AttributeError) as error:
            pass
        # max height and width is new
        try:
            max_width = xml_obj.xpath("//MaxWidth")[0].text
            self.max_width = max_width
        except (IndexError, AttributeError) as error:
            pass
        try:
            max_height = xml_obj.xpath("//MaxHeight")[0].text
            self.max_height = max_height
        except (IndexError, AttributeError) as error:
            pass


class OWSServiceMetadata:
    def __init__(self):
        self.section = "all" # serviceIdentification, serviceProvider, operationMetadata, contents, all
        # version = ""
        # update_sequence = ""


class OWSRequestHandler:
    def built_request(self):
        pass

    def do_request(self):
        pass

    def parse_result(self):
        pass

    # def get_section(self):
    #    pass

