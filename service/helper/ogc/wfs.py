import threading
import uuid
from abc import abstractmethod
from collections import OrderedDict

import time

from celery import Task
from django.contrib.gis.geos import Polygon, GEOSGeometry
from lxml.etree import _Element

from service.settings import DEFAULT_SRS, SERVICE_OPERATION_URI_TEMPLATE, SERVICE_METADATA_URI_TEMPLATE, \
    HTML_METADATA_URI_TEMPLATE, service_logger
from MrMap.settings import XML_NAMESPACES, EXEC_TIME_PRINT, \
    MULTITHREADING_THRESHOLD, GENERIC_NAMESPACE_TEMPLATE
from MrMap.messages import SERVICE_GENERIC_ERROR
from MrMap.utils import execute_threads
from service.helper.enums import OGCServiceVersionEnum, OGCServiceEnum, OGCOperationEnum, ResourceOriginEnum, \
    MetadataRelationEnum
from service.helper.enums import MetadataEnum
from service.helper.epsg_api import EpsgApi
from service.helper.iso.iso_19115_metadata_parser import ISOMetadata
from service.helper.ogc.wms import OGCWebService
from service.helper import service_helper, xml_helper, task_helper
from service.models import FeatureType, Keyword, ReferenceSystem, Service, Metadata, ServiceType, MimeType, Namespace, \
    FeatureTypeElement, MetadataRelation, RequestOperation, ExternalAuthentication, ServiceUrl
from service.settings import ALLOWED_SRS, PROGRESS_STATUS_AFTER_PARSING
from structure.models import Organization, MrMapUser, MrMapGroup, Contact


class OGCWebFeatureServiceFactory:
    """ Creates the correct OGCWebFeatureService objects

    """
    def get_ogc_wfs(self, version: OGCServiceVersionEnum, service_connect_url=None, external_auth=None):
        """ Returns the correct implementation of an OGCWebFeatureService according to the given version

        Args:
            version: The version number of the service
            service_connect_url: The capabilities request uri
        Returns:
            An OGCWebFeatureService
        """
        if version is OGCServiceVersionEnum.V_1_0_0:
            return OGCWebFeatureService_1_0_0(service_connect_url=service_connect_url, external_auth=external_auth)
        if version is OGCServiceVersionEnum.V_1_1_0:
            return OGCWebFeatureService_1_1_0(service_connect_url=service_connect_url, external_auth=external_auth)
        if version is OGCServiceVersionEnum.V_2_0_0:
            return OGCWebFeatureService_2_0_0(service_connect_url=service_connect_url, external_auth=external_auth)
        if version is OGCServiceVersionEnum.V_2_0_2:
            return OGCWebFeatureService_2_0_2(service_connect_url=service_connect_url, external_auth=external_auth)


