# common classes for handling of OWS (OGC Webservices)
# for naming conventions see http://portal.opengeospatial.org/files/?artifact_id=38867
from service.helper.common_connector import CommonConnector
from service.helper.enums import ConnectionType, VersionTypes, ServiceTypes


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

    def get_service_metadata_v100(self, xml_obj):
        pass

    def get_service_metadata_v110(self, xml_obj):
        pass

    def get_service_metadata_v111(self, xml_obj):
        """ Returns the xml as iterable object

        Args:
            xml_obj: The xml as iterable object
        Returns:
            nothing
        """

        # Since it may be possible that data providers do not put information where they have to be, we need to
        # build these ugly try catches and always check for list structures where lists could happen

        try:
            self.service_identification_abstract = xml_obj.xpath("//Service/Abstract")[0].text
        except IndexError:
            pass
        try:
            self.service_identification_title = xml_obj.xpath("//Service/Title")[0].text
        except IndexError:
            pass
        try:
            self.service_identification_fees = xml_obj.xpath("//Service/Fees")[0].text
        except IndexError:
            pass
        try:
            self.service_identification_accessconstraints = xml_obj.xpath("//Service/AccessConstraints")[0].text
        except IndexError:
            pass
        try:
            self.service_provider_providername = xml_obj.xpath("//Service/ContactInformation/ContactPersonPrimary/ContactOrganization")[0].text
        except IndexError:
            pass
        try:
            self.service_provider_contact_contactinstructions = xml_obj.xpath("//Service/ContactInformation")[0]
        except IndexError:
            pass
        try:
            self.service_provider_responsibleparty_individualname = xml_obj.xpath("//Service/ContactInformation/ContactPersonPrimary/ContactPerson")[0].text
        except IndexError:
            pass
        try:
            self.service_provider_responsibleparty_positionname = xml_obj.xpath("//Service/ContactInformation/ContactPersonPrimary/ContactPosition")[0].text
        except IndexError:
            pass
        try:
            self.service_provider_telephone_voice = xml_obj.xpath("//Service/ContactInformation/ContactVoiceTelephone")[0].text
        except IndexError:
            pass
        try:
            self.service_provider_telephone_facsimile = xml_obj.xpath("//Service/ContactInformation/ContactFacsimileTelephone")[0].text
        except IndexError:
            pass
        try:
            self.service_provider_address_electronicmailaddress = xml_obj.xpath("//Service/ContactInformation/ContactElectronicMailAddress")[0].text
        except IndexError:
            pass
        try:
            keywords = xml_obj.xpath("//Service/KeywordList/Keyword")
            kw = []
            for keyword in keywords:
                kw.append(keyword.text)
            self.service_identification_keywords = kw
        except IndexError:
            pass
        try:
            elements = xml_obj.xpath("//Service/OnlineResource")
            ors = []
            for element in elements:
                ors.append(element.get("{http://www.w3.org/1999/xlink}href"))
            self.service_provider_onlineresource_linkage = ors
        except IndexError:
            pass
        try:
            self.service_provider_address_country = xml_obj.xpath("//Service/ContactInformation/ContactAddress/Country")[0].text
        except IndexError:
            pass
        try:
            self.service_provider_address_postalcode = xml_obj.xpath("//Service/ContactInformation/ContactAddress/PostCode")[0].text
        except IndexError:
            pass
        try:
            self.service_provider_address_city = xml_obj.xpath("//Service/ContactInformation/ContactAddress/City")[0].text
        except IndexError:
            pass
        try:
            self.service_provider_address_state_or_province = xml_obj.xpath("//Service/ContactInformation/ContactAddress/StateOrProvince")[0].text
        except IndexError:
            pass
        try:
            self.service_provider_address = xml_obj.xpath("//Service/ContactInformation/ContactAddress/Address")[0].text
        except IndexError:
            pass

    def get_service_metadata_v130(self, xml_obj):
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

