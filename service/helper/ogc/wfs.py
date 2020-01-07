import threading
import uuid
from abc import abstractmethod
from collections import OrderedDict

import time

from celery import Task
from django.contrib.gis.geos import Polygon
from django.db import transaction
from lxml.etree import _Element

from service.settings import MD_TYPE_FEATURETYPE, MD_TYPE_SERVICE, MD_RELATION_TYPE_VISUALIZES
from MapSkinner.settings import XML_NAMESPACES, EXEC_TIME_PRINT, \
    MULTITHREADING_THRESHOLD, PROGRESS_STATUS_AFTER_PARSING, GENERIC_NAMESPACE_TEMPLATE
from MapSkinner.messages import SERVICE_GENERIC_ERROR
from MapSkinner.utils import execute_threads
from service.helper.enums import VersionEnum, ServiceEnum
from service.helper.epsg_api import EpsgApi
from service.helper.iso.iso_metadata import ISOMetadata
from service.helper.ogc.wms import OGCWebService
from service.helper import service_helper, xml_helper, task_helper
from service.models import FeatureType, Keyword, ReferenceSystem, Service, Metadata, ServiceType, MimeType, Namespace, \
    FeatureTypeElement, MetadataRelation, MetadataOrigin, MetadataType, RequestOperation, Document, \
    ExternalAuthentication
from service.settings import MD_RELATION_TYPE_DESCRIBED_BY, ALLOWED_SRS
from structure.models import Organization, User