class OGCWebFeatureService(OGCWebService):

    def __init__(self, service_connect_url, service_version, service_type, external_auth: ExternalAuthentication):
        super().__init__(
            service_connect_url=service_connect_url,
            service_version=service_version,
            service_type=service_type,
            external_auth=external_auth
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
        self.service_mime_type_list = []
        self.service_mime_type_get_feature_list = []

        # for wfs we need to overwrite the default namespace with 'wfs'
        XML_NAMESPACES["default"] = XML_NAMESPACES.get("wfs", "")

    class Meta:
        abstract = True

    @abstractmethod
    def create_from_capabilities(self, metadata_only: bool = False, async_task: Task = None, external_auth: ExternalAuthentication = None):
        """ Fills the object with data from the capabilities document

        Returns:
             nothing
        """
        # get xml as iterable object
        xml_obj = xml_helper.parse_xml(xml=self.service_capabilities_xml)

        # parse service metadata
        self.get_service_metadata_from_capabilities(xml_obj, async_task)
        self.get_capability_metadata(xml_obj)

        # check if 'real' linked service metadata exist
        service_metadata_uri = xml_helper.try_get_text_from_xml_element(
            xml_elem=xml_obj,
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("ExtendedCapabilities") +
                 "/" + GENERIC_NAMESPACE_TEMPLATE.format("ExtendedCapabilities") +
                 "/" + GENERIC_NAMESPACE_TEMPLATE.format("MetadataUrl") +
                 "/" + GENERIC_NAMESPACE_TEMPLATE.format("URL")
        )
        if service_metadata_uri is not None:
            self.get_service_metadata(uri=service_metadata_uri, async_task=async_task)

        if not metadata_only:
            start_time = time.time()
            self.get_feature_type_metadata(xml_obj=xml_obj, async_task=async_task, external_auth=external_auth)
            service_logger.debug(EXEC_TIME_PRINT % ("featuretype metadata", time.time() - start_time))

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
        service_xml = xml_helper.try_get_single_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("ServiceIdentification"),
            xml_obj
        )
        self.service_identification_title = xml_helper.try_get_text_from_xml_element(
            xml_elem=service_xml,
            elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("Title")
        )

        if async_task is not None:
            task_helper.update_service_description(async_task, self.service_identification_title, phase_descr="Parsing main capabilities")

        self.service_identification_abstract = xml_helper.try_get_text_from_xml_element(
            xml_elem=service_xml,
            elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("Abstract")
        )

        self.service_identification_fees = xml_helper.try_get_text_from_xml_element(
            xml_elem=service_xml,
            elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("Fees")
        )

        self.service_identification_accessconstraints = xml_helper.try_get_text_from_xml_element(
            xml_elem=service_xml,
            elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("AccessConstraints")
        )

        keywords = xml_helper.try_get_element_from_xml(
            xml_elem=service_xml,
            elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("Keywords") +
                 "/" + GENERIC_NAMESPACE_TEMPLATE.format("Keyword")
        ) or []
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

        self.service_provider_providername = xml_helper.try_get_text_from_xml_element(
            xml_elem=xml_obj,
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("ProviderName")
        )

        provider_site_elem = xml_helper.try_get_single_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("ProviderSite"),
            xml_obj
        )
        self.service_provider_url = xml_helper.get_href_attribute(xml_elem=provider_site_elem)
        self.service_provider_responsibleparty_individualname = xml_helper.try_get_text_from_xml_element(
            xml_elem=xml_obj,
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("IndividualName")
        )
        self.service_provider_responsibleparty_positionname = xml_helper.try_get_text_from_xml_element(
            xml_elem=xml_obj,
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("PositionName")
        )
        self.service_provider_telephone_voice = xml_helper.try_get_text_from_xml_element(
            xml_elem=xml_obj,
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("Voice")
        )
        self.service_provider_telephone_facsimile = xml_helper.try_get_text_from_xml_element(
            xml_elem=xml_obj,
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("Facsimile")
        )
        self.service_provider_address = xml_helper.try_get_text_from_xml_element(
            xml_elem=xml_obj,
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("DeliveryPoint")
        )
        self.service_provider_address_city = xml_helper.try_get_text_from_xml_element(
            xml_elem=xml_obj,
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("City")
        )
        self.service_provider_address_state_or_province = xml_helper.try_get_text_from_xml_element(
            xml_elem=xml_obj,
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("AdministrativeArea")
        )
        self.service_provider_address_postalcode = xml_helper.try_get_text_from_xml_element(
            xml_elem=xml_obj,
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("PostalCode")
        )
        self.service_provider_address_country = xml_helper.try_get_text_from_xml_element(
            xml_elem=xml_obj,
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("Country")
        )
        self.service_provider_address_electronicmailaddress = xml_helper.try_get_text_from_xml_element(
            xml_elem=xml_obj,
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("ElectronicMailAddress")
        )
        online_resource_elem = xml_helper.try_get_single_element_from_xml(
            xml_elem=xml_obj,
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource")
        )
        self.service_provider_onlineresource_linkage = xml_helper.get_href_attribute(online_resource_elem)
        if self.service_provider_onlineresource_linkage is None or self.service_provider_onlineresource_linkage == "":
            # There are metadatas where no online resource link is given. We need to generate it manually therefore...
            self.service_provider_onlineresource_linkage = service_helper.split_service_uri(self.service_connect_url).get("base_uri")
            self.service_provider_onlineresource_linkage = service_helper.prepare_original_uri_stump(self.service_provider_onlineresource_linkage)

        self.service_provider_contact_hoursofservice = xml_helper.try_get_text_from_xml_element(
            xml_elem=xml_obj,
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("HoursOfService")
        )
        self.service_provider_contact_contactinstructions = xml_helper.try_get_text_from_xml_element(
            xml_elem=xml_obj,
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("ContactInstructions")
        )

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

        # Shorten the usage of our operation enums
        get_cap = OGCOperationEnum.GET_CAPABILITIES.value
        descr_feat = OGCOperationEnum.DESCRIBE_FEATURE_TYPE.value
        get_feat = OGCOperationEnum.GET_FEATURE.value
        trans = OGCOperationEnum.TRANSACTION.value
        lock_feat = OGCOperationEnum.LOCK_FEATURE.value
        get_feat_lock = OGCOperationEnum.GET_FEATURE_WITH_LOCK.value
        get_gml = OGCOperationEnum.GET_GML_OBJECT.value
        list_stored_queries = OGCOperationEnum.LIST_STORED_QUERIES.value
        descr_stored_queries = OGCOperationEnum.DESCRIBE_STORED_QUERIES.value
        get_prop_val = OGCOperationEnum.GET_PROPERTY_VALUE.value

        actions = [
            get_cap,
            descr_feat,
            get_feat,
            trans,
            lock_feat,
            get_feat_lock,
            get_gml,
            list_stored_queries,
            descr_stored_queries,
            get_prop_val,
        ]
        get = {}
        post = {}

        for action in actions:
            xpath_str = './' + GENERIC_NAMESPACE_TEMPLATE.format('Operation') + '[@name="' + action + '"]'
            operation_elem = xml_helper.try_get_single_element_from_xml(xml_elem=operation_metadata, elem=xpath_str)

            if operation_elem is None:
                continue

            get_uri_elem = xml_helper.try_get_single_element_from_xml(
                elem=".//" + GENERIC_NAMESPACE_TEMPLATE.format("Get"),
                xml_elem=operation_elem
            )
            _get = xml_helper.get_href_attribute(xml_elem=get_uri_elem)

            post_uri_elem = xml_helper.try_get_single_element_from_xml(
                elem=".//" + GENERIC_NAMESPACE_TEMPLATE.format("Post"),
                xml_elem=operation_elem
            )
            _post = xml_helper.get_href_attribute(xml_elem=post_uri_elem)

            get[action] = _get
            post[action] = _post

            # Parse the possible outputFormats for every operation object
            output_format_element = xml_helper.try_get_single_element_from_xml(
                './/' + GENERIC_NAMESPACE_TEMPLATE.format('Parameter') + '[@name="outputFormat"]',
                operation_elem
            )
            if output_format_element is not None:
                output_format_value_elements = xml_helper.try_get_element_from_xml(
                    ".//" + GENERIC_NAMESPACE_TEMPLATE.format("Value"),
                    output_format_element
                )
                for value_elem in output_format_value_elements:
                    format_value = xml_helper.try_get_text_from_xml_element(value_elem)
                    mime_type = MimeType.objects.get_or_create(
                        operation=action,
                        mime_type=format_value
                    )[0]
                    self.service_mime_type_list.append(mime_type)
                    if action == OGCOperationEnum.GET_FEATURE.value:
                        self.service_mime_type_get_feature_list.append(mime_type)

        self.get_capabilities_uri["get"] = get.get(get_cap, None)
        self.get_capabilities_uri["post"] = post.get(get_cap, None)

        self.describe_feature_type_uri["get"] = get.get(descr_feat, None)
        self.describe_feature_type_uri["post"] = post.get(descr_feat, None)

        self.get_feature_uri["get"] = get.get(get_feat, None)
        self.get_feature_uri["post"] = post.get(get_feat, None)

        self.transaction_uri["get"] = get.get(trans, None)
        self.transaction_uri["post"] = post.get(trans, None)

        self.lock_feature_uri["get"] = get.get(lock_feat, None)
        self.lock_feature_uri["post"] = post.get(lock_feat, None)

        self.get_feature_with_lock_uri["get"] = get.get(get_feat_lock, None)
        self.get_feature_with_lock_uri["post"] = post.get(get_feat_lock, None)

        self.get_gml_object_uri["get"] = get.get(get_gml, None)
        self.get_gml_object_uri["post"] = post.get(get_gml, None)

        self.list_stored_queries_uri["get"] = get.get(list_stored_queries, None)
        self.list_stored_queries_uri["post"] = post.get(list_stored_queries, None)

        self.get_property_value_uri["get"] = get.get(get_prop_val, None)
        self.get_property_value_uri["post"] = post.get(get_prop_val, None)

        self.describe_stored_queries_uri["get"] = get.get(descr_stored_queries, None)
        self.describe_stored_queries_uri["post"] = post.get(descr_stored_queries, None)

    def _get_feature_type_metadata(self, feature_type, epsg_api, service_type_version: str, async_task: Task = None, step_size: float = None, external_auth: ExternalAuthentication = None):
        """ Get featuretype metadata of a single featuretype

        Args:
            feature_type: The featuretype xml object
            epsg_api: The epsg api object
            service_type_version(str): The service type version as string
        Returns:
            feature_type_list(dict): A dict containing all different metadatas for this featuretype and it's children
        """

        f_t = FeatureType()
        md = Metadata()
        md_type = MetadataEnum.FEATURETYPE.value
        md.metadata_type = md_type
        f_t.metadata = md
        md.title = xml_helper.try_get_text_from_xml_element(
            xml_elem=feature_type,
            elem=".//" + GENERIC_NAMESPACE_TEMPLATE.format("Title")
        )

        # update async task if this is called async
        if async_task is not None and step_size is not None:
            task_helper.update_progress_by_step(async_task, step_size)
            task_helper.update_service_description(async_task, None, "Parsing {}".format(md.title))

        md.identifier = xml_helper.try_get_text_from_xml_element(
            xml_elem=feature_type,
            elem=".//" + GENERIC_NAMESPACE_TEMPLATE.format("Name")
        )
        md.abstract = xml_helper.try_get_text_from_xml_element(
            xml_elem=feature_type,
            elem=".//" + GENERIC_NAMESPACE_TEMPLATE.format("Abstract")
        )

        # Feature type keywords
        keywords = xml_helper.try_get_element_from_xml(
            xml_elem=feature_type,
            elem=".//" + GENERIC_NAMESPACE_TEMPLATE.format("Keyword")
        )

        for keyword in keywords:
            kw = xml_helper.try_get_text_from_xml_element(xml_elem=keyword)
            if kw is None:
                continue
            kw = Keyword.objects.get_or_create(keyword=kw)[0]
            f_t.metadata.keywords_list.append(kw)

        # SRS
        ## default
        srs = xml_helper.try_get_text_from_xml_element(
            xml_elem=feature_type,
            elem=".//" + GENERIC_NAMESPACE_TEMPLATE.format("DefaultSRS")
        )
        if srs is not None:
            parts = epsg_api.get_subelements(srs)
            srs_default = ReferenceSystem.objects.get_or_create(code=parts.get("code"), prefix=parts.get("prefix"))[0]
            f_t.default_srs = srs_default

        ## additional
        srs = xml_helper.try_get_element_from_xml(
            xml_elem=feature_type,
            elem=".//" + GENERIC_NAMESPACE_TEMPLATE.format("OtherSRS"))
        srs_list = []
        for sys in srs:
            parts = epsg_api.get_subelements(sys.text)
            # check if this srs is allowed for us. If not, skip it!
            if parts.get("code") not in ALLOWED_SRS:
                continue
            srs_other = ReferenceSystem.objects.get_or_create(code=parts.get("code"), prefix=parts.get("prefix"))[0]
            srs_list.append(srs_other)

        # Latlon bounding box
        tmp = xml_helper.try_get_text_from_xml_element(
            elem=".//" + GENERIC_NAMESPACE_TEMPLATE.format("LowerCorner"),
            xml_elem=feature_type
        )
        if tmp is not None:
            # tmp might be None if no extent information are found. Just skip this.
            min_x = tmp.split(" ")[0]
            min_y = tmp.split(" ")[1]
            tmp = xml_helper.try_get_text_from_xml_element(
                elem=".//" + GENERIC_NAMESPACE_TEMPLATE.format("UpperCorner"),
                xml_elem=feature_type
            )
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
            f_t.metadata.bounding_geometry = bbox
            f_t.bbox_lat_lon = bbox

        # Output formats
        formats = xml_helper.try_get_element_from_xml(
            xml_elem=feature_type,
            elem=".//" + GENERIC_NAMESPACE_TEMPLATE.format("Format")
        )
        format_list = []

        if len(formats) == 0:
            # No Formats found on feature type level. Specification says, we use the same formats, that are specified
            # by the parent service element
            format_list = self.service_mime_type_get_feature_list
        else:
            for _format in formats:
                # Due to missing semantic interpretation in the standard of WFS, we assume the outputFormats of featureTypes
                # to define the GetFeature operation
                m_t = MimeType.objects.get_or_create(
                    operation=OGCOperationEnum.GET_FEATURE.value,
                    mime_type=xml_helper.try_get_text_from_xml_element(
                        xml_elem=_format
                    )
                )[0]
                format_list.append(m_t)

        # Dataset (ISO) Metadata parsing
        self._parse_dataset_md(f_t, feature_type)

        # Feature type elements
        # Feature type namespaces
        elements_namespaces = self._get_featuretype_elements_namespaces(f_t, service_type_version, external_auth=external_auth)

        self.feature_type_list[f_t.metadata.identifier] = {
            "feature_type": f_t,
            "srs_list": srs_list,
            "format_list": format_list,
            "element_list": elements_namespaces.get("element_list", []),
            "ns_list": elements_namespaces.get("ns_list", []),
            "dataset_md_list": f_t.dataset_md_list,
        }

    @abstractmethod
    def get_feature_type_metadata(self, xml_obj, async_task: Task = None, external_auth: ExternalAuthentication = None):
        """ Parse the capabilities document <FeatureTypeList> metadata into the self object

        This abstract implementation follows the wfs specification for version 1.1.0

        Args:
            xml_obj: A minidom object which holds the xml content
            async_task: The async task object
        Returns:
             Nothing
        """
        feature_type_list = xml_helper.try_get_element_from_xml(
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("FeatureType"),
            xml_elem=xml_obj
        )
        service_type_version = xml_helper.try_get_attribute_from_xml_element(
            xml_elem=xml_obj,
            attribute="version",
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("WFS_Capabilities")
        )
        epsg_api = EpsgApi()
        # Feature types
        thread_list = []

        len_ft_list = len(feature_type_list)
        if len_ft_list == 0:
            # do not divide by zero!
            len_ft_list = 1

        # calculate the step size for an async call
        # 55 is the diff from the last process update (10) to the next static one (65)
        step_size = float(PROGRESS_STATUS_AFTER_PARSING / len_ft_list)

        # decide whether to use multithreading or iterative approach
        if len_ft_list > MULTITHREADING_THRESHOLD:
            for xml_feature_type in feature_type_list:
                thread_list.append(threading.Thread(target=self._get_feature_type_metadata, args=(xml_feature_type, epsg_api, service_type_version, async_task, step_size, external_auth)))
            execute_threads(thread_list)
        else:
            for xml_feature_type in feature_type_list:
                self._get_feature_type_metadata(xml_feature_type, epsg_api, service_type_version, async_task, step_size, external_auth)


    @abstractmethod
    def _get_featuretype_elements_namespaces(self, feature_type, service_type_version: str, external_auth: ExternalAuthentication):
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
            descr_feat_root = xml_helper.get_feature_type_elements_xml(
                title=feature_type.metadata.identifier,
                service_type="wfs",
                service_type_version=service_type_version,
                uri=self.describe_feature_type_uri.get("get", ""),
                external_auth=external_auth,
            )
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

    def get_single_feature_type_metadata(self, identifier, external_auth: ExternalAuthentication):
        if self.service_capabilities_xml is None:
            # load xml, might have been forgotten
            self.get_capabilities()

        xml_obj = xml_helper.parse_xml(xml=self.service_capabilities_xml)
        feature_type = xml_helper.try_get_element_from_xml(
            xml_elem=xml_obj,
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("FeatureType") +
                 "/" + GENERIC_NAMESPACE_TEMPLATE.format("Name") + "[text()='{}']".format(identifier) +
                 "/" + "parent::" + GENERIC_NAMESPACE_TEMPLATE.format("FeatureType")
        )
        service_type_version = xml_helper.try_get_attribute_from_xml_element(
            xml_elem=xml_obj,
            attribute="version",
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("WFS_Capabilities")
        )
        if len(feature_type) > 0:
            feature_type = feature_type[0]
            epsg_api = EpsgApi()
            self._get_feature_type_metadata(feature_type, epsg_api, service_type_version, external_auth=external_auth)

    @abstractmethod
    def create_service_model_instance(self, user: MrMapUser, register_group, register_for_organization, external_auth: ExternalAuthentication, is_update_candidate_for: Service):
        """ Map all data from the WebFeatureService classes to their database models

        Args:
            user (MrMapUser): The user which performs the action
            register_group (Group): The group which is used to register this service
            register_for_organization (Organization): The organization for which this service is being registered
            external_auth (ExternalAuthentication): The external authentication object
        Returns:
             service (Service): Service instance, contains all information, ready for persisting!
        """

        orga_published_for = register_for_organization
        group = register_group

        # Contact
        contact = self._create_contact_organization_record()

        # Metadata
        md = self._create_metadata_record(contact, group)

        # Process external authentication data, if provided
        self._process_external_authentication(md, external_auth)

        # Service
        service = self._create_service_record(group, orga_published_for, md, is_update_candidate_for)

        # Additional (Keywords, linked metadata, MimeTypes, ...)
        self._create_additional_records(service, md)

        # feature types
        self._create_feature_types(service, group, contact)

        return service

    def _create_contact_organization_record(self):
        """ Creates a contact record from the OGCWebFeatureService object

        Returns:
             contact (Contact): A persisted contact object
        """
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
        return contact

    def _create_metadata_record(self, contact: Organization, group: MrMapGroup):
        """ Creates a Metadata record from the OGCWebFeatureService object

        Args:
            contact (Contact): The contact object
            group (MrMapGroup): The owner/creator group
        Returns:
             md (Metadata): The persisted metadata record
        """
        md = Metadata()
        md_type = MetadataEnum.SERVICE.value
        md.metadata_type = md_type
        md.title = self.service_identification_title
        if self.service_file_identifier is None:
            self.service_file_identifier = uuid.uuid4()
        md.identifier = self.service_file_identifier
        md.abstract = self.service_identification_abstract
        md.online_resource = self.service_provider_onlineresource_linkage

        md.contact = contact
        md.authority_url = self.service_provider_url
        md.access_constraints = self.service_identification_accessconstraints
        md.fees = self.service_identification_fees
        md.created_by = group
        md.capabilities_original_uri = self.service_connect_url
        if self.service_bounding_box is not None:
            md.bounding_geometry = self.service_bounding_box

        # Save metadata record so we can use M2M or id of record later
        md.save()

        return md

    def _create_service_record(self, group: MrMapGroup, orga_published_for: Organization, md: Metadata, is_update_candidate_for: Service):
        """ Creates a Service object from the OGCWebFeatureService object

        Args:
            group (MrMapGroup): The owner/creator group
            orga_published_for (Organization): The organization for which the service is published
            orga_publisher (Organization): THe organization that publishes
            md (Metadata): The describing metadata
        Returns:
             service (Service): The persisted service object
        """
        service = Service()
        service_type = ServiceType.objects.get_or_create(
            name=self.service_type.value,
            version=self.service_version.value
        )[0]
        service.service_type = service_type
        service.created_by = group
        service.published_for = orga_published_for

        service.availability = 0.0
        service.is_available = False
        service.is_root = True
        md.service = service
        service.is_update_candidate_for = is_update_candidate_for

        # Save record to enable M2M relations
        service.save()

        operation_urls = [
            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_CAPABILITIES.value,
                url=self.get_capabilities_uri.get("get", None),
                method="Get"
            )[0],
            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_CAPABILITIES.value,
                url=self.get_capabilities_uri.get("post", None),
                method="Post"
            )[0],

            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.DESCRIBE_FEATURE_TYPE.value,
                url=self.describe_feature_type_uri.get("get", None),
                method="Get"
            )[0],
            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.DESCRIBE_FEATURE_TYPE.value,
                url=self.describe_feature_type_uri.get("post", None),
                method="Post"
            )[0],

            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_FEATURE.value,
                url=self.get_feature_uri.get("get", None),
                method="Get"
            )[0],
            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_FEATURE.value,
                url=self.get_feature_uri.get("post", None),
                method="Post"
            )[0],

            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.TRANSACTION.value,
                url=self.transaction_uri.get("get", None),
                method="Get"
            )[0],
            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.TRANSACTION.value,
                url=self.transaction_uri.get("post", None),
                method="Post"
            )[0],

            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_PROPERTY_VALUE.value,
                url=self.get_property_value_uri.get("get", None),
                method="Get"
            )[0],
            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_PROPERTY_VALUE.value,
                url=self.get_property_value_uri.get("post", None),
                method="Post"
            )[0],

            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.LIST_STORED_QUERIES.value,
                url=self.list_stored_queries_uri.get("get", None),
                method="Get"
            )[0],
            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.LIST_STORED_QUERIES.value,
                url=self.list_stored_queries_uri.get("post", None),
                method="Post"
            )[0],

            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.DESCRIBE_STORED_QUERIES.value,
                url=self.describe_stored_queries_uri.get("get", None),
                method="Get"
            )[0],
            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.DESCRIBE_STORED_QUERIES.value,
                url=self.describe_stored_queries_uri.get("post", None),
                method="Post"
            )[0],

            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_GML_OBJECT.value,
                url=self.get_gml_object_uri.get("get", None),
                method="Get"
            )[0],
            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_GML_OBJECT.value,
                url=self.get_gml_object_uri.get("post", None),
                method="Post"
            )[0],

        ]
        service.operation_urls.add(*operation_urls)

        # Persist capabilities document
        service.persist_original_capabilities_doc(self.service_capabilities_xml)

        return service

    def _create_additional_records(self, service: Service, md: Metadata):
        """ Creates additional records like linked service metadata, keywords or MimeTypes/Formats

        Args:
            service (Service): The service record
            md (Metadata): THe metadata record
        Returns:

        """

        # save linked service metadata
        if self.linked_service_metadata is not None:
            service.linked_service_metadata = self.linked_service_metadata.to_db_model(MetadataEnum.SERVICE.value, created_by=md.created_by)
            md_relation = MetadataRelation()
            md_relation.metadata_to = service.linked_service_metadata
            md_relation.origin = ResourceOriginEnum.CAPABILITIES.value
            md_relation.relation_type = MetadataRelationEnum.VISUALIZES.value
            md_relation.save()
            md.related_metadata.add(md_relation)

        # Keywords
        for kw in self.service_identification_keywords:
            if kw is None:
                continue
            keyword = Keyword.objects.get_or_create(keyword=kw)[0]
            md.keywords.add(keyword)

        # MimeTypes
        for mime_type in self.service_mime_type_list:
            md.formats.add(mime_type)

    def _create_feature_types(self, service: Service, group: MrMapGroup, contact: Contact):
        """ Iterates over parsed feature types and creates DB records for each

        Args:
            service (Service):
            group (Service):
            contact (Service):
        Returns:

        """

        for feature_type_key, feature_type_val in self.feature_type_list.items():
            f_t = feature_type_val.get("feature_type")
            f_t.metadata.created_by = group
            f_t.parent_service = service
            f_t.metadata.contact = contact
            f_t.metadata.capabilities_original_uri = self.service_connect_url

            f_t.dataset_md_list = feature_type_val.get("dataset_md_list", [])
            f_t.additional_srs_list = feature_type_val.get("srs_list", [])
            f_t.formats_list = feature_type_val.get("format_list", [])
            f_t.elements_list = feature_type_val.get("element_list", [])
            f_t.namespaces_list = feature_type_val.get("ns_list", [])

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
                dataset_record = dataset_md.to_db_model(created_by=group)
                dataset_record.save()
                md_relation = MetadataRelation()
                md_relation.metadata_to = dataset_record
                origin = ResourceOriginEnum.CAPABILITIES.value
                md_relation.origin = origin
                md_relation.relation_type = MetadataRelationEnum.DESCRIBED_BY.value
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
                md.formats.add(_format)

            # elements
            for _element in f_t.elements_list:
                f_t.elements.add(_element)

            # namespaces
            for ns in f_t.namespaces_list:
                f_t.namespaces.add(ns)


    ### DATASET METADATA ###
    def _parse_dataset_md(self, feature_type, xml_feature_type_obj: _Element):
        """ Parses the dataset metadata from the element.

        Creates new ISOMetadata elements, if parsing is successful.

        Args:
            feature_type: The feature type object
            xml_feature_type_obj: The xml feature type object, that holds the dataset link information
        Returns:

        """
        # check for possible dataset metadata
        if self.has_dataset_metadata(xml_feature_type_obj):
            iso_metadata_xml_elements = xml_helper.try_get_element_from_xml(
                xml_elem=xml_feature_type_obj,
                elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("MetadataURL")
            )
            for iso_xml in iso_metadata_xml_elements:
                # Depending on the service version, the uris can live inside a href attribute or inside the xml element as text
                iso_uri = xml_helper.try_get_text_from_xml_element(xml_elem=iso_xml) or xml_helper.get_href_attribute(iso_xml)
                if iso_uri is None:
                    continue
                try:
                    iso_metadata = ISOMetadata(uri=iso_uri, origin="capabilities")
                except Exception as e:
                    # there are iso metadatas that have been filled wrongly -> if so we will drop them
                    continue
                feature_type.dataset_md_list.append(iso_metadata)

    def get_feature_type_by_identifier(self, identifier: str = None, external_auth: ExternalAuthentication = None):
        """ Extract a single feature type by its identifier and parse it into a FeatureType object

        Args:
            identifier (str): Identifier for the requested FeatureType
        Returns:
            a parsed FeatureType object
        """
        # feature types are stored in the .feature_type_list attribute
        self.get_single_feature_type_metadata(identifier, external_auth=external_auth)
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
    def __init__(self, service_connect_url, external_auth: ExternalAuthentication):
        super().__init__(
            service_connect_url=service_connect_url,
            service_version=OGCServiceVersionEnum.V_1_0_0,
            service_type=OGCServiceEnum.WFS,
            external_auth=external_auth
        )
        XML_NAMESPACES["schemaLocation"] = "http://schemas.opengis.net/wfs/1.0.0/WFS-capabilities.xsd"
        XML_NAMESPACES["xsi"] = "http://www.w3.org/2001/XMLSchema-instance"
        XML_NAMESPACES["lvermgeo"] = "http://www.lvermgeo.rlp.de/lvermgeo"
        XML_NAMESPACES["default"] = XML_NAMESPACES.get("wfs")

    def get_service_operations_and_formats(self, xml_obj):
        """ Creates table records from <Capability><Request></Request></Capability contents

        Args:
            xml_obj: The xml document object
        Returns:

        """
        cap_request = xml_helper.try_get_single_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("Capability") +
            "/" + GENERIC_NAMESPACE_TEMPLATE.format("Request"),
            xml_obj
        )
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
        service_node = xml_helper.try_get_single_element_from_xml(
            elem="/" + GENERIC_NAMESPACE_TEMPLATE.format("WFS_Capabilities") +
                 "/" + GENERIC_NAMESPACE_TEMPLATE.format("Service"),
            xml_elem=xml_obj
        )
        # TITLE
        title_node = xml_helper.try_get_text_from_xml_element(elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("Title"), xml_elem=service_node)
        self.service_identification_title = title_node

        # ABSTRACT
        self.service_identification_abstract = xml_helper.try_get_text_from_xml_element(
            elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("Abstract"),
            xml_elem=service_node
        )

        # FEES
        self.service_identification_fees = xml_helper.try_get_text_from_xml_element(
            elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("Fees"),
            xml_elem=service_node
        )

        # ACCESS CONSTRAINTS
        self.service_identification_accessconstraints = xml_helper.try_get_text_from_xml_element(
            elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("AccessConstraints"),
            xml_elem=service_node
        )

        # KEYWORDS
        keywords_str = xml_helper.try_get_text_from_xml_element(
            elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("Keywords"),
            xml_elem=service_node
        )
        self.service_identification_keywords = service_helper.resolve_keywords_array_string(keywords_str)
        del keywords_str

        # ONLINE RESOURCE
        self.service_provider_onlineresource_linkage = xml_helper.try_get_text_from_xml_element(
            elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource"),
            xml_elem=service_node
        )

        del service_node

    def get_capability_metadata(self, xml_obj):
        """ Parse the wfs <Capability> metadata into the self object

        Args:
            xml_obj: A minidom object which holds the xml content
        Returns:
             Nothing
        """
        cap_node = xml_helper.try_get_single_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("Capability"),
            xml_elem=xml_obj
        )

        get_cap = OGCOperationEnum.GET_CAPABILITIES.value
        descr_feat = OGCOperationEnum.DESCRIBE_FEATURE_TYPE.value
        get_feat = OGCOperationEnum.GET_FEATURE.value
        trans = OGCOperationEnum.TRANSACTION.value
        lock_feat = OGCOperationEnum.LOCK_FEATURE.value
        get_feat_lock = OGCOperationEnum.GET_FEATURE_WITH_LOCK.value

        actions = [
            get_cap,
            descr_feat,
            get_feat,
            trans,
            lock_feat,
            get_feat_lock
        ]
        get = {}
        post = {}
        for action in actions:
            node = xml_helper.try_get_single_element_from_xml(
                ".//" + GENERIC_NAMESPACE_TEMPLATE.format(action),
                cap_node
            )
            if node is None:
                continue
            get[action] = xml_helper.try_get_attribute_from_xml_element(
                elem=".//" + GENERIC_NAMESPACE_TEMPLATE.format("Get"),
                xml_elem=node,
                attribute="onlineResource"
            )
            post[action] = xml_helper.try_get_attribute_from_xml_element(
                elem=".//" + GENERIC_NAMESPACE_TEMPLATE.format("Post"),
                xml_elem=node,
                attribute="onlineResource"
            )
        del cap_node

        self.get_capabilities_uri["get"] = get.get(get_cap, None)
        self.get_capabilities_uri["post"] = post.get(get_cap, None)

        self.describe_feature_type_uri["get"] = get.get(descr_feat, None)
        self.describe_feature_type_uri["post"] = post.get(descr_feat, None)

        self.get_feature_uri["get"] = get.get(get_feat, None)
        self.get_feature_uri["post"] = post.get(get_feat, None)

        self.transaction_uri["get"] = get.get(trans, None)
        self.transaction_uri["post"] = post.get(trans, None)

        self.lock_feature_uri["get"] = get.get(lock_feat, None)
        self.lock_feature_uri["post"] = post.get(lock_feat, None)

        self.get_feature_with_lock_uri["get"] = get.get(get_feat_lock, None)
        self.get_feature_with_lock_uri["post"] = post.get(get_feat_lock, None)

    def get_feature_type_metadata(self, xml_obj, async_task: Task = None, external_auth: ExternalAuthentication = None):
        """ Parse the wfs <Service> metadata into the self object

        Args:
            xml_obj: A minidom object which holds the xml content
            async_task: The asynchronous task object
        Returns:
             Nothing
        """
        service_type_version = xml_helper.try_get_attribute_from_xml_element(
            xml_elem=xml_obj,
            attribute="version",
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("WFS_Capabilities")
        )
        feat_nodes = xml_helper.try_get_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("WFS_Capabilities") +
            "/" + GENERIC_NAMESPACE_TEMPLATE.format("FeatureTypeList") +
            "/" + GENERIC_NAMESPACE_TEMPLATE.format("FeatureType"),
            xml_obj
        )

        step_size = float(PROGRESS_STATUS_AFTER_PARSING / len(feat_nodes))

        for node in feat_nodes:
            feature_type = FeatureType()
            metadata = Metadata()
            feature_type.metadata = metadata
            feature_type.metadata.identifier = xml_helper.try_get_text_from_xml_element(
                elem=".//" + GENERIC_NAMESPACE_TEMPLATE.format("Name"),
                xml_elem=node
            )
            feature_type.metadata.title = xml_helper.try_get_text_from_xml_element(
                elem=".//" + GENERIC_NAMESPACE_TEMPLATE.format("Title"),
                xml_elem=node
            )
            feature_type.metadata.abstract = xml_helper.try_get_text_from_xml_element(
                elem=".//" + GENERIC_NAMESPACE_TEMPLATE.format("Abstract"),
                xml_elem=node
            )
            keywords = service_helper.resolve_keywords_array_string(xml_helper.try_get_text_from_xml_element(
                elem=".//" + GENERIC_NAMESPACE_TEMPLATE.format("Keywords"),
                xml_elem=node
            )
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
                "minx": xml_helper.try_get_attribute_from_xml_element(
                    elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("LatLongBoundingBox"),
                    xml_elem=node,
                    attribute="minx"
                ),
                "miny": xml_helper.try_get_attribute_from_xml_element(
                    elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("LatLongBoundingBox"),
                    xml_elem=node,
                    attribute="miny"
                ),
                "maxx": xml_helper.try_get_attribute_from_xml_element(
                    elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("LatLongBoundingBox"),
                    xml_elem=node,
                    attribute="maxx"
                ),
                "maxy": xml_helper.try_get_attribute_from_xml_element(
                    elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("LatLongBoundingBox"),
                    xml_elem=node,
                    attribute="maxy"
                ),
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
            srs_list = xml_helper.try_get_element_from_xml("./" + GENERIC_NAMESPACE_TEMPLATE.format("SRS"), node)
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

            # lat lon bounding box
            bbox = {
                "minx": xml_helper.try_get_attribute_from_xml_element(
                    elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("LatLongBoundingBox"), xml_elem=node,
                    attribute="minx"),
                "miny": xml_helper.try_get_attribute_from_xml_element(
                    elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("LatLongBoundingBox"), xml_elem=node,
                    attribute="miny"),
                "maxx": xml_helper.try_get_attribute_from_xml_element(
                    elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("LatLongBoundingBox"), xml_elem=node,
                    attribute="maxx"),
                "maxy": xml_helper.try_get_attribute_from_xml_element(
                    elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("LatLongBoundingBox"), xml_elem=node,
                    attribute="maxy"),
            }
            # create polygon element from simple bbox dict
            geom = GEOSGeometry(Polygon.from_bbox([
                float(bbox["minx"]), float(bbox["miny"]), float(bbox["maxx"]), float(bbox["maxy"])
            ]), int(feature_type.default_srs.code))
            geom.transform(DEFAULT_SRS)
            feature_type.bbox_lat_lon = geom

            # Feature type elements
            # Feature type namespaces
            elements_namespaces = self._get_featuretype_elements_namespaces(feature_type, service_type_version, external_auth)

            # check for possible ISO metadata
            self._parse_dataset_md(feature_type, node)

            # put the feature types objects with keywords and reference systems into the dict for the persisting process
            self.feature_type_list[feature_type.metadata.identifier] = {
                "feature_type": feature_type,
                "keyword_list": kw_list,
                "srs_list": srs_model_list,
                "format_list": [],
                "element_list": elements_namespaces["element_list"],
                "ns_list": elements_namespaces["ns_list"],
                "dataset_md_list": feature_type.dataset_md_list,
            }

            # update async task if this is called async
            if async_task is not None and step_size is not None:
                task_helper.update_progress_by_step(async_task, step_size)
                task_helper.update_service_description(async_task, None, "Parsing {}".format(metadata.title))


class OGCWebFeatureService_1_1_0(OGCWebFeatureService):
    """
    Uses base implementation from OGCWebFeatureService class
    """
    def __init__(self, service_connect_url, external_auth: ExternalAuthentication):
        super().__init__(
            service_connect_url=service_connect_url,
            service_version=OGCServiceVersionEnum.V_1_1_0,
            service_type=OGCServiceEnum.WFS,
            external_auth=external_auth
        )
        XML_NAMESPACES["schemaLocation"] = "http://schemas.opengis.net/wfs/1.1.0/wfs.xsd"
        XML_NAMESPACES["wfs"] = "http://www.opengis.net/wfs"
        XML_NAMESPACES["ows"] = "http://www.opengis.net/ows"
        XML_NAMESPACES["fes"] = "http://www.opengis.net/fes"
        XML_NAMESPACES["default"] = XML_NAMESPACES["wfs"]

    def get_service_operations_and_formats(self, xml_obj):
        """ Creates table records from <Capability><Request></Request></Capability contents

        Args:
            xml_obj: The xml document object
        Returns:

        """
        operations = xml_helper.try_get_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("OperationsMetadata") +
            "/" + GENERIC_NAMESPACE_TEMPLATE.format("Operation"), xml_obj
        )
        for operation in operations:
            name = xml_helper.try_get_attribute_from_xml_element(operation, "name")
            RequestOperation.objects.get_or_create(
                operation_name=name,
            )

