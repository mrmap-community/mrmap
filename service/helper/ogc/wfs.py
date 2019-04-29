#common classes for handling of WFS (OGC WebFeatureServices)
#http://www.opengeospatial.org/standards/wf
import json
from abc import abstractmethod

from MapSkinner.settings import XML_NAMESPACES
from service.helper.enums import VersionTypes, ServiceTypes
from service.helper.epsg_api import EpsgApi
from service.helper.ogc.wms import OGCWebService
from service.helper import service_helper
from service.models import FeatureType, Keyword, ReferenceSystem, ReferenceSystemToFeatureType, KeywordToFeatureType


class OGCWebFeatureService(OGCWebService):

    def __init__(self, service_connect_url, service_version, service_type):
        super().__init__(
            service_connect_url=service_connect_url,
            service_version=service_version,
            service_type=service_type
        )
        # wfs specific attributes
        self.get_capabilities_uri = {
            "get": None,
            "post": None,
        }
        self.describe_feature_type_uri = {
            "get": None,
            "post": None,
        }
        self.get_feature_uri = {
            "get": None,
            "post": None,
        }
        self.transaction_uri = {
            "get": None,
            "post": None,
        }
        self.lock_feature_uri = {
            "get": None,
            "post": None,
        }
        self.get_feature_with_lock_uri = {
            "get": None,
            "post": None,
        }

        self.feature_type_list = {}

        XML_NAMESPACES["default"] = XML_NAMESPACES.get("wfs", "")

    class Meta:
        abstract = True

    @abstractmethod
    def create_from_capabilities(self):
        """ Fills the object with data from the capabilities document

        Returns:
             nothing
        """
        # get xml as iterable object
        xml_obj = service_helper.get_xml_dom(xml=self.service_capabilities_xml)
        # parse service metadata
        self.get_service_metadata(xml_obj=xml_obj)
        self.get_capability_metadata(xml_obj=xml_obj)
        self.get_feature_type_metadata(xml_obj=xml_obj)


    @abstractmethod
    def get_service_metadata(self, xml_obj):
        """ Implementation has to be in the wfs classes directly since they are too different from version to version.
        No common method is implementable.

        :param xml_obj:
        :return:
        """
        pass

    @abstractmethod
    def get_capability_metadata(self, xml_obj):
        """ Implementation has to be in the wfs classes directly since they are too different from version to version.
        No common method is implementable.

        :param xml_obj:
        :return:
        """
        pass

    @abstractmethod
    def get_feature_type_metadata(self, xml_obj):
        """ Implementation has to be in the wfs classes directly since they are too different from version to version.
        No common method is implementable.

        :param xml_obj:
        :return:
        """
        pass

    @abstractmethod
    def persist(self):
        """ Implementation has to be in the wfs classes directly since they are too different from version to version.
        No common method is implementable.

        :param xml_obj:
        :return:
        """
        pass

class OGCWebFeatureServiceFactory:
    """ Creates the correct OGCWebFeatureService objects

    """
    def get_ogc_wfs(self, version: VersionTypes, service_connect_url: str):
        """ Returns the correct implementation of an OGCWebFeatureService according to the given version

        Args:
            version: The version number of the service
            service_connect_url: The capabilities request uri
        Returns:
            An OGCWebFeatureService
        """
        if version is VersionTypes.V_1_0_0:
            return OGCWebFeatureService_1_0_0(service_connect_url=service_connect_url)
        if version is VersionTypes.V_1_1_0:
            return OGCWebFeatureService_1_1_0(service_connect_url=service_connect_url)
        if version is VersionTypes.V_2_0_0:
            return OGCWebFeatureService_2_0_0(service_connect_url=service_connect_url)
        if version is VersionTypes.V_2_0_2:
            return OGCWebFeatureService_2_0_2(service_connect_url=service_connect_url)


