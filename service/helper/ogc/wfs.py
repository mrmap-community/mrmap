#common classes for handling of WFS (OGC WebFeatureServices)
#http://www.opengeospatial.org/standards/wf
import json
import threading
import uuid
from abc import abstractmethod
from collections import OrderedDict

import time

from django.contrib.gis.geos import Polygon
from django.db import transaction

from MapSkinner.settings import XML_NAMESPACES, GENERIC_ERROR_MSG, EXEC_TIME_PRINT
from MapSkinner.utils import execute_threads
from service.config import ALLOWED_SRS
from service.helper.enums import VersionTypes, ServiceTypes
from service.helper.epsg_api import EpsgApi
from service.helper.ogc.wms import OGCWebService
from service.helper import service_helper
from service.models import FeatureType, Keyword, ReferenceSystem, Service, Metadata, ServiceType, MimeType, Namespace, \
    FeatureTypeElement
from structure.models import Organization, User


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
        ]
        execute_threads(thread_list)

        start_time = time.time()
        self.get_service_iso_metadata(xml_obj)
        print(EXEC_TIME_PRINT % ("service iso metadata", time.time() - start_time))

        start_time = time.time()
        self.get_feature_type_metadata(xml_obj)
        print(EXEC_TIME_PRINT % ("featuretype metadata", time.time() - start_time))
        # always execute version specific tasks AFTER multithreading
        # Otherwise we might face race conditions which lead to loss of data!
        self.get_version_specific_metadata(xml_obj)

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
            text = keyword.text
            if text is None:
                continue
            try:
                kw.append(text)
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
        if self.service_provider_onlineresource_linkage is None or self.service_provider_onlineresource_linkage == "":
            # There are metadatas where no online resource link is given. We need to generate it manually therefore...
            self.service_provider_onlineresource_linkage = service_helper.split_service_uri(self.service_connect_url).get("base_uri") + "?"
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
        operation_metadata = service_helper.try_get_element_from_xml("//ows:OperationsMetadata", xml_obj)
        if len(operation_metadata) > 0:
            operation_metadata = operation_metadata[0]
        else:
            return
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
    def _get_featuretype_elements_namespaces(self, feature_type, service_type_version:str):
        """ Get the elements and their namespaces of a feature type object

        Args:
            feature_type: The feature type xml object
            service_type_version(str): The service type version as string
        Returns:
            dict: Containing "element_list" and "ns_list"
        """
        element_list = []
        ns_list = []
        if self.describe_feature_type_uri.get("get") is not None:
            XML_NAMESPACES["default"] = XML_NAMESPACES["xsd"]
            descr_feat_root = service_helper.get_feature_type_elements_xml(title=feature_type.name,
                                                                    service_type="wfs",
                                                                    service_type_version=service_type_version,
                                                                    uri=self.describe_feature_type_uri.get("get"))
            if descr_feat_root is not None:
                # Feature type elements
                elements = service_helper.try_get_element_from_xml(elem="//xsd:element", xml_elem=descr_feat_root)
                for element in elements:
                    f_t_element = FeatureTypeElement.objects.get_or_create(
                        name=service_helper.try_get_attribute_from_xml_element(xml_elem=element, attribute="name"),
                        type=service_helper.try_get_attribute_from_xml_element(xml_elem=element, attribute="type"),
                    )[0]
                    element_list.append(f_t_element)

                # Feature type namespaces
                namespaces = service_helper.try_get_element_from_xml(elem="./namespace::*", xml_elem=descr_feat_root)
                for namespace in namespaces:
                    if namespace[0] is None:
                        continue
                    ns = Namespace.objects.get_or_create(
                        name=namespace[0],
                        uri=namespace[1],
                    )[0]
                    if ns not in ns_list:
                        ns_list.append(ns)
        return {
            "element_list": element_list,
            "ns_list": ns_list,
        }


    @transaction.atomic
    def _get_feature_type_metadata(self, feature_type, epsg_api, service_type_version:str):
        """ Get featuretype metadata of a single featuretype

        Args:
            feature_type: The featuretype xml object
            epsg_api: The epsg api object
            service_type_version(str): The service type version as string
        Returns:
            feature_type_list(dict): A dict containing all different metadatas for this featuretype and it's children
        """
        f_t = FeatureType()
        f_t.uuid = uuid.uuid4()
        f_t.title = service_helper.try_get_text_from_xml_element(xml_elem=feature_type, elem=".//wfs:Title")
        f_t.name = service_helper.try_get_text_from_xml_element(xml_elem=feature_type, elem=".//wfs:Name")
        f_t.abstract = service_helper.try_get_text_from_xml_element(xml_elem=feature_type, elem=".//wfs:Abstract")
        # Feature type keywords
        keywords = service_helper.try_get_element_from_xml(xml_elem=feature_type, elem=".//ows:Keyword")
        keyword_list = []
        for keyword in keywords:
            kw = service_helper.try_get_text_from_xml_element(xml_elem=keyword)
            if kw is None:
                continue
            kw = Keyword.objects.get_or_create(keyword=kw)[0]
            keyword_list.append(kw)
        # SRS
        ## default
        srs = service_helper.try_get_text_from_xml_element(xml_elem=feature_type, elem=".//wfs:DefaultSRS")
        if srs is not None:
            parts = epsg_api.get_subelements(srs)
            srs_default = ReferenceSystem.objects.get_or_create(code=parts.get("code"), prefix=parts.get("prefix"))[0]
            f_t.default_srs = srs_default
        ## additional
        srs = service_helper.try_get_element_from_xml(xml_elem=feature_type, elem=".//wfs:OtherSRS")
        srs_list = []
        for sys in srs:
            parts = epsg_api.get_subelements(sys.text)
            # check if this srs is allowed for us. If not, skip it!
            if parts.get("code") not in ALLOWED_SRS:
                continue
            srs_other = ReferenceSystem.objects.get_or_create(code=parts.get("code"), prefix=parts.get("prefix"))[0]
            srs_list.append(srs_other)
        # Latlon bounding box
        tmp = service_helper.try_get_text_from_xml_element(elem=".//ows:LowerCorner", xml_elem=feature_type)
        min_x = tmp.split(" ")[0]
        min_y = tmp.split(" ")[1]
        tmp = service_helper.try_get_text_from_xml_element(elem=".//ows:UpperCorner", xml_elem=feature_type)
        max_x = tmp.split(" ")[0]
        max_y = tmp.split(" ")[1]
        tmp = OrderedDict()
        bbox = Polygon(
            (
                (float(min_x), float(min_y)),
                (float(min_x), float(max_y)),
                (float(max_x), float(max_y)),
                (float(max_x), float(min_y)),
                (float(min_x), float(min_y)),
            )
        )
        f_t.bbox_lat_lon = bbox
        # Output formats
        formats = service_helper.try_get_element_from_xml(xml_elem=feature_type, elem=".//wfs:Format")
        format_list = []
        for _format in formats:
            m_t = MimeType.objects.get_or_create(
                mime_type=service_helper.try_get_text_from_xml_element(
                    xml_elem=_format
                )
            )[0]
            format_list.append(m_t)

        # Feature type elements
        # Feature type namespaces
        elements_namespaces = self._get_featuretype_elements_namespaces(f_t, service_type_version)
        self.feature_type_list[f_t.name] = {
            "feature_type": f_t,
            "keyword_list": keyword_list,
            "srs_list": srs_list,
            "format_list": format_list,
            "element_list": elements_namespaces.get("element_list", []),
            "ns_list": elements_namespaces.get("ns_list", []),
        }

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
        service_type_version = service_helper.try_get_attribute_from_xml_element(xml_elem=xml_obj,
                                                                                 attribute="version",
                                                                                 elem="//wfs:WFS_Capabilities")
        epsg_api = EpsgApi()
        # Feature types
        for feature_type in feature_type_list:
            self._get_feature_type_metadata(feature_type, epsg_api, service_type_version)


    @abstractmethod
    @transaction.atomic
    def create_service_model_instance(self, user: User, register_group, register_for_organization):
        """ Map all data from the WebFeatureService classes to their database models

        Args:
            user (User): The user which performs the action
            register_group (Group): The group which is used to register this service
            register_for_organization (Organization): The organization for which this service is being registered
        Returns:
             service (Service): Service instance, contains all information, ready for persisting!
        """

        orga_published_for = register_for_organization
        orga_publisher = user.organization

        group = register_group
        # Metadata
        md = Metadata()
        md.title = self.service_identification_title
        if self.service_file_identifier is None:
            self.service_file_identifier = uuid.uuid4()
        md.uuid = self.service_file_identifier
        md.abstract = self.service_identification_abstract
        md.online_resource = self.service_provider_onlineresource_linkage
        ## contact
        contact = Organization.objects.get_or_create(
            organization_name=self.service_provider_providername,
            person_name=self.service_provider_responsibleparty_individualname,
            email=self.service_provider_address_electronicmailaddress,
            phone=self.service_provider_telephone_voice,
            facsimile=self.service_provider_telephone_facsimile,
            city=self.service_provider_address_city,
            address=self.service_provider_address,
            postal_code=self.service_provider_address_postalcode,
            state_or_province=self.service_provider_address_state_or_province,
            country=self.service_provider_address_country,
        )[0]
        md.contact = contact
        md.authority_url = self.service_provider_url
        md.access_constraints = self.service_identification_accessconstraints
        md.created_by = group
        md.original_uri = self.service_connect_url
        md.bounding_geometry = self.service_bounding_box
        #md.save()

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
        #service.save()

        # Keywords
        for kw in self.service_identification_keywords:
            keyword = Keyword.objects.get_or_create(keyword=kw)[0]
            md.keywords_list.append(keyword)
            #md.keywords.add(keyword)

        # feature types
        for feature_type_key, feature_type_val in self.feature_type_list.items():
            f_t = feature_type_val.get("feature_type")
            f_t.created_by = group
            f_t.service = service
            # f_t.save()

            # keywords of feature types
            for kw in feature_type_val.get("keyword_list"):
                f_t.keywords_list.append(kw)
                # f_t.keywords.add(kw)

            # srs of feature types
            for srs in feature_type_val.get("srs_list"):
                f_t.additional_srs_list.append(srs)
                # f_t.additional_srs.add(srs)

            # formats
            for _format in feature_type_val.get("format_list"):
                f_t.formats_list.append(_format)
                #_format.save()
                # f_t.formats.add(_format)

            # elements
            for _element in feature_type_val.get("element_list"):
                f_t.elements_list.append(_element)
                # f_t.elements.add(_element)

            # namespaces
            for ns in feature_type_val.get("ns_list"):
                f_t.namespaces_list.append(ns)
                # f_t.namespaces.add(ns)

            # add feature type to list of related feature types
            service.feature_type_list.append(f_t)

        return service

    @transaction.atomic
    def persist_service_model(self, service):
        """ Persist the service model object

        Returns:
             Nothing
        """
        # save metadata
        md = service.metadata
        md.save()
        service.metadata = md
        # save parent service
        service.save()

        # Keywords
        for kw in service.metadata.keywords_list:
            service.metadata.keywords.add(kw)

        # feature types
        for f_t in service.feature_type_list:
            f_t.service = service
            f_t.save()

            # keywords of feature types
            for kw in f_t.keywords_list:
                f_t.keywords.add(kw)

            # srs of feature types
            for srs in f_t.additional_srs_list:
                f_t.additional_srs.add(srs)

            # formats
            for _format in f_t.formats_list:
                _format.save()
                f_t.formats.add(_format)

            # elements
            for _element in f_t.elements_list:
                f_t.elements.add(_element)

            # namespaces
            for ns in f_t.namespaces_list:
                f_t.namespaces.add(ns)