class OGCWebFeatureServiceFactory:
    """ Creates the correct OGCWebFeatureService objects

    """
    def get_ogc_wfs(self, version: VersionEnum, service_connect_url=None):
        """ Returns the correct implementation of an OGCWebFeatureService according to the given version

        Args:
            version: The version number of the service
            service_connect_url: The capabilities request uri
        Returns:
            An OGCWebFeatureService
        """
        if version is VersionEnum.V_1_0_0:
            return OGCWebFeatureService_1_0_0(service_connect_url=service_connect_url)
        if version is VersionEnum.V_1_1_0:
            return OGCWebFeatureService_1_1_0(service_connect_url=service_connect_url)
        if version is VersionEnum.V_2_0_0:
            return OGCWebFeatureService_2_0_0(service_connect_url=service_connect_url)
        if version is VersionEnum.V_2_0_2:
            return OGCWebFeatureService_2_0_2(service_connect_url=service_connect_url)


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
        self.list_stored_queries_uri = {
            "get": None,
            "post": None,
        }
        self.get_property_value_uri = {
            "get": None,
            "post": None,
        }
        self.describe_stored_queries_uri = {
            "get": None,
            "post": None,
        }

        self.feature_type_list = {}

        # for wfs we need to overwrite the default namespace with 'wfs'
        XML_NAMESPACES["default"] = XML_NAMESPACES.get("wfs", "")

    class Meta:
        abstract = True

    @abstractmethod
    def create_from_capabilities(self, metadata_only: bool = False, async_task: Task = None):
        """ Fills the object with data from the capabilities document

        Returns:
             nothing
        """
        # get xml as iterable object
        xml_obj = xml_helper.parse_xml(xml=self.service_capabilities_xml)

        # parse service metadata
        self.get_service_metadata_from_capabilities(xml_obj, async_task)
        self.get_capability_metadata(xml_obj)

        # check possible operations on this service
        start_time = time.time()
        self.get_service_operations(xml_obj, self.get_parser_prefix())
        print(EXEC_TIME_PRINT % ("service operation checking", time.time() - start_time))

        # check if 'real' linked service metadata exist
        service_metadata_uri = xml_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:ExtendedCapabilities/inspire_dls:ExtendedCapabilities/inspire_common:MetadataUrl/inspire_common:URL")
        if service_metadata_uri is not None:
            self.get_service_metadata(uri=service_metadata_uri, async_task=async_task)

        if not metadata_only:
            start_time = time.time()
            self.get_feature_type_metadata(xml_obj=xml_obj, async_task=async_task)
            print(EXEC_TIME_PRINT % ("featuretype metadata", time.time() - start_time))

        # always execute version specific tasks AFTER multithreading
        # Otherwise we might face race conditions which lead to loss of data!
        self.get_version_specific_metadata(xml_obj)


    @abstractmethod
    def get_service_metadata_from_capabilities(self, xml_obj, async_task: Task = None):
        """ Parse the capability document <Service> metadata into the self object

        Args:
            xml_obj: A minidom object which holds the xml content
        Returns:
             Nothing
        """
        self.service_identification_title = xml_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:ServiceIdentification/ows:Title")

        if async_task is not None:
            task_helper.update_service_description(async_task, self.service_identification_title)

        self.service_identification_abstract = xml_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:ServiceIdentification/ows:Abstract")
        self.service_identification_fees = xml_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:ServiceIdentification/ows:Fees")
        self.service_identification_accessconstraints = xml_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:ServiceIdentification/ows:AccessConstraints")
        keywords = xml_helper.try_get_element_from_xml(xml_elem=xml_obj, elem="//ows:ServiceIdentification/ows:Keywords/ows:Keyword")
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

        self.service_provider_providername = xml_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:ProviderName")
        provider_site_elem = xml_helper.try_get_single_element_from_xml("//ows:ProviderSite", xml_obj)
        self.service_provider_url = xml_helper.get_href_attribute(xml_elem=provider_site_elem)
        self.service_provider_responsibleparty_individualname = xml_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:IndividualName")
        self.service_provider_responsibleparty_positionname = xml_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:PositionName")
        self.service_provider_telephone_voice = xml_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:Voice")
        self.service_provider_telephone_facsimile = xml_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:Facsimile")
        self.service_provider_address = xml_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:DeliveryPoint")
        self.service_provider_address_city = xml_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:City")
        self.service_provider_address_state_or_province = xml_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:AdministrativeArea")
        self.service_provider_address_postalcode = xml_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:PostalCode")
        self.service_provider_address_country = xml_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:Country")
        self.service_provider_address_electronicmailaddress = xml_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:ElectronicMailAddress")
        online_resource_elem = xml_helper.try_get_single_element_from_xml(xml_elem=xml_obj, elem="//ows:OnlineResource")
        self.service_provider_onlineresource_linkage = xml_helper.get_href_attribute(online_resource_elem)
        if self.service_provider_onlineresource_linkage is None or self.service_provider_onlineresource_linkage == "":
            # There are metadatas where no online resource link is given. We need to generate it manually therefore...
            self.service_provider_onlineresource_linkage = service_helper.split_service_uri(self.service_connect_url).get("base_uri") + "?"
        self.service_provider_contact_hoursofservice = xml_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:HoursOfService")
        self.service_provider_contact_contactinstructions = xml_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//ows:ContactInstructions")

    @abstractmethod
    def get_capability_metadata(self, xml_obj):
        """ Parse the capabilities document <Capability> metadata into the self object

        Args:
            xml_obj: A minidom object which holds the xml content
        Returns:
             Nothing
        """
        operation_metadata = xml_helper.try_get_element_from_xml("//" + GENERIC_NAMESPACE_TEMPLATE.format("OperationsMetadata"), xml_obj)
        if len(operation_metadata) > 0:
            operation_metadata = operation_metadata[0]
        else:
            return
        actions = ["GetCapabilities", "DescribeFeatureType", "GetFeature",
                   "Transaction", "LockFeature", "GetFeatureWithLock",
                   "GetGmlObject", "ListStoredQueries", "DescribeStoredQueries",
                   "GetPropertyValue"
                   ]
        get = {}
        post = {}

        for action in actions:
            xpath_str = './ows:Operation[@name="' + action + '"]'
            operation = xml_helper.try_get_single_element_from_xml(xml_elem=operation_metadata, elem=xpath_str)

            if operation is None:
                continue

            get_elem = xml_helper.try_get_single_element_from_xml(elem=".//ows:Get", xml_elem=operation)
            _get = xml_helper.get_href_attribute(xml_elem=get_elem)

            post_elem = xml_helper.try_get_single_element_from_xml(elem=".//ows:Post", xml_elem=operation)
            _post = xml_helper.get_href_attribute(xml_elem=post_elem)

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

        self.get_gml_object_uri["get"] = get.get("GetGmlObject", None)
        self.get_gml_object_uri["post"] = post.get("GetGmlObject", None)

        self.list_stored_queries_uri["get"] = get.get("ListStoredQueries", None)
        self.list_stored_queries_uri["post"] = post.get("ListStoredQueries", None)

        self.get_property_value_uri["get"] = get.get("GetPropertyValue", None)
        self.get_property_value_uri["post"] = post.get("GetPropertyValue", None)

        self.describe_stored_queries_uri["get"] = get.get("DescribeStoredQueries", None)
        self.describe_stored_queries_uri["post"] = post.get("DescribeStoredQueries", None)

    def _get_feature_type_metadata(self, feature_type, epsg_api, service_type_version: str, async_task: Task = None, step_size: float = None):
        """ Get featuretype metadata of a single featuretype

        Args:
            feature_type: The featuretype xml object
            epsg_api: The epsg api object
            service_type_version(str): The service type version as string
        Returns:
            feature_type_list(dict): A dict containing all different metadatas for this featuretype and it's children
        """
        # update async task if this is called async
        if async_task is not None and step_size is not None:
            task_helper.update_progress_by_step(async_task, step_size)

        f_t = FeatureType()
        md = Metadata()
        md_type = MetadataType.objects.get_or_create(type=MD_TYPE_FEATURETYPE)[0]
        md.metadata_type = md_type
        md.uuid = uuid.uuid4()
        f_t.metadata = md
        f_t.uuid = uuid.uuid4()
        md.title = xml_helper.try_get_text_from_xml_element(xml_elem=feature_type, elem=".//wfs:Title")
        md.identifier = xml_helper.try_get_text_from_xml_element(xml_elem=feature_type, elem=".//wfs:Name")
        md.abstract = xml_helper.try_get_text_from_xml_element(xml_elem=feature_type, elem=".//wfs:Abstract")

        # Feature type keywords
        keywords = xml_helper.try_get_element_from_xml(xml_elem=feature_type, elem=".//ows:Keyword")
        keyword_list = []
        for keyword in keywords:
            kw = xml_helper.try_get_text_from_xml_element(xml_elem=keyword)
            if kw is None:
                continue
            kw = Keyword.objects.get_or_create(keyword=kw)[0]
            f_t.metadata.keywords_list.append(kw)

        # SRS
        ## default
        srs = xml_helper.try_get_text_from_xml_element(xml_elem=feature_type, elem=".//wfs:DefaultSRS")
        if srs is not None:
            parts = epsg_api.get_subelements(srs)
            srs_default = ReferenceSystem.objects.get_or_create(code=parts.get("code"), prefix=parts.get("prefix"))[0]
            f_t.default_srs = srs_default
        ## additional
        srs = xml_helper.try_get_element_from_xml(xml_elem=feature_type, elem=".//wfs:OtherSRS")
        srs_list = []
        for sys in srs:
            parts = epsg_api.get_subelements(sys.text)
            # check if this srs is allowed for us. If not, skip it!
            if parts.get("code") not in ALLOWED_SRS:
                continue
            srs_other = ReferenceSystem.objects.get_or_create(code=parts.get("code"), prefix=parts.get("prefix"))[0]
            srs_list.append(srs_other)

        # Latlon bounding box
        tmp = xml_helper.try_get_text_from_xml_element(elem=".//ows:LowerCorner", xml_elem=feature_type)
        min_x = tmp.split(" ")[0]
        min_y = tmp.split(" ")[1]
        tmp = xml_helper.try_get_text_from_xml_element(elem=".//ows:UpperCorner", xml_elem=feature_type)
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
        formats = xml_helper.try_get_element_from_xml(xml_elem=feature_type, elem=".//wfs:Format")
        format_list = []
        for _format in formats:
            m_t = MimeType.objects.get_or_create(
                mime_type=xml_helper.try_get_text_from_xml_element(
                    xml_elem=_format
                )
            )[0]
            format_list.append(m_t)

        # Dataset (ISO) Metadata parsing
        self.__parse_iso_md(f_t, feature_type)

        # Feature type elements
        # Feature type namespaces
        elements_namespaces = self._get_featuretype_elements_namespaces(f_t, service_type_version)

        self.feature_type_list[f_t.metadata.identifier] = {
            "feature_type": f_t,
            "srs_list": srs_list,
            "format_list": format_list,
            "element_list": elements_namespaces.get("element_list", []),
            "ns_list": elements_namespaces.get("ns_list", []),
            "dataset_md_list": f_t.dataset_md_list,
        }

    @abstractmethod
    def get_feature_type_metadata(self, xml_obj, async_task: Task = None):
        """ Parse the capabilities document <FeatureTypeList> metadata into the self object

        This abstract implementation follows the wfs specification for version 1.1.0

        Args:
            xml_obj: A minidom object which holds the xml content
            async_task: The async task object
        Returns:
             Nothing
        """
        feature_type_list = xml_helper.try_get_element_from_xml(elem="//wfs:FeatureType", xml_elem=xml_obj)
        service_type_version = xml_helper.try_get_attribute_from_xml_element(xml_elem=xml_obj,
                                                                                 attribute="version",
                                                                                 elem="//wfs:WFS_Capabilities")
        epsg_api = EpsgApi()
        # Feature types
        thread_list = []

        len_ft_list = len(feature_type_list)

        # calculate the step size for an async call
        # 55 is the diff from the last process update (10) to the next static one (65)
        step_size = float(PROGRESS_STATUS_AFTER_PARSING / len_ft_list)

        # decide whether to use multithreading or iterative approach
        if len_ft_list > MULTITHREADING_THRESHOLD:
            for xml_feature_type in feature_type_list:
                thread_list.append(threading.Thread(target=self._get_feature_type_metadata, args=(xml_feature_type, epsg_api, service_type_version, async_task, step_size)))
            execute_threads(thread_list)
        else:
            for xml_feature_type in feature_type_list:
                self._get_feature_type_metadata(xml_feature_type, epsg_api, service_type_version, async_task, step_size)


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
            descr_feat_root = xml_helper.get_feature_type_elements_xml(title=feature_type.metadata.identifier,
                                                                    service_type="wfs",
                                                                    service_type_version=service_type_version,
                                                                    uri=self.describe_feature_type_uri.get("get"))
            if descr_feat_root is not None:
                # Feature type elements
                elements = xml_helper.try_get_element_from_xml(elem="//xsd:element", xml_elem=descr_feat_root)
                for element in elements:
                    f_t_element = FeatureTypeElement.objects.get_or_create(
                        name=xml_helper.try_get_attribute_from_xml_element(xml_elem=element, attribute="name"),
                        type=xml_helper.try_get_attribute_from_xml_element(xml_elem=element, attribute="type"),
                    )[0]
                    element_list.append(f_t_element)

                # Feature type namespaces
                namespaces = xml_helper.try_get_element_from_xml(elem="./namespace::*", xml_elem=descr_feat_root)
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

    def get_single_feature_type_metadata(self, identifier):
        if self.service_capabilities_xml is None:
            # load xml, might have been forgotten
            self.get_capabilities()

        xml_obj = xml_helper.parse_xml(xml=self.service_capabilities_xml)
        feature_type = xml_helper.try_get_element_from_xml(xml_elem=xml_obj, elem="//wfs:FeatureType/wfs:Name[text()='{}']/parent::wfs:FeatureType".format(identifier))
        service_type_version = xml_helper.try_get_attribute_from_xml_element(xml_elem=xml_obj,
                                                                                 attribute="version",
                                                                                 elem="//wfs:WFS_Capabilities")
        if len(feature_type) > 0:
            feature_type = feature_type[0]
            epsg_api = EpsgApi()
            self._get_feature_type_metadata(feature_type, epsg_api, service_type_version)

    @abstractmethod
    def create_service_model_instance(self, user: User, register_group, register_for_organization):
        """ Map all data from the WebFeatureService classes to their database models

        This does not persist the models to the database!

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
        md_type = MetadataType.objects.get_or_create(type=MD_TYPE_SERVICE)[0]
        md.metadata_type = md_type
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
        md.fees = self.service_identification_fees
        md.created_by = group
        md.capabilities_original_uri = self.service_connect_url
        md.capabilities_uri = self.service_connect_url
        md.bounding_geometry = self.service_bounding_box

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

        service.get_capabilities_uri_GET = self.get_capabilities_uri.get("get", None)
        service.get_capabilities_uri_POST = self.get_capabilities_uri.get("post", None)

        service.describe_layer_uri_GET = self.describe_feature_type_uri.get("get", None)
        service.describe_layer_uri_POST = self.describe_feature_type_uri.get("post", None)

        service.get_feature_info_uri_GET = self.get_feature_uri.get("get", None)
        service.get_feature_info_uri_POST = self.get_feature_uri.get("post", None)

        service.transaction_uri_GET = self.transaction_uri.get("get", None)
        service.transaction_uri_POST = self.transaction_uri.get("post", None)

        service.get_property_value_uri_GET = self.get_property_value_uri.get("get", None)
        service.get_property_value_uri_POST = self.get_property_value_uri.get("post", None)

        service.list_stored_queries_uri_GET = self.list_stored_queries_uri.get("get", None)
        service.list_stored_queries_uri_GET = self.list_stored_queries_uri.get("post", None)

        service.describe_stored_queries_uri_GET = self.describe_stored_queries_uri.get("get", None)
        service.describe_stored_queries_uri_POST = self.describe_stored_queries_uri.get("post", None)

        service.get_gml_objct_uri_GET = self.get_gml_object_uri.get("get", None)
        service.get_gml_objct_uri_POST = self.get_gml_object_uri.get("post", None)

        service.availability = 0.0
        service.is_available = False
        service.is_root = True

        md.service = service

        if self.linked_service_metadata is not None:
            service.linked_service_metadata = self.linked_service_metadata.to_db_model(MD_TYPE_SERVICE)

        # Keywords
        for kw in self.service_identification_keywords:
            if kw is None:
                continue
            keyword = Keyword.objects.get_or_create(keyword=kw)[0]
            md.keywords_list.append(keyword)

        # feature types
        for feature_type_key, feature_type_val in self.feature_type_list.items():
            f_t = feature_type_val.get("feature_type")
            f_t.metadata.created_by = group
            f_t.parent_service = service
            f_t.metadata.contact = contact
            f_t.metadata.capabilities_original_uri = self.service_connect_url
            f_t.metadata.capabilities_uri = self.service_connect_url

            f_t.dataset_md_list = feature_type_val.get("dataset_md_list", [])
            f_t.additional_srs_list = feature_type_val.get("srs_list", [])
            f_t.formats_list = feature_type_val.get("format_list", [])
            f_t.elements_list = feature_type_val.get("element_list", [])
            f_t.namespaces_list = feature_type_val.get("ns_list", [])

            # add feature type to list of related feature types
            service.feature_type_list.append(f_t)

        return service

    @transaction.atomic
    def persist_service_model(self, service, external_auth: ExternalAuthentication):
        """ Persist the service model object

        Returns:
             Nothing
        """
        # save metadata
        md = service.metadata
        md.save()
        if external_auth is not None:
            external_auth.metadata = md
            external_auth.save()

        # save linked service metadata
        if service.linked_service_metadata is not None:
            md_relation = MetadataRelation()
            md_relation.metadata_from = md
            md_relation.metadata_to = service.linked_service_metadata
            md_relation.origin = MetadataOrigin.objects.get_or_create(
                name='capabilities'
            )[0]
            md_relation.relation_type = MD_RELATION_TYPE_VISUALIZES
            md_relation.save()
            md.related_metadata.add(md_relation)

        # save again, due to added related metadata
        md.save()

        service.metadata = md
        # save parent service
        service.save()

        # Keywords
        for kw in service.metadata.keywords_list:
            service.metadata.keywords.add(kw)

        # feature types
        for f_t in service.feature_type_list:
            f_t.parent_service = service
            md = f_t.metadata
            md.save()
            f_t.metadata = md
            f_t.save()

            # persist featuretype keywords through metadata
            for kw in f_t.metadata.keywords_list:
                f_t.metadata.keywords.add(kw)

            # dataset_md of feature types
            for dataset_md in f_t.dataset_md_list:
                dataset_md.save()
                md_relation = MetadataRelation()
                md_relation.metadata_from = f_t.metadata
                md_relation.metadata_to = dataset_md
                origin = MetadataOrigin.objects.get_or_create(name="capabilities")[0]
                md_relation.origin = origin
                md_relation.relation_type = MD_RELATION_TYPE_DESCRIBED_BY
                md_relation.save()
                f_t.metadata.related_metadata.add(md_relation)

            # keywords of feature types
            for kw in f_t.keywords_list:
                f_t.metadata.keywords.add(kw)

            # all (additional + default) srs of feature types
            for srs in f_t.additional_srs_list:
                f_t.metadata.reference_system.add(srs)

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


    ### ISO METADATA ###
    def __parse_iso_md(self, feature_type, xml_feature_type_obj: _Element):
        # check for possible ISO metadata
        if self.has_iso_metadata(xml_feature_type_obj):
            iso_metadata_xml_elements = xml_helper.try_get_element_from_xml(xml_elem=xml_feature_type_obj,
                                                                            elem="./wfs:MetadataURL")
            for iso_xml in iso_metadata_xml_elements:
                iso_uri = xml_helper.try_get_text_from_xml_element(xml_elem=iso_xml)
                try:
                    iso_metadata = ISOMetadata(uri=iso_uri, origin="capabilities")
                except Exception:
                    # there are iso metadatas that have been filled wrongly -> if so we will drop them
                    continue
                feature_type.dataset_md_list.append(iso_metadata.to_db_model())



    def get_feature_type_by_identifier(self, identifier: str = None):
        """ Extract a single feature type by its identifier and parse it into a FeatureType object

        Args:
            identifier (str): Identifier for the requested FeatureType
        Returns:
            a parsed FeatureType object
        """
        # feature types are stored in the .feature_type_list attribute
        self.get_single_feature_type_metadata(identifier)
        f_t = None
        for key, val in self.feature_type_list.items():
            f_t = val
            break
        return f_t


class OGCWebFeatureService_1_0_0(OGCWebFeatureService):
    """
    The wfs version 1.0.0 is slightly different than the rest. Therefore we need to overwrite the abstract
    methods and provide an individual way to parse the data.
    """
    def __init__(self, service_connect_url):
        super().__init__(
            service_connect_url=service_connect_url,
            service_version=VersionEnum.V_1_0_0,
            service_type=ServiceEnum.WFS,
        )
        XML_NAMESPACES["schemaLocation"] = "http://geodatenlb1.rlp:80/geoserver/schemas/wfs/1.0.0/WFS-capabilities.xsd"
        XML_NAMESPACES["xsi"] = "http://www.w3.org/2001/XMLSchema-instance"
        XML_NAMESPACES["lvermgeo"] = "http://www.lvermgeo.rlp.de/lvermgeo"
        XML_NAMESPACES["default"] = XML_NAMESPACES.get("wfs")

    def get_parser_prefix(self):
        return "wfs:"

    def get_service_operations(self, xml_obj, prefix: str):
        """ Creates table records from <Capability><Request></Request></Capability contents

        Args:
            xml_obj: The xml document object
            prefix: The prefix for the service type ('wms'/'wfs')
        Returns:

        """
        cap_request = xml_helper.try_get_single_element_from_xml("//{}Capability/{}Request".format(prefix, prefix), xml_obj)
        if cap_request is None:
            return
        operations = cap_request.getchildren()
        for operation in operations:
            RequestOperation.objects.get_or_create(
                operation_name=operation.tag,
            )

    def get_service_metadata_from_capabilities(self, xml_obj, async_task: Task = None):
        """ Parse the wfs <Service> metadata into the self object

        Args:
            xml_obj: A minidom object which holds the xml content
        Returns:
             Nothing
        """
        service_node = xml_helper.try_get_single_element_from_xml(elem="/wfs:WFS_Capabilities/wfs:Service", xml_elem=xml_obj)
        # TITLE
        title_node = xml_helper.try_get_text_from_xml_element(elem="./wfs:Title", xml_elem=service_node)
        self.service_identification_title = title_node

        # ABSTRACT
        self.service_identification_abstract = xml_helper.try_get_text_from_xml_element(elem="./wfs:Abstract", xml_elem=service_node)

        # FEES
        self.service_identification_fees = xml_helper.try_get_text_from_xml_element(elem="./wfs:Fees", xml_elem=service_node)

        # ACCESS CONSTRAINTS
        self.service_identification_accessconstraints = xml_helper.try_get_text_from_xml_element(elem="./wfs:AccessConstraints", xml_elem=service_node)

        # KEYWORDS
        keywords_str = xml_helper.try_get_text_from_xml_element(elem="./wfs:Keywords", xml_elem=service_node)
        self.service_identification_keywords = service_helper.resolve_keywords_array_string(keywords_str)
        del keywords_str

        # ONLINE RESOURCE
        self.service_provider_onlineresource_linkage = xml_helper.try_get_text_from_xml_element(elem="./wfs:OnlineResource", xml_elem=service_node)

        del service_node

    def get_capability_metadata(self, xml_obj):
        """ Parse the wfs <Capability> metadata into the self object

        Args:
            xml_obj: A minidom object which holds the xml content
        Returns:
             Nothing
        """
        cap_node = xml_helper.try_get_single_element_from_xml("//wfs:Capability", xml_elem=xml_obj)
        actions = [
            "GetCapabilities",
            "DescribeFeatureType",
            "GetFeature",
            "Transaction",
            "LockFeature",
            "GetFeatureWithLock"
        ]
        get = {}
        post = {}
        for action in actions:
            node = xml_helper.try_get_single_element_from_xml(".//wfs:" + action, cap_node)
            if node is None:
                continue
            get[action] = xml_helper.try_get_attribute_from_xml_element(elem=".//wfs:Get", xml_elem=node, attribute="onlineResource")
            post[action] = xml_helper.try_get_attribute_from_xml_element(elem=".//wfs:Post", xml_elem=node, attribute="onlineResource")
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

    def get_feature_type_metadata(self, xml_obj, async_task: Task = None):
        """ Parse the wfs <Service> metadata into the self object

        Args:
            xml_obj: A minidom object which holds the xml content
        Returns:
             Nothing
        """
        service_type_version = xml_helper.try_get_attribute_from_xml_element(xml_elem=xml_obj,
                                                                                 attribute="version",
                                                                                 elem="//wfs:WFS_Capabilities")
        feat_nodes = xml_helper.try_get_element_from_xml("/wfs:WFS_Capabilities/wfs:FeatureTypeList/wfs:FeatureType", xml_obj)

        step_size = float(PROGRESS_STATUS_AFTER_PARSING / len(feat_nodes))

        for node in feat_nodes:
            feature_type = FeatureType()
            metadata = Metadata()
            feature_type.metadata = metadata
            feature_type.metadata.identifier = xml_helper.try_get_text_from_xml_element(elem=".//wfs:Name", xml_elem=node)
            feature_type.metadata.title = xml_helper.try_get_text_from_xml_element(elem=".//wfs:Title", xml_elem=node)
            feature_type.metadata.abstract = xml_helper.try_get_text_from_xml_element(elem=".//wfs:Abstract", xml_elem=node)
            keywords = service_helper.resolve_keywords_array_string(
                xml_helper.try_get_text_from_xml_element(elem=".//wfs:Keywords", xml_elem=node)
            )

            # keywords
            kw_list = []
            for keyword in keywords:
                if keyword is None:
                    continue
                kw = Keyword.objects.get_or_create(keyword=keyword)[0]
                feature_type.metadata.keywords_list.append(kw)

            # lat lon bounding box
            bbox = {
                "minx": xml_helper.try_get_attribute_from_xml_element(elem="./wfs:LatLongBoundingBox", xml_elem=node, attribute="minx"),
                "miny": xml_helper.try_get_attribute_from_xml_element(elem="./wfs:LatLongBoundingBox", xml_elem=node, attribute="miny"),
                "maxx": xml_helper.try_get_attribute_from_xml_element(elem="./wfs:LatLongBoundingBox", xml_elem=node, attribute="maxx"),
                "maxy": xml_helper.try_get_attribute_from_xml_element(elem="./wfs:LatLongBoundingBox", xml_elem=node, attribute="maxy"),
            }
            # create polygon element from simple bbox dict

            bounding_points = (
                (float(bbox["minx"]), float(bbox["miny"])),
                (float(bbox["minx"]), float(bbox["maxy"])),
                (float(bbox["maxx"]), float(bbox["maxy"])),
                (float(bbox["maxx"]), float(bbox["miny"])),
                (float(bbox["minx"]), float(bbox["miny"]))
            )
            feature_type.bbox_lat_lon = Polygon(bounding_points)

            # reference systems
            # append only the ...ToFeatureType objects, since the reference systems will be created automatically
            srs_list = xml_helper.try_get_element_from_xml("./wfs:SRS", node)
            srs_model_list = []
            epsg_api = EpsgApi()
            i = 0
            for srs in srs_list:
                srs_val = xml_helper.try_get_text_from_xml_element(srs)
                parts = epsg_api.get_subelements(srs_val)
                # check if this srs is allowed for us. If not, skip it!
                if parts.get("code") not in ALLOWED_SRS:
                    continue
                srs_model = ReferenceSystem.objects.get_or_create(code=parts.get("code"), prefix=parts.get("prefix"))[0]
                if i == 0:
                    # since the 1.0.0. standard does not differ between a default and additional systems, we must define th
                    # first reference system occuring as 'default'
                    feature_type.default_srs = srs_model
                else:
                    srs_model_list.append(srs_model)

            # Feature type elements
            # Feature type namespaces
            elements_namespaces = self._get_featuretype_elements_namespaces(feature_type, service_type_version)

            # put the feature types objects with keywords and reference systems into the dict for the persisting process
            self.feature_type_list[feature_type.metadata.identifier] = {
                "feature_type": feature_type,
                "keyword_list": kw_list,
                "srs_list": srs_model_list,
                "format_list": [],
                "element_list": elements_namespaces["element_list"],
                "ns_list": elements_namespaces["ns_list"],
            }

            # update async task if this is called async
            if async_task is not None and step_size is not None:
                task_helper.update_progress_by_step(async_task, step_size)


class OGCWebFeatureService_1_1_0(OGCWebFeatureService):
    """
    Uses base implementation from OGCWebFeatureService class
    """
    def __init__(self, service_connect_url):
        super().__init__(
            service_connect_url=service_connect_url,
            service_version=VersionEnum.V_1_1_0,
            service_type=ServiceEnum.WFS,
        )
        XML_NAMESPACES["wfs"] = "http://www.opengis.net/wfs"
        XML_NAMESPACES["ows"] = "http://www.opengis.net/ows"
        XML_NAMESPACES["fes"] = "http://www.opengis.net/fes"
        XML_NAMESPACES["default"] = XML_NAMESPACES["wfs"]

    def get_parser_prefix(self):
        return "ows:"

    def get_service_operations(self, xml_obj, prefix: str):
        """ Creates table records from <Capability><Request></Request></Capability contents

        Args:
            xml_obj: The xml document object
            prefix: The prefix for the service type ('wms'/'wfs')
        Returns:

        """
        operations = xml_helper.try_get_element_from_xml("//{}OperationsMetadata/{}Operation".format(prefix, prefix), xml_obj)
        for operation in operations:
            name = xml_helper.try_get_attribute_from_xml_element(operation, "name")
            RequestOperation.objects.get_or_create(
                operation_name=name,
            )

class OGCWebFeatureService_2_0_0(OGCWebFeatureService):
    """
    Uses base implementation from OGCWebFeatureService class
    """
    def __init__(self, service_connect_url):
        super().__init__(
            service_connect_url=service_connect_url,
            service_version=VersionEnum.V_2_0_0,
            service_type=ServiceEnum.WFS,
        )
        XML_NAMESPACES["wfs"] = "http://www.opengis.net/wfs/2.0"
        XML_NAMESPACES["ows"] = "http://www.opengis.net/ows/1.1"
        XML_NAMESPACES["fes"] = "http://www.opengis.net/fes/2.0"
        XML_NAMESPACES["default"] = XML_NAMESPACES["wfs"]

    def get_parser_prefix(self):
        return "ows:"

    def get_service_operations(self, xml_obj, prefix: str):
        """ Creates table records from <Capability><Request></Request></Capability contents

        Args:
            xml_obj: The xml document object
            prefix: The prefix for the service type ('wms'/'wfs')
        Returns:

        """
        operations = xml_helper.try_get_element_from_xml("//{}OperationsMetadata/{}Operation".format(prefix, prefix), xml_obj)
        for operation in operations:
            name = xml_helper.try_get_attribute_from_xml_element(operation, "name")
            RequestOperation.objects.get_or_create(
                operation_name=name,
            )

    def get_version_specific_metadata(self, xml_obj):
        """ Runs metadata parsing for data which is only present in this version

        Args:
            xml_obj: The xml metadata object
        Returns:
             nothing
        """
        epsg_api = EpsgApi()
        # featuretype keywords are different than in older versions
        feature_type_list = xml_helper.try_get_element_from_xml(elem="//wfs:FeatureType", xml_elem=xml_obj)
        for feature_type in feature_type_list:
            name = xml_helper.try_get_text_from_xml_element(xml_elem=feature_type, elem=".//wfs:Name")
            try:
                f_t = self.feature_type_list.get(name).get("feature_type")
            except AttributeError:
                # if this happens the metadata is broken or not reachable due to bad configuration
                raise BaseException(SERVICE_GENERIC_ERROR)
            # Feature type keywords
            keywords = xml_helper.try_get_element_from_xml(xml_elem=feature_type, elem=".//ows:Keyword")
            keyword_list = []
            for keyword in keywords:
                kw = xml_helper.try_get_text_from_xml_element(xml_elem=keyword)
                if kw is None:
                    continue
                kw = Keyword.objects.get_or_create(keyword=kw)[0]
                keyword_list.append(kw)
            self.feature_type_list[name]["keyword_list"] = keyword_list

            # srs are now called crs -> parse for crs again!
            # CRS
            ## default
            crs = xml_helper.try_get_text_from_xml_element(xml_elem=feature_type, elem=".//wfs:DefaultCRS")
            if crs is not None:
                parts = epsg_api.get_subelements(crs)
                # check if this srs is allowed for us. If not, skip it!
                if parts.get("code") not in ALLOWED_SRS:
                    continue
                crs_default = ReferenceSystem.objects.get_or_create(code=parts.get("code"), prefix=parts.get("prefix"))[0]
                f_t.default_srs = crs_default
            ## additional
            crs = xml_helper.try_get_element_from_xml(xml_elem=feature_type, elem=".//wfs:OtherCRS")
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
            service_version=VersionEnum.V_2_0_2,
            service_type=ServiceEnum.WFS,
        )
        XML_NAMESPACES["wfs"] = "http://www.opengis.net/wfs/2.0"
        XML_NAMESPACES["ows"] = "http://www.opengis.net/ows/1.1"
        XML_NAMESPACES["fes"] = "http://www.opengis.net/fes/2.0"
        XML_NAMESPACES["default"] = XML_NAMESPACES["wfs"]

    def get_parser_prefix(self):
        return "ows:"

    def get_service_operations(self, xml_obj, prefix: str):
        """ Creates table records from <Capability><Request></Request></Capability contents

        Args:
            xml_obj: The xml document object
            prefix: The prefix for the service type ('wms'/'wfs')
        Returns:

        """
        operations = xml_helper.try_get_element_from_xml("//{}OperationsMetadata/{}Operation".format(prefix, prefix), xml_obj)
        for operation in operations:
            name = xml_helper.try_get_attribute_from_xml_element(operation, "name")
            RequestOperation.objects.get_or_create(
                operation_name=name,
            )