class OGCWebFeatureService_1_0_0(OGCWebFeatureService):
    def __init__(self, service_connect_url):
        super().__init__(
            service_connect_url=service_connect_url,
            service_version=VersionTypes.V_1_0_0,
            service_type=ServiceTypes.WFS,
        )

    def get_service_metadata(self, xml_obj):
        """ Parse the wfs <Service> metadata into the self object

        Args:
            xml_obj: A minidom object which holds the xml content
        Returns:
             Nothing
        """
        service_node = xml_obj.getElementsByTagName("Service")
        # TITLE
        title_node = service_helper.get_node_from_node_list(service_node, "Title")
        self.service_identification_title = service_helper.get_text_from_node(title_node)
        del title_node

        # ABSTRACT
        abstract_node = service_helper.get_node_from_node_list(service_node, "Abstract")
        self.service_identification_abstract = service_helper.get_text_from_node(abstract_node)
        del abstract_node

        # FEES
        fees_node = service_helper.get_node_from_node_list(service_node, "Fees")
        self.service_identification_fees = service_helper.get_text_from_node(fees_node)
        del fees_node

        # ACCESS CONSTRAINTS
        ac_node = service_helper.get_node_from_node_list(service_node, "AccessConstraints")
        self.service_identification_accessconstraints = service_helper.get_text_from_node(ac_node)
        del ac_node

        # KEYWORDS
        keywords_node = service_helper.get_node_from_node_list(service_node, "Keywords")
        keywords_str = service_helper.get_text_from_node(keywords_node)
        self.service_identification_keywords = service_helper.resolve_keywords_array_string(keywords_str)
        del keywords_node, keywords_str

        # ONLINE RESOURCE
        or_node = service_helper.get_node_from_node_list(service_node, "OnlineResource")
        self.service_provider_onlineresource_linkage = service_helper.get_text_from_node(or_node)
        del or_node

        del service_node

    def get_capability_metadata(self, xml_obj):
        """ Parse the wfs <Capability> metadata into the self object

        Args:
            xml_obj: A minidom object which holds the xml content
        Returns:
             Nothing
        """
        cap_node = xml_obj.getElementsByTagName("Capability")[0]
        actions = ["GetCapabilities", "DescribeFeatureType", "GetFeature", "Transaction", "LockFeature",
                   "GetFeatureWithLock"]
        get = {}
        post = {}
        for action in actions:
            node = cap_node.getElementsByTagName(action)[0]
            get[action] = service_helper.get_attributes_from_node(
                node.getElementsByTagName("Get")[0]
            ).get("onlineResource", None)
            post[action] = service_helper.get_attributes_from_node(
                node.getElementsByTagName("Post")[0]
            ).get("onlineResource", None)
        del cap_node

        self.get_capabilities_uri["get"] = get.get("GetCapabilities", None)
        self.get_capabilities_uri["post"] = post.get("GetCapabilities", None)

        self.describe_feature_type_uri["get"] = get.get("DescribeFeatureType", None)
        self.describe_feature_type_uri["post"] = post.get("DescribeFeatureType", None)

        self.get_feature_uri["get"] = get.get("GetFeature", None)
        self.get_feature_uri["post"] = post.get("GetFeature", None)

        self.transaction_uri["get"] = get.get("Transaction", None)
        self.transaction_uri["post"] = post.get("Transaction", None)

        self.lock_feature_uri["get"] = get.get("LockFeature", None)
        self.lock_feature_uri["post"] = post.get("LockFeature", None)

        self.get_feature_with_lock_uri["get"] = get.get("GetFeatureWithLock", None)
        self.get_feature_with_lock_uri["post"] = post.get("GetFeatureWithLock", None)

    def get_feature_type_metadata(self, xml_obj):
        """ Parse the wfs <Service> metadata into the self object

        Args:
            xml_obj: A minidom object which holds the xml content
        Returns:
             Nothing
        """
        feat_nodes = xml_obj.getElementsByTagName("FeatureType")
        for node in feat_nodes:
            feature_type = FeatureType()
            feature_type.name = service_helper.get_text_from_node(node.getElementsByTagName("Name")[0])
            feature_type.title = service_helper.get_text_from_node(node.getElementsByTagName("Title")[0])
            feature_type.abstract = service_helper.get_text_from_node(node.getElementsByTagName("Abstract")[0])
            keywords = service_helper.resolve_keywords_array_string(
                service_helper.get_text_from_node(
                    node.getElementsByTagName("Keywords")[0]
                )
            )
            # keywords
            # append only the ...ToFeatureType objects, since the keywords will be created automatically
            kw_list = []
            for keyword in keywords:
                kw = Keyword.objects.get_or_create(keyword=keyword)[0]
                kw_to_feature_type = KeywordToFeatureType()
                kw_to_feature_type.keyword = kw
                kw_to_feature_type.feature_type = feature_type
                kw_list.append(kw_to_feature_type)

            # lat lon bounding box
            bbox = service_helper.get_attributes_from_node(service_helper.find_node_recursive([node], "LatLongBoundingBox"))
            bbox = json.dumps(bbox)
            feature_type.bbox_lat_lon = bbox

            # reference systems
            # append only the ...ToFeatureType objects, since the reference systems will be created automatically
            srs_list = node.getElementsByTagName("SRS")
            srs_model_list = []
            epsg_api = EpsgApi()
            for srs in srs_list:
                srs_val = service_helper.get_text_from_node(srs)
                id = epsg_api.get_real_identifier(srs_val)
                prefix = srs[:len(srs_val)-len(str(id))]
                srs_model = ReferenceSystem.objects.get_or_create(code=id, prefix=prefix)[0]
                srs_to_feature_type = ReferenceSystemToFeatureType()
                srs_to_feature_type.feature_type = feature_type
                srs_to_feature_type.reference_system = srs_model
                srs_model_list.append(srs_to_feature_type)

            # put the feature types objects with keywords and reference systems into the dict for the persisting process
            # will happen later
            self.feature_type_list[feature_type.name] = {
                "feature_type": feature_type,
                "keyword_list": kw_list,
                "srs_list": srs_model_list,
            }

    def persist(self):
        # ToDo: Implement this!
        pass


