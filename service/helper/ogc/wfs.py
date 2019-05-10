#common classes for handling of WFS (OGC WebFeatureServices)
#http://www.opengeospatial.org/standards/wf
import json
import threading
import uuid
from abc import abstractmethod

from django.db import transaction

from MapSkinner.settings import XML_NAMESPACES
from MapSkinner.utils import execute_threads
from service.helper.enums import VersionTypes, ServiceTypes
from service.helper.epsg_api import EpsgApi
from service.helper.ogc.wms import OGCWebService
from service.helper import service_helper
from service.models import FeatureType, Keyword, ReferenceSystem, Service, Metadata, ServiceType
from structure.models import Organization, Group, User


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
        # wms 1.1.0
        self.get_gml_object_uri = {
            "get": None,
            "post": None,
        }
        # wms 2.0.0
        self.list_stored_queries = {
            "get": None,
            "post": None,
        }

        self.feature_type_list = {}

        # for wfs we need to overwrite the default namespace with 'wfs'
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
        xml_obj = service_helper.parse_xml(xml=self.service_capabilities_xml)
        # parse service metadata
        thread_list = [
            threading.Thread(target=self.get_service_metadata, args=(xml_obj,)),
            threading.Thread(target=self.get_capability_metadata, args=(xml_obj,)),
            threading.Thread(target=self.get_feature_type_metadata, args=(xml_obj,))
        ]
        execute_threads(thread_list)


    @abstractmethod
    def get_service_metadata(self, xml_obj):
        """ Parse the wfs <Service> metadata into the self object

        Args:
            xml_obj: A minidom object which holds the xml content
        Returns:
             Nothing
        """
        self.service_identification_title = service_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:ServiceIdentification/ows:Title")
        self.service_identification_abstract = service_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:ServiceIdentification/ows:Abstract")
        self.service_identification_fees = service_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:ServiceIdentification/ows:Fees")
        self.service_identification_accessconstraints = service_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:ServiceIdentification/ows:AccessConstraints")
        keywords = service_helper.try_get_element_from_xml(xml_elem=xml_obj, elem="//ows:ServiceIdentification/ows:Keywords/ows:Keyword")
        kw = []
        for keyword in keywords:
            try:
                kw.append(keyword.text)
            except AttributeError:
                pass
        self.service_identification_keywords = kw

        self.service_provider_providername = service_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:ProviderName")
        self.service_provider_url = service_helper.try_get_attribute_from_xml_element(xml_elem=xml_obj, attribute="{http://www.w3.org/1999/xlink}href", elem="//ows:ProviderSite")
        self.service_provider_responsibleparty_individualname = service_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:IndividualName")
        self.service_provider_responsibleparty_positionname = service_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:PositionName")
        self.service_provider_telephone_voice = service_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:Voice")
        self.service_provider_telephone_facsimile = service_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:Facsimile")
        self.service_provider_address = service_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:DeliveryPoint")
        self.service_provider_address_city = service_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:City")
        self.service_provider_address_state_or_province = service_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:AdministrativeArea")
        self.service_provider_address_postalcode = service_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:PostalCode")
        self.service_provider_address_country = service_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:Country")
        self.service_provider_address_electronicmailaddress = service_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:ElectronicMailAddress")
        self.service_provider_onlineresource_linkage = service_helper.try_get_attribute_from_xml_element(xml_elem=xml_obj, elem="//ows:OnlineResource", attribute="{http://www.w3.org/1999/xlink}href")
        self.service_provider_contact_hoursofservice = service_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:HoursOfService")
        self.service_provider_contact_contactinstructions = service_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:ContactInstructions")

    @abstractmethod
    def get_capability_metadata(self, xml_obj):
        """ Parse the wfs <Capability> metadata into the self object

        Args:
            xml_obj: A minidom object which holds the xml content
        Returns:
             Nothing
        """
        operation_metadata = service_helper.try_get_element_from_xml("//ows:OperationsMetadata", xml_obj)[0]
        actions = ["GetCapabilities", "DescribeFeatureType", "GetFeature", "Transaction", "LockFeature",
                   "GetFeatureWithLock", "GetGMLObject", "ListStoredQueries"]
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

        self.get_gml_object_uri["get"] = get.get("ListStoredQueries", None)
        self.get_gml_object_uri["post"] = post.get("ListStoredQueries", None)

    @abstractmethod
    def get_feature_type_metadata(self, xml_obj):
        """ Parse the wfs <FeatureTypeList> metadata into the self object

        This abstract implementation follows the wfs specification for version 1.1.0

        Args:
            xml_obj: A minidom object which holds the xml content
        Returns:
             Nothing
        """
        feature_type_list = service_helper.try_get_element_from_xml(elem="//wfs:FeatureType", xml_elem=xml_obj)
        epsg_api = EpsgApi()

        # Feature types
        for feature_type in feature_type_list:
            f_t = FeatureType()
            f_t.title = service_helper.try_get_text_from_xml_element(xml_elem=feature_type, elem="//wfs:Title")
            f_t.name = service_helper.try_get_text_from_xml_element(xml_elem=feature_type, elem="//wfs:Name")
            f_t.abstract = service_helper.try_get_text_from_xml_element(xml_elem=feature_type, elem="//wfs:Abstract")

            # Feature type keywords
            keywords = service_helper.try_get_element_from_xml(xml_elem=feature_type, elem="//ows:Keyword")
            keyword_list = []
            for keyword in keywords:
                kw = service_helper.try_get_text_from_xml_element(xml_elem=keyword)
                kw = Keyword.objects.get_or_create(keyword=kw)[0]
                keyword_list.append(kw)

            # SRS
            ## default
            srs = service_helper.try_get_text_from_xml_element(xml_elem=feature_type, elem="//wfs:DefaultSRS")
            if srs is not None:
                parts = epsg_api.get_subelements(srs)
                srs_default = ReferenceSystem.objects.get_or_create(code=parts.get("code"), prefix=parts.get("prefix"))[0]
                parts = epsg_api.get_subelements(srs)
                f_t.default_srs = srs_default

            ## additional
            srs = service_helper.try_get_element_from_xml(xml_elem=feature_type, elem="//wfs:OtherSRS")
            srs_list = []
            for sys in srs:
                parts = epsg_api.get_subelements(sys.text)
                srs_other = ReferenceSystem.objects.get_or_create(code=parts.get("code"), prefix=parts.get("prefix"))[0]
                srs_list.append(srs_other)

            # Latlon bounding box
            tmp = service_helper.try_get_text_from_xml_element(elem="//ows:LowerCorner", xml_elem=feature_type)
            min_x = tmp.split(" ")[0]
            min_y = tmp.split(" ")[1]
            tmp = service_helper.try_get_text_from_xml_element(elem="//ows:UpperCorner", xml_elem=feature_type)
            max_x = tmp.split(" ")[0]
            max_y = tmp.split(" ")[1]
            tmp = {
                "minx": min_x,
                "miny": min_y,
                "maxx": max_x,
                "maxy": max_y,
            }
            f_t.bbox_lat_lon = json.dumps(tmp)

            self.feature_type_list[f_t.name] = {
                "feature_type": f_t,
                "keyword_list": keyword_list,
                "srs_list": srs_list,
            }

    @abstractmethod
    @transaction.atomic
    def persist(self, user: User):
        orga_published_for = user.secondary_organization
        orga_publisher = user.primary_organization

        group = user.groups.all()[0] # ToDo: Find better solution for group selection than this

        # Metadata
        md = Metadata()
        md.title = self.service_identification_title
        md.uuid = uuid.uuid4()
        md.abstract = self.service_identification_abstract
        md.online_resource = self.service_provider_onlineresource_linkage
        ## contact
        contact = Organization.objects.get_or_create(
            organization_name=self.service_provider_providername,
            person_name=self.service_provider_responsibleparty_individualname,
            email=self.service_provider_address_electronicmailaddress,
            phone=self.service_provider_telephone_voice,
            city=self.service_provider_address_city,
            address=self.service_provider_address,
            postal_code=self.service_provider_address_postalcode,
            state_or_province=self.service_provider_address_state_or_province
        )[0]
        md.contact = contact
        md.authority_url = self.service_provider_url
        md.access_constraints = self.service_identification_accessconstraints
        md.created_by = group
        md.save()

        # Service
        service = Service()
        service_type = ServiceType.objects.get_or_create(
            name=self.service_type.value,
            version=self.service_version.value
        )[0]
        service.servicetype = service_type
        service.created_by = group
        service.published_for = orga_published_for
        service.published_by = orga_publisher
        service.availability = 0.0
        service.is_available = False
        service.is_root = True
        service.metadata = md
        service.save()

        # Keywords
        for kw in self.service_identification_keywords:
            keyword = Keyword.objects.get_or_create(keyword=kw)[0]
            md.keywords.add(keyword)

        # feature types
        for feature_type_key, feature_type_val in self.feature_type_list.items():
            f_t = feature_type_val.get("feature_type")
            f_t.created_by = group
            f_t.save()
            service.featuretypes.add(f_t)
            # keywords of feature types
            for kw in feature_type_val.get("keyword_list"):
                f_t.keywords.add(kw)
            # srs of feature types
            for srs in feature_type_val.get("srs_list"):
                f_t.reference_system.add(srs)

        # toDo: Implement persisting of get_feature_uri and so on



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
    """
    The wfs version 1.0.0 is slightly different than the rest. Therefore we need to overwrite the abstract
    methods and provide an individual way to parse the data.
    """
    def __init__(self, service_connect_url):
        super().__init__(
            service_connect_url=service_connect_url,
            service_version=VersionTypes.V_1_0_0,
            service_type=ServiceTypes.WFS,
        )
        XML_NAMESPACES["schemaLocation"] = "http://geodatenlb1.rlp:80/geoserver/schemas/wfs/1.0.0/WFS-capabilities.xsd"
        XML_NAMESPACES["xsi"] = "http://www.w3.org/2001/XMLSchema-instance"
        XML_NAMESPACES["lvermgeo"] = "http://www.lvermgeo.rlp.de/lvermgeo"
        XML_NAMESPACES["default"] = XML_NAMESPACES.get("wfs")

    def get_service_metadata(self, xml_obj):
        """ Parse the wfs <Service> metadata into the self object

        Args:
            xml_obj: A minidom object which holds the xml content
        Returns:
             Nothing
        """
        service_node = service_helper.try_get_single_element_from_xml("/wfs:WFS_Capabilities/wfs:Service", xml_elem=xml_obj)
        # TITLE
        title_node = service_helper.try_get_text_from_xml_element(elem="./wfs:Title", xml_elem=service_node)
        self.service_identification_title = title_node

        # ABSTRACT
        self.service_identification_abstract = service_helper.try_get_text_from_xml_element(elem="./wfs:Abstract", xml_elem=service_node)

        # FEES
        self.service_identification_fees = service_helper.try_get_text_from_xml_element(elem="./wfs:Fees", xml_elem=service_node)

        # ACCESS CONSTRAINTS
        self.service_identification_accessconstraints = service_helper.try_get_text_from_xml_element(elem="./wfs:AccessConstraints", xml_elem=service_node)

        # KEYWORDS
        keywords_str = service_helper.try_get_text_from_xml_element(elem="./wfs:Keywords", xml_elem=service_node)
        self.service_identification_keywords = service_helper.resolve_keywords_array_string(keywords_str)
        del keywords_str

        # ONLINE RESOURCE
        self.service_provider_onlineresource_linkage = service_helper.try_get_text_from_xml_element(elem="./wfs:OnlineResource", xml_elem=service_node)

        del service_node

    def get_capability_metadata(self, xml_obj):
        """ Parse the wfs <Capability> metadata into the self object

        Args:
            xml_obj: A minidom object which holds the xml content
        Returns:
             Nothing
        """
        cap_node = service_helper.try_get_single_element_from_xml("/wfs:WFS_Capabilities/wfs:Capability", xml_elem=xml_obj)
        actions = ["GetCapabilities", "DescribeFeatureType", "GetFeature", "Transaction", "LockFeature",
                   "GetFeatureWithLock"]
        get = {}
        post = {}
        for action in actions:
            node = service_helper.try_get_single_element_from_xml(".//wfs:" + action, cap_node)
            get[action] = service_helper.try_get_attribute_from_xml_element(elem=".//wfs:Get", xml_elem=node, attribute="onlineResource")
            post[action] = service_helper.try_get_attribute_from_xml_element(elem=".//wfs:Post", xml_elem=node, attribute="onlineResource")
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
        feat_nodes = service_helper.try_get_element_from_xml("/wfs:WFS_Capabilities/wfs:FeatureTypeList/wfs:FeatureType", xml_obj)
        for node in feat_nodes:
            feature_type = FeatureType()
            feature_type.name = service_helper.try_get_text_from_xml_element(elem=".//wfs:Name", xml_elem=node)
            feature_type.title = service_helper.try_get_text_from_xml_element(elem=".//wfs:Title", xml_elem=node)
            feature_type.abstract = service_helper.try_get_text_from_xml_element(elem=".//wfs:Abstract", xml_elem=node)
            keywords = service_helper.resolve_keywords_array_string(
                service_helper.try_get_text_from_xml_element(elem=".//wfs:Keywords", xml_elem=node)
            )
            # keywords
            # append only the ...ToFeatureType objects, since the keywords will be created automatically
            kw_list = []
            for keyword in keywords:
                kw = Keyword.objects.get_or_create(keyword=keyword)[0]
                kw_list.append(kw)

            # lat lon bounding box
            bbox = {
                "minx": service_helper.try_get_attribute_from_xml_element(elem="./wfs:LatLongBoundingBox", xml_elem=node, attribute="minx"),
                "miny": service_helper.try_get_attribute_from_xml_element(elem="./wfs:LatLongBoundingBox", xml_elem=node, attribute="miny"),
                "maxx": service_helper.try_get_attribute_from_xml_element(elem="./wfs:LatLongBoundingBox", xml_elem=node, attribute="maxx"),
                "maxy": service_helper.try_get_attribute_from_xml_element(elem="./wfs:LatLongBoundingBox", xml_elem=node, attribute="maxy"),
            }
            feature_type.bbox_lat_lon = bbox

            # reference systems
            # append only the ...ToFeatureType objects, since the reference systems will be created automatically
            srs_list = service_helper.try_get_element_from_xml("./wfs:SRS", node)
            srs_model_list = []
            epsg_api = EpsgApi()
            for srs in srs_list:
                srs_val = service_helper.try_get_text_from_xml_element(srs)
                parts = epsg_api.get_subelements(srs_val)
                srs_model = ReferenceSystem.objects.get_or_create(code=parts.get("code"), prefix=parts.get("prefix"))[0]
                srs_model_list.append(srs_model)

            # put the feature types objects with keywords and reference systems into the dict for the persisting process
            # will happen later
            self.feature_type_list[feature_type.name] = {
                "feature_type": feature_type,
                "keyword_list": kw_list,
                "srs_list": srs_model_list,
            }