class OGCWebFeatureServiceFactory:
    """ Creates the correct OGCWebFeatureService objects

    """
    def get_ogc_wfs(self, version: VersionTypes, service_connect_url=None):
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
        service_node = service_helper.try_get_single_element_from_xml(elem="/wfs:WFS_Capabilities/wfs:Service", xml_elem=xml_obj)
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
        service_type_version = service_helper.try_get_attribute_from_xml_element(xml_elem=xml_obj,
                                                                                 attribute="version",
                                                                                 elem="//wfs:WFS_Capabilities")
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
                # check if this srs is allowed for us. If not, skip it!
                if parts.get("code") not in ALLOWED_SRS:
                    continue
                srs_model = ReferenceSystem.objects.get_or_create(code=parts.get("code"), prefix=parts.get("prefix"))[0]
                srs_model_list.append(srs_model)

            # Feature type elements
            # Feature type namespaces
            elements_namespaces = self._get_featuretype_elements_namespaces(feature_type, service_type_version)

            # put the feature types objects with keywords and reference systems into the dict for the persisting process
            # will happen later
            self.feature_type_list[feature_type.name] = {
                "feature_type": feature_type,
                "keyword_list": kw_list,
                "srs_list": srs_model_list,
                "format_list": [],
                "element_list": elements_namespaces["element_list"],
                "ns_list": elements_namespaces["ns_list"],
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
        XML_NAMESPACES["wfs"] = "http://www.opengis.net/wfs"
        XML_NAMESPACES["ows"] = "http://www.opengis.net/ows"
        XML_NAMESPACES["fes"] = "http://www.opengis.net/fes"
        XML_NAMESPACES["default"] = XML_NAMESPACES["wfs"]


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

    def get_version_specific_metadata(self, xml_obj):
        epsg_api = EpsgApi()
        # featuretype keywords are different than in older versions
        feature_type_list = service_helper.try_get_element_from_xml(elem="//wfs:FeatureType", xml_elem=xml_obj)
        for feature_type in feature_type_list:
            name = service_helper.try_get_text_from_xml_element(xml_elem=feature_type, elem=".//wfs:Name")
            try:
                f_t = self.feature_type_list.get(name).get("feature_type")
            except AttributeError:
                # if this happens the metadata is broken or not reachable due to bad configuration
                raise BaseException(GENERIC_ERROR_MSG)
            # Feature type keywords
            keywords = service_helper.try_get_element_from_xml(xml_elem=feature_type, elem=".//ows:Keyword")
            keyword_list = []
            for keyword in keywords:
                kw = service_helper.try_get_text_from_xml_element(xml_elem=keyword)
                kw = Keyword.objects.get_or_create(keyword=kw)[0]
                keyword_list.append(kw)
            self.feature_type_list[name]["keyword_list"] = keyword_list

            # srs are now called crs -> do it again!
            # CRS
            ## default
            crs = service_helper.try_get_text_from_xml_element(xml_elem=feature_type, elem=".//wfs:DefaultCRS")
            if crs is not None:
                parts = epsg_api.get_subelements(crs)
                # check if this srs is allowed for us. If not, skip it!
                if parts.get("code") not in ALLOWED_SRS:
                    continue
                crs_default = ReferenceSystem.objects.get_or_create(code=parts.get("code"), prefix=parts.get("prefix"))[0]
                f_t.default_srs = crs_default
            ## additional
            crs = service_helper.try_get_element_from_xml(xml_elem=feature_type, elem=".//wfs:OtherCRS")
            crs_list = []
            for sys in crs:
                parts = epsg_api.get_subelements(sys.text)
                # check if this srs is allowed for us. If not, skip it!
                if parts.get("code") not in ALLOWED_SRS:
                    continue
                srs_other = ReferenceSystem.objects.get_or_create(code=parts.get("code"), prefix=parts.get("prefix"))[0]
                crs_list.append(srs_other)
            self.feature_type_list[name]["srs_list"] = crs_list


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