class OGCWebFeatureService_1_1_0(OGCWebFeatureService):
    def __init__(self, service_connect_url):
        super().__init__(
            service_connect_url=service_connect_url,
            service_version=VersionTypes.V_1_1_0,
            service_type=ServiceTypes.WFS,
        )
        self.get_gml_object_uri = {
            "get": None,
            "post": None,
        }

    def get_service_metadata(self, xml_obj):
        """ Parse the wfs <Service> metadata into the self object

        PLEASE NOTICE:
        In here we do not use minidom parsing. Yes, this function takes the xml_obj dom object as a parameter
        but the xml xpath parsable object will be retrieved internal. So there is no usage of xml_obj in here.
        This will be fixed one day.

        Args:
            xml_obj: A minidom object which holds the xml content
        Returns:
             Nothing
        """
        xml_xpath = service_helper.parse_xml(self.service_capabilities_xml)
        self.service_identification_title = service_helper.try_get_text_from_xml_element(xml_elem=xml_xpath, elem="//ows:ServiceIdentification/ows:Title")
        self.service_identification_abstract = service_helper.try_get_text_from_xml_element(xml_elem=xml_xpath, elem="//ows:ServiceIdentification/ows:Abstract")
        self.service_identification_fees = service_helper.try_get_text_from_xml_element(xml_elem=xml_xpath, elem="//ows:ServiceIdentification/ows:Fees")
        self.service_identification_accessconstraints = service_helper.try_get_text_from_xml_element(xml_elem=xml_xpath, elem="//ows:ServiceIdentification/ows:AccessConstraints")
        keywords = service_helper.try_get_element_from_xml(xml_elem=xml_xpath, elem="//ows:ServiceIdentification/ows:Keywords/ows:Keyword")
        kw = []
        for keyword in keywords:
            try:
                kw.append(keyword.text)
            except AttributeError:
                pass
        self.service_identification_keywords = kw

        self.service_provider_providername = service_helper.try_get_text_from_xml_element(xml_elem=xml_xpath, elem="//ows:ProviderName")
        self.service_provider_url = service_helper.try_get_attribute_from_xml_element(xml_elem=xml_xpath, attribute="{http://www.w3.org/1999/xlink}href", elem="//ows:ProviderSite")
        self.service_provider_responsibleparty_individualname = service_helper.try_get_text_from_xml_element(xml_elem=xml_xpath, elem="//ows:IndividualName")
        self.service_provider_responsibleparty_positionname = service_helper.try_get_text_from_xml_element(xml_elem=xml_xpath, elem="//ows:PositionName")
        self.service_provider_telephone_voice = service_helper.try_get_text_from_xml_element(xml_elem=xml_xpath, elem="//ows:Voice")
        self.service_provider_telephone_facsimile = service_helper.try_get_text_from_xml_element(xml_elem=xml_xpath, elem="//ows:Facsimile")
        self.service_provider_address = service_helper.try_get_text_from_xml_element(xml_elem=xml_xpath, elem="//ows:DeliveryPoint")
        self.service_provider_address_city = service_helper.try_get_text_from_xml_element(xml_elem=xml_xpath, elem="//ows:City")
        self.service_provider_address_state_or_province = service_helper.try_get_text_from_xml_element(xml_elem=xml_xpath, elem="//ows:AdministrativeArea")
        self.service_provider_address_postalcode = service_helper.try_get_text_from_xml_element(xml_elem=xml_xpath, elem="//ows:PostalCode")
        self.service_provider_address_country = service_helper.try_get_text_from_xml_element(xml_elem=xml_xpath, elem="//ows:Country")
        self.service_provider_address_electronicmailaddress = service_helper.try_get_text_from_xml_element(xml_elem=xml_xpath, elem="//ows:ElectronicMailAddress")
        self.service_provider_onlineresource_linkage = service_helper.try_get_attribute_from_xml_element(xml_elem=xml_xpath, elem="//ows:OnlineResource", attribute="{http://www.w3.org/1999/xlink}href")
        self.service_provider_contact_hoursofservice = service_helper.try_get_text_from_xml_element(xml_elem=xml_xpath, elem="//ows:HoursOfService")
        self.service_provider_contact_contactinstructions = service_helper.try_get_text_from_xml_element(xml_elem=xml_xpath, elem="//ows:ContactInstructions")

    def get_capability_metadata(self, xml_obj):
        """ Parse the wfs <Capability> metadata into the self object

        PLEASE NOTICE:
        In here we do not use minidom parsing. Yes, this function takes the xml_obj dom object as a parameter
        but the xml xpath parsable object will be retrieved internal. So there is no usage of xml_obj in here.
        This will be fixed one day.

        Args:
            xml_obj: A minidom object which holds the xml content
        Returns:
             Nothing
        """
        xml_xpath = service_helper.parse_xml(self.service_capabilities_xml)
        operation_metadata = service_helper.try_get_element_from_xml("//ows:OperationsMetadata", xml_xpath)[0]
        actions = ["GetCapabilities", "DescribeFeatureType", "GetFeature", "Transaction", "LockFeature",
                   "GetFeatureWithLock", "GetGMLObject"]
        get = {}
        post = {}
        for action in actions:
            xpath_str = './ows:Operation[@name="' + action + '"]'
            operation = service_helper.try_get_single_element_from_xml(xml_elem=operation_metadata, elem=xpath_str)
            if operation is None:
                continue
            _get = service_helper.try_get_attribute_from_xml_element(
                xml_elem=operation,
                attribute="{http://www.w3.org/1999/xlink}href",
                elem=".//ows:Get"
            )
            _post = service_helper.try_get_attribute_from_xml_element(
                xml_elem=operation,
                attribute="{http://www.w3.org/1999/xlink}href",
                elem=".//ows:Post"
            )
            get[action] = _get
            post[action] = _post
        self.get_capabilities_uri["get"] = get.get("GetCapabilities", None)
        self.get_capabilities_uri["post"] = post.get("GetCapabilities", None)

        self.describe_feature_type_uri["get"] = get.get("DescribeFeatureType", None)
        self.describe_feature_type_uri["post"] = post.get("DescribeFeatureType", None)

        self.get_feature_uri["get"] = get.get("GetFeature", None)
        self.get_feature_uri["post"] = post.get("GetFeature", None)

        self.transaction_uri["get"] = get.get("Transaction", None)
        self.transaction_uri["post"] = post.get("Transaction", None)

        self.lock_feature_uri["get"] = get.get("LockFeature", None)
        self.lock_feature_uri["post"] = post.get("LockFeature", None)

        self.get_feature_with_lock_uri["get"] = get.get("GetFeatureWithLock", None)
        self.get_feature_with_lock_uri["post"] = post.get("GetFeatureWithLock", None)

        self.get_gml_object_uri["get"] = get.get("GetGMLObject", None)
        self.get_gml_object_uri["post"] = post.get("GetGMLObject", None)

    def get_feature_type_metadata(self, xml_obj):
        xml_xpath = service_helper.parse_xml(self.service_capabilities_xml)
        feature_type_list = service_helper.try_get_element_from_xml(elem="//wfs:FeatureType", xml_elem=xml_xpath)

        # Feature types
        for feature_type in feature_type_list:
            f_t = FeatureType()
            f_t.title = service_helper.try_get_text_from_xml_element(xml_elem=feature_type, elem="//wfs:Title")
            f_t.name = service_helper.try_get_text_from_xml_element(xml_elem=feature_type, elem="//wfs:Name")
            f_t.abstract = service_helper.try_get_text_from_xml_element(xml_elem=feature_type, elem="//wfs:Abstract")

            # Feature type keywords
            keywords = service_helper.try_get_element_from_xml(xml_elem=feature_type, elem="//wfs:Keyword")
            keyword_list = []
            for keyword in keywords:
                kw = Keyword.objects.get_or_create(name=keyword.text)
                kw_to_ft = KeywordToFeatureType()
                kw_to_ft.keyword = kw
                kw_to_ft.feature_type = f_t
                keyword_list.append(kw_to_ft)

            # SRS
            srs_default = service_helper.try_get_element_from_xml(xml_elem=feature_type, elem="//wfs:")



class OGCWebFeatureService_2_0_0(OGCWebFeatureService):
    def __init__(self, service_connect_url):
        super().__init__(
            service_connect_url=service_connect_url,
            service_version=VersionTypes.V_2_0_0,
            service_type=ServiceTypes.WFS,
        )


class OGCWebFeatureService_2_0_2(OGCWebFeatureService):
    def __init__(self, service_connect_url):
        super().__init__(
            service_connect_url=service_connect_url,
            service_version=VersionTypes.V_2_0_2,
            service_type=ServiceTypes.WFS,
        )