class OGCWebFeatureService_1_1_0(OGCWebFeatureService):
    """
    Uses base implementation from OGCWebFeatureService class
    """
    def __init__(self, service_connect_url):
        super().__init__(
            service_connect_url=service_connect_url,
            service_version=VersionTypes.V_1_1_0,
            service_type=ServiceTypes.WFS,
        )


class OGCWebFeatureService_2_0_0(OGCWebFeatureService):
    """
    Uses base implementation from OGCWebFeatureService class
    """
    def __init__(self, service_connect_url):
        super().__init__(
            service_connect_url=service_connect_url,
            service_version=VersionTypes.V_2_0_0,
            service_type=ServiceTypes.WFS,
        )
        XML_NAMESPACES["wfs"] = "http://www.opengis.net/wfs/2.0"
        XML_NAMESPACES["ows"] = "http://www.opengis.net/ows/1.1"
        XML_NAMESPACES["fes"] = "http://www.opengis.net/fes/2.0"
        XML_NAMESPACES["default"] = XML_NAMESPACES["wfs"]


class OGCWebFeatureService_2_0_2(OGCWebFeatureService):
    """
    Uses base implementation from OGCWebFeatureService class
    """
    def __init__(self, service_connect_url):
        super().__init__(
            service_connect_url=service_connect_url,
            service_version=VersionTypes.V_2_0_2,
            service_type=ServiceTypes.WFS,
        )