class OGCWebFeatureService_2_0_0(OGCWebFeatureService):
    """
    Uses base implementation from OGCWebFeatureService class
    """
    def __init__(self, service_connect_url, external_auth: ExternalAuthentication):
        super().__init__(
            service_connect_url=service_connect_url,
            service_version=OGCServiceVersionEnum.V_2_0_0,
            service_type=OGCServiceEnum.WFS,
            external_auth=external_auth
        )
        XML_NAMESPACES["schemaLocation"] = "http://schemas.opengis.net/wfs/2.0/wfs.xsd"
        XML_NAMESPACES["wfs"] = "http://www.opengis.net/wfs/2.0"
        XML_NAMESPACES["ows"] = "http://www.opengis.net/ows/1.1"
        XML_NAMESPACES["fes"] = "http://www.opengis.net/fes/2.0"
        XML_NAMESPACES["default"] = XML_NAMESPACES["wfs"]

    def get_service_operations_and_formats(self, xml_obj):
        """ Creates table records from <Capability><Request></Request></Capability contents

        Args:
            xml_obj: The xml document object
        Returns:

        """
        operations = xml_helper.try_get_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("OperationsMetadata") +
            "/" + GENERIC_NAMESPACE_TEMPLATE.format("Operation"), xml_obj
        )
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
        feature_type_list = xml_helper.try_get_element_from_xml(
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("FeatureType"),
            xml_elem=xml_obj
        )
        for feature_type_xml_elem in feature_type_list:
            name = xml_helper.try_get_text_from_xml_element(
                xml_elem=feature_type_xml_elem,
                elem=".//" + GENERIC_NAMESPACE_TEMPLATE.format("Name")
            )
            try:
                f_t = self.feature_type_list.get(name).get("feature_type")
            except AttributeError:
                # if this happens the metadata is broken or not reachable due to bad configuration
                raise BaseException(SERVICE_GENERIC_ERROR)

            # Feature type keywords
            keywords = xml_helper.try_get_element_from_xml(
                xml_elem=feature_type_xml_elem,
                elem=".//" + GENERIC_NAMESPACE_TEMPLATE.format("Keyword")
            )
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
            crs = xml_helper.try_get_text_from_xml_element(
                xml_elem=feature_type_xml_elem,
                elem=".//" + GENERIC_NAMESPACE_TEMPLATE.format("DefaultCRS")
            )
            if crs is not None:
                parts = epsg_api.get_subelements(crs)
                # check if this srs is allowed for us. If not, skip it!
                if parts.get("code") not in ALLOWED_SRS:
                    continue
                crs_default = ReferenceSystem.objects.get_or_create(code=parts.get("code"), prefix=parts.get("prefix"))[0]
                f_t.default_srs = crs_default
            ## additional
            crs = xml_helper.try_get_element_from_xml(
                xml_elem=feature_type_xml_elem,
                elem=".//" + GENERIC_NAMESPACE_TEMPLATE.format("OtherCRS")
            )
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
    def __init__(self, service_connect_url, external_auth: ExternalAuthentication):
        super().__init__(
            service_connect_url=service_connect_url,
            service_version=OGCServiceVersionEnum.V_2_0_2,
            service_type=OGCServiceEnum.WFS,
            external_auth=external_auth
        )
        XML_NAMESPACES["wfs"] = "http://www.opengis.net/wfs/2.0"
        XML_NAMESPACES["ows"] = "http://www.opengis.net/ows/1.1"
        XML_NAMESPACES["fes"] = "http://www.opengis.net/fes/2.0"
        XML_NAMESPACES["default"] = XML_NAMESPACES["wfs"]

    def get_service_operations_and_formats(self, xml_obj):
        """ Creates table records from <Capability><Request></Request></Capability contents

        Args:
            xml_obj: The xml document object
        Returns:

        """
        operations = xml_helper.try_get_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("OperationsMetadata") +
            "/" + GENERIC_NAMESPACE_TEMPLATE.format("Operation"),
            xml_obj
        )
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

        # featuretype keywords are different now
        feature_type_list = xml_helper.try_get_element_from_xml(elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("FeatureType"), xml_elem=xml_obj)
        for feature_type_xml_elem in feature_type_list:
            name = xml_helper.try_get_text_from_xml_element(xml_elem=feature_type_xml_elem, elem=".//" + GENERIC_NAMESPACE_TEMPLATE.format("Name"))
            try:
                f_t = self.feature_type_list.get(name).get("feature_type")
            except AttributeError:
                # if this happens the metadata is broken or not reachable due to bad configuration
                raise BaseException(SERVICE_GENERIC_ERROR)

            # Feature type keywords
            keywords = xml_helper.try_get_element_from_xml(xml_elem=feature_type_xml_elem, elem=".//ows:Keyword")
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
            crs = xml_helper.try_get_text_from_xml_element(xml_elem=feature_type_xml_elem, elem=".//" + GENERIC_NAMESPACE_TEMPLATE.format("DefaultCRS"))
            if crs is not None:
                parts = epsg_api.get_subelements(crs)
                # check if this srs is allowed for us. If not, skip it!
                if parts.get("code") not in ALLOWED_SRS:
                    continue
                crs_default = ReferenceSystem.objects.get_or_create(code=parts.get("code"), prefix=parts.get("prefix"))[0]
                f_t.default_srs = crs_default
            ## additional
            crs = xml_helper.try_get_element_from_xml(xml_elem=feature_type_xml_elem, elem=".//" + GENERIC_NAMESPACE_TEMPLATE.format("OtherCRS"))
            crs_list = []
            for sys in crs:
                parts = epsg_api.get_subelements(sys.text)
                # check if this srs is allowed for us. If not, skip it!
                if parts.get("code") not in ALLOWED_SRS:
                    continue
                srs_other = ReferenceSystem.objects.get_or_create(code=parts.get("code"), prefix=parts.get("prefix"))[0]
                crs_list.append(srs_other)
            self.feature_type_list[name]["srs_list"] = crs_list


