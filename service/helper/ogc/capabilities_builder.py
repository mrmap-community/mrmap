"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 31.07.19

"""
from collections import OrderedDict
from time import time

from django.contrib.gis.gdal import GDALException
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import QuerySet
from lxml.etree import Element, QName

from MrMap.settings import XML_NAMESPACES, GENERIC_NAMESPACE_TEMPLATE
from service.helper import xml_helper
from service.helper.enums import OGCServiceVersionEnum, OGCServiceEnum, OGCOperationEnum, MetadataEnum, DocumentEnum
from service.helper.epsg_api import EpsgApi
from service.models import Metadata, Layer, Document, FeatureType
from service.settings import SERVICE_OPERATION_URI_TEMPLATE, SERVICE_METADATA_URI_TEMPLATE, service_logger


class CapabilityXMLBuilder:
    """

    Creates a xml document, according to the specification of OGC WMS and WFS

    http://schemas.opengis.net/wms/
    http://schemas.opengis.net/wfs/

    """
    def __init__(self, metadata: Metadata, force_version: str = None):
        self.metadata = metadata

        # A single FeatureType is not a service, therefore we can not use the regular metadata.service call.
        if metadata.is_metadata_type(MetadataEnum.SERVICE):
            service = metadata.service
            parent_service = service
        elif metadata.is_metadata_type(MetadataEnum.FEATURETYPE):
            service = FeatureType.objects.get(
                metadata=metadata
            ).parent_service
            parent_service = service
        elif metadata.is_metadata_type(MetadataEnum.LAYER):
            service = metadata.service
            if not service.is_root:
                parent_service = service.parent_service
            else:
                parent_service = service

        self.service = service
        self.parent_service = parent_service

        self.service_type = self.service.service_type.name
        self.service_version = force_version or self.service.service_type.version

        self.namespaces = {
            "sld": XML_NAMESPACES["sld"],
            "xlink": XML_NAMESPACES["xlink"],
            "xsi": XML_NAMESPACES["xsi"],
            "ogc": XML_NAMESPACES["ogc"],
            "inspire_vs": XML_NAMESPACES["inspire_vs"],
            "inspire_common": XML_NAMESPACES["inspire_common"],
            "inspire_dls": XML_NAMESPACES["inspire_dls"],
        }

        self.default_ns = ""
        self.xlink_ns = "{" + XML_NAMESPACES["xlink"] + "}"
        self.xsi_ns = "{" + XML_NAMESPACES["xsi"] + "}"

        self.inspire_vs_ns = "{" + XML_NAMESPACES["inspire_vs"] + "}"
        self.inspire_common_ns = "{" + XML_NAMESPACES["inspire_common"] + "}"
        self.inspire_dls_ns = "{" + XML_NAMESPACES["inspire_dls"] + "}"
        self.inspire_supported_language_code = "ger"
        self.inspire_response_language_code = "ger"
        self.inspire_media_type = "application/vnd.iso.19139+xml"

        self.schema_location = ""

        self.original_doc = None
        try:
            doc = Document.objects.get(
                metadata=parent_service.metadata,
                is_original=True,
                document_type=DocumentEnum.CAPABILITY.value
            )
            self.original_doc = xml_helper.parse_xml(
                doc.content
            )
        except ObjectDoesNotExist:
            # If no document can be found in the databse, we have to fetch the original remote document
            self.original_doc = xml_helper.parse_xml(
                metadata.get_remote_original_capabilities_document(
                    version=force_version
                )
            )

    def generate_xml(self):
        """ Generates the capability xml

        Returns:
             xml (str): The xml document as string
        """
        xml_builder = None

        if self.parent_service.is_service_type(OGCServiceEnum.WMS):

            if self.service_version == OGCServiceVersionEnum.V_1_0_0.value:
                xml_builder = CapabilityWMS100Builder(self.metadata, self.service_version)

            elif self.service_version == OGCServiceVersionEnum.V_1_1_1.value:
                xml_builder = CapabilityWMS111Builder(self.metadata, self.service_version)

            elif self.service_version == OGCServiceVersionEnum.V_1_3_0.value:
                xml_builder = CapabilityWMS130Builder(self.metadata, self.service_version)

            else:
                # If something unknown has been passed as version, we use 1.1.1 as default
                xml_builder = CapabilityWMS111Builder(self.metadata, self.service_version)

        elif self.parent_service.is_service_type(OGCServiceEnum.WFS):

            if self.service_version == OGCServiceVersionEnum.V_1_0_0.value:
                xml_builder = CapabilityWFS100Builder(self.metadata, self.service_version)

            elif self.service_version == OGCServiceVersionEnum.V_1_1_0.value:
                xml_builder = CapabilityWFS110Builder(self.metadata, self.service_version)

            elif self.service_version == OGCServiceVersionEnum.V_2_0_0.value:
                xml_builder = CapabilityWFS200Builder(self.metadata, self.service_version)

            elif self.service_version == OGCServiceVersionEnum.V_2_0_2.value:
                xml_builder = CapabilityWFS202Builder(self.metadata, self.service_version)
            else:
                # If something unknown has been passed as version, we use 2.0.0 as default
                xml_builder = CapabilityWFS200Builder(self.metadata, self.service_version)

        xml = xml_builder._generate_xml()
        return xml

    def _generate_licence_related_constraints(self) -> (str, str):
        """ Generates the string content for fees and access constraints elements based on a given metadata

        Returns:
             fees (str): The fees string
             access_constraints (str): The access constraints string
        """
        md = self.metadata
        fees = md.fees
        access_constraints = md.access_constraints

        licence = md.licence
        if licence is not None:
            appendix = "\n {} ({}), \n {}, \n {}".format(licence.name, licence.identifier, licence.description, licence.description_url)
            fees += appendix
            access_constraints += appendix

        return fees, access_constraints

    def _generate_simple_elements_from_dict(self, upper_elem: Element, contents: dict, ns: str=None):
        """ Generate multiple subelements of a xml object

        Variable `contents` contains key-value pairs of Element tag names and their text content.
        This method creates only simple xml elements, which have a tag name and the text value set.

        Args:
            upper_elem (_Element): The upper xml element
            contents (dict): The content dict
        Returns:
            nothing
        """
        if ns is None:
            ns = self.default_ns

        for key, val in contents.items():
            k = key.format(ns)
            elem = xml_helper.create_subelement(upper_elem, k)
            xml_helper.write_text_to_element(elem, txt=val)

    def _fetch_original_xml(self, upper_elem: Element, element_tag: str):
        """ Paste an original xml element into the given upper_element

        Args:
            upper_elem (Element): The upper xml element
            element_tag (str): The name of the original element
        Returns:

        """
        original_service_elem = xml_helper.try_get_single_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format(element_tag),
            self.original_doc
        )
        if original_service_elem is not None:
            xml_helper.add_subelement(
                upper_elem,
                original_service_elem
            )

    def _generate_vendor_specific_capabilities_xml(self, upper_elem: Element, ns: str=None):
        """ Generate the 'VendorSpecificCapabilities' subelement of a xml service object

        Args:
            upper_elem (_Element): The upper xml element
        Returns:
            nothing
        """
        # VendorSpecificCapabilities
        # Take something from the original xml document (hopefully this is provided!)
        self._fetch_original_xml(upper_elem, "VendorSpecificCapabilities")

        # Check if the content exists
        elem = xml_helper.try_get_single_element_from_xml(
            upper_elem,
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("VendorSpecificCapabilities")
        )
        if elem is None:
            # Nothing was found, we must create our own service metadata!
            elem = xml_helper.create_subelement(
                upper_elem,
                "VendorSpecificCapabilities"
            )
            self._generate_extended_capabilities_xml(elem, ns)

    def _generate_extended_capabilities_xml(self, upper_elem: Element, ns: str = None):
        """ Generate the 'ExtendedCapabilities' subelement of a xml service object

        Args:
            upper_elem (_Element): The upper xml element
        Returns:
            nothing
        """
        if ns is None:
            ns = self.inspire_vs_ns

        elem = xml_helper.create_subelement(
            upper_elem,
            "{}ExtendedCapabilities".format(ns)
        )

        self._generate_extended_capabilities_metadata_url_xml(elem)
        self._generate_extended_capabilities_supported_language_xml(elem)
        self._generate_extended_capabilities_response_language_xml(elem)

    def _generate_extended_capabilities_metadata_url_xml(self, upper_elem: Element):
        """ Generate the 'MetadataUrl' subelement of a xml VendorSpecificCapabilities object

        Args:
            upper_elem (_Element): The upper xml element
        Returns:
            nothing
        """
        metadata_url_elem = xml_helper.create_subelement(
            upper_elem,
            "{}MetadataUrl".format(self.inspire_common_ns),
            attrib={
                "{}type".format(self.xsi_ns): "inspire_common:resourceLocatorType"
            }
        )

        # URL
        url_elem = xml_helper.create_subelement(
            metadata_url_elem,
            "{}URL".format(self.inspire_common_ns)
        )
        xml_helper.write_text_to_element(
            url_elem,
            txt=SERVICE_METADATA_URI_TEMPLATE.format(self.metadata.id)
        )

        # MediaType
        media_type_elem = xml_helper.create_subelement(
            metadata_url_elem,
            "{}MediaType".format(self.inspire_common_ns)
        )
        xml_helper.write_text_to_element(
            media_type_elem,
            txt=self.inspire_media_type
        )

    def _generate_extended_capabilities_supported_language_xml(self, upper_elem: Element):
        """ Generate the 'SupportedLanguages' subelement of a xml VendorSpecificCapabilities object

        Args:
            upper_elem (_Element): The upper xml element
        Returns:
            nothing
        """
        supported_languages_elem = xml_helper.create_subelement(
            upper_elem,
            "{}SupportedLanguages".format(self.inspire_common_ns),
        )

        # DefaultLanguage
        default_lang_elem = xml_helper.create_subelement(
            supported_languages_elem,
            "{}DefaultLanguage".format(self.inspire_common_ns)
        )
        lang_elem = xml_helper.create_subelement(
            default_lang_elem,
            "{}Language".format(self.inspire_common_ns)
        )
        xml_helper.write_text_to_element(
            lang_elem,
            txt=self.inspire_supported_language_code
        )

        # SupportedLanguage
        default_lang_elem = xml_helper.create_subelement(
            supported_languages_elem,
            "{}SupportedLanguage".format(self.inspire_common_ns)
        )
        lang_elem = xml_helper.create_subelement(
            default_lang_elem,
            "{}Language".format(self.inspire_common_ns)
        )
        xml_helper.write_text_to_element(
            lang_elem,
            txt=self.inspire_supported_language_code
        )

    def _generate_extended_capabilities_response_language_xml(self, upper_elem: Element):
        """ Generate the 'ResponseLanguage' subelement of a xml VendorSpecificCapabilities object

        Args:
            upper_elem (_Element): The upper xml element
        Returns:
            nothing
        """
        response_languages_elem = xml_helper.create_subelement(
            upper_elem,
            "{}ResponseLanguage".format(self.inspire_common_ns),
        )
        lang_elem = xml_helper.create_subelement(
            response_languages_elem,
            "{}Language".format(self.inspire_common_ns)
        )
        xml_helper.write_text_to_element(
            lang_elem,
            txt=self.inspire_response_language_code
        )


class CapabilityWMSBuilder(CapabilityXMLBuilder):
    """ Base class for WMS capabilities building

    http://schemas.opengis.net/wms/
    Wraps all basic capabilities generating methods

    """
    def __init__(self, metadata: Metadata, force_version: str = None):
        super().__init__(metadata=metadata, force_version=force_version)
        self.root_layer = Layer.objects.get(
            parent_service=self.parent_service,
            parent_layer=None
        )

    def _generate_xml(self):
        """ Generate an xml capabilities document from the metadata object

        Args:

        Returns:
             nothing
        """
        root = Element(
            '{}WMS_Capabilities'.format(self.default_ns),
            attrib={
                "version": self.service_version,
                "{}schemaLocation".format(self.xsi_ns): self.schema_location,
            },
            nsmap=self.namespaces
        )
        self.xml_doc_obj = root

        start_time = time()
        service = xml_helper.create_subelement(root, "{}Service".format(self.default_ns))
        self._generate_service_xml(service)
        service_logger.debug("Service creation took {} seconds".format((time() - start_time)))

        start_time = time()
        capability = xml_helper.create_subelement(root, "{}Capability".format(self.default_ns))
        self._generate_capability_xml(capability)
        service_logger.debug("Capabilities creation took {} seconds".format(time() - start_time))

        start_time = time()
        xml = xml_helper.xml_to_string(root, pretty_print=False)
        service_logger.debug("Rendering to string took {} seconds".format((time() - start_time)))

        return xml

    def _generate_service_xml(self, service_elem: Element):
        """ Generate the 'Service' subelement of a xml service object

        Args:
            service_elem (_Element): The service xml element
        Returns:
            nothing
        """
        md = self.metadata
        service_md = self.parent_service.metadata

        # Create generic xml starter elements
        contents = OrderedDict({
            "{}Name": service_md.identifier,
            "{}Title": service_md.title,
            "{}Abstract": service_md.abstract,
        })
        self._generate_simple_elements_from_dict(service_elem, contents)

        # KeywordList and keywords
        self._generate_keyword_xml(service_elem, service_md)

        # OnlineResource
        self._generate_online_resource_xml(service_elem, service_md)

        # Fill in the data for <ContactInformation>
        self._generate_service_contact_information_xml(service_elem)

        # Create generic xml end elements
        fees, access_constraints = self._generate_licence_related_constraints()
        contents = OrderedDict({
            "{}Fees": fees,
            "{}AccessConstraints": access_constraints,
        })
        self._generate_simple_elements_from_dict(service_elem, contents)

        # Various
        self._generate_service_version_specific(service_elem, md)

    def _generate_online_resource_xml(self, upper_elem: Element, md: Metadata):
        """ Generate the 'Layer' subelement of a capability xml object

        Args:
            upper_elem (_Element): The upper xml element (service or layer level)
            md (Metadata): The metadata object
        Returns:
            nothing
        """
        xml_helper.create_subelement(
            upper_elem,
            "{}OnlineResource".format(self.default_ns),
            attrib={
                "{}href".format(self.xlink_ns): SERVICE_OPERATION_URI_TEMPLATE.format(md.id)
            }
        )

    def _generate_service_contact_information_xml(self, service_elem):
        """ Generate the 'ContactInformation' subelement of a xml service object

        Args:
            service_elem (_Element): The service xml element
        Returns:
            nothing
        """
        md = self.metadata
        contact = md.contact

        contact_info_elem = xml_helper.create_subelement(
            service_elem,
            "{}ContactInformation".format(self.default_ns)
        )

        contents = OrderedDict({
            "{}ContactPersonPrimary": "",
            "{}ContactAddress": "",
            "{}ContactVoiceTelephone": contact.phone,
            "{}ContactFacsimileTelephone": contact.facsimile,
            "{}ContactElectronicMailAddress": contact.email,
        })

        self._generate_simple_elements_from_dict(contact_info_elem, contents)

        # Get <ContactPersonPrimary> element to fill in the data
        contact_person_primary_elem = xml_helper.try_get_single_element_from_xml(
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("ContactPersonPrimary"),
            contact_info_elem
        )
        self._generate_service_contact_person_primary_xml(contact_person_primary_elem)

        # Get <ContactAddress> element to fill in the data
        address_elem = xml_helper.try_get_single_element_from_xml(
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("ContactAddress"),
            contact_info_elem
        )
        self._generate_service_contact_address_xml(address_elem)

    def _generate_service_contact_person_primary_xml(self, contact_person_primary_elem: Element):
        """ Generate the 'ContactPersonPrimary' subelement of a xml service object

        Args:
            contact_person_primary_elem (_Element): The <ContactPersonPrimary> xml element
        Returns:
            nothing
        """
        md = self.metadata
        contact = md.contact

        contents = OrderedDict({
            "{}ContactPerson": contact.person_name,
            "{}ContactPosition": "",
        })
        self._generate_simple_elements_from_dict(contact_person_primary_elem, contents)

    def _generate_service_contact_address_xml(self, address_elem: Element):
        """ Generate the 'ContactAddress' subelement of a xml service object

        Args:
            address_elem (_Element): The address xml element
        Returns:
            nothing
        """
        md = self.metadata
        contact = md.contact

        contents = {
            "{}AddressType": contact.address_type,
            "{}Address": contact.address,
            "{}City": contact.city,
            "{}StateOrProvince": contact.state_or_province,
            "{}PostCode": contact.postal_code,
            "{}Country": contact.country,
        }
        self._generate_simple_elements_from_dict(address_elem, contents)

    def _generate_capability_xml(self, capability_elem: Element):
        """ Generate the 'Capability' subelement of a xml object

        Args:
            capability_elem (_Element): The capability xml element
        Returns:
            nothing
        """
        # Layers are not included in this contents dict, since they will be appended separately at the end
        contents = OrderedDict({
            "{}Request": "",
            "{}UserDefinedSymbolization": "",
        })
        self._generate_simple_elements_from_dict(capability_elem, contents)

        request_elem = xml_helper.try_get_single_element_from_xml(
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("Request"),
            capability_elem
        )

        self._generate_capability_request_xml(request_elem)

        self._generate_capability_exception_xml(capability_elem)

        layer_md = self.metadata
        if self.metadata.is_metadata_type(MetadataEnum.SERVICE):
            layer_md = self.root_layer.metadata

        self._generate_capability_layer_xml(capability_elem, layer_md)

        self._generate_vendor_specific_capabilities_xml(capability_elem, self.inspire_vs_ns)

    def _generate_capability_exception_xml(self, capability_elem: Element):
        """ Generate the 'Exception' subelement of a xml capability object

        Args:
            capability_elem (_Element): The request xml element
        Returns:
            nothing
        """
        # Since this is not a very important information, we do not parse the Exception information during registration.
        # Therefore we do a little hack: Just copy the element from the `original_capability_document` of the related
        # metadata document object.
        try:
            original_doc = Document.objects.get(
                metadata=self.service.metadata,
                document_type=DocumentEnum.CAPABILITY.value,
                is_original=True,
            ).content
            if original_doc is None:
                original_doc = Document.objects.get(
                    metadata=self.service.parent_service.metadata,
                    document_type=DocumentEnum.CAPABILITY.value,
                    is_original=True,
                ).content
        except ObjectDoesNotExist as e:
            return
        original_doc = xml_helper.parse_xml(original_doc)
        original_exception_elem = xml_helper.try_get_single_element_from_xml(
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("Capability")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("Exception"),
            original_doc
        )
        if original_exception_elem is not None:
            xml_helper.add_subelement(capability_elem, original_exception_elem)

    def _generate_capability_request_xml(self, request_elem: Element):
        """ Generate the 'Request' subelement of a xml capability object

        Args:
            request_elem (_Element): The request xml element
        Returns:
            nothing
        """
        md = self.metadata
        service = md.service

        contents = OrderedDict({
            "{}GetCapabilities": "",
            "{}GetMap": "",
            "{}GetFeatureInfo": "",
        })

        operation_urls = service.operation_urls.all()
        additional_contents = OrderedDict({
            OGCOperationEnum.DESCRIBE_LAYER.value: {
                "get": getattr(operation_urls.filter(operation=OGCOperationEnum.DESCRIBE_LAYER.value, method="Get").first(), "url", None),
                "post": getattr(operation_urls.filter(operation=OGCOperationEnum.DESCRIBE_LAYER.value, method="Post").first(), "url", None),
            },
            OGCOperationEnum.GET_LEGEND_GRAPHIC.value: {
                "get": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_LEGEND_GRAPHIC.value, method="Get").first(), "url", None),
                "post": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_LEGEND_GRAPHIC.value, method="Post").first(), "url", None),
            },
            OGCOperationEnum.GET_STYLES.value: {
                "get": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_STYLES.value, method="Get").first(), "url", None),
                "post": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_STYLES.value, method="Post").first(), "url", None),
            },
            OGCOperationEnum.PUT_STYLES.value: {
                "get": getattr(operation_urls.filter(operation=OGCOperationEnum.PUT_STYLES.value, method="Get").first(), "url", None),
                "post": getattr(operation_urls.filter(operation=OGCOperationEnum.PUT_STYLES.value, method="Post").first(), "url", None),
            },
        })

        # Put additional contents (if they are valid) in the regular contents
        for key, val in additional_contents.items():
            post_uri = val.get("post", "")
            get_uri = val.get("get", "")
            if post_uri is not None or get_uri is not None:
                contents.update({"{}" + key: ""})

        # Create xml elements
        service_mime_types = service.metadata.get_formats()
        for key, val in contents.items():
            k = key.format(self.default_ns)
            elem = xml_helper.create_subelement(request_elem, k)
            self._generate_capability_operation_xml(elem, service_mime_types)

    def _generate_capability_operation_xml(self, operation_elem: Element, service_mime_types: QuerySet):
        """ Generate the various operation subelements of a xml capability object

        Args:
            operation_elem (_Element): The operation xml element
            service_mime_types (QuerySet): Queryset containing all mime_types of the service
        Returns:
            nothing
        """
        md = self.metadata
        service = md.service
        tag = QName(operation_elem).localname

        operation_urls = service.operation_urls.all()
        operations = OrderedDict({
            OGCOperationEnum.GET_CAPABILITIES.value: {
                "get": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_CAPABILITIES.value, method="Get").first(), "url", None),
                "post": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_CAPABILITIES.value, method="Post").first(), "url", None),
            },
            OGCOperationEnum.GET_MAP.value: {
                "get": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_MAP.value, method="Get").first(), "url", None),
                "post": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_MAP.value, method="Post").first(), "url", None),
            },
            OGCOperationEnum.GET_FEATURE_INFO.value: {
                "get": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_FEATURE_INFO.value, method="Get").first(), "url", None),
                "post": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_FEATURE_INFO.value, method="Post").first(), "url", None),
            },
            OGCOperationEnum.DESCRIBE_LAYER.value: {
                "get": getattr(operation_urls.filter(operation=OGCOperationEnum.DESCRIBE_LAYER.value, method="Get").first(), "url", None),
                "post": getattr(operation_urls.filter(operation=OGCOperationEnum.DESCRIBE_LAYER.value, method="Post").first(), "url", None),
            },
            OGCOperationEnum.GET_LEGEND_GRAPHIC.value: {
                "get": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_LEGEND_GRAPHIC.value, method="Get").first(), "url", None),
                "post": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_LEGEND_GRAPHIC.value, method="Post").first(), "url", None),
            },
            OGCOperationEnum.GET_STYLES.value: {
                "get": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_STYLES.value, method="Get").first(), "url", None),
                "post": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_STYLES.value, method="Post").first(), "url", None),
            },
            OGCOperationEnum.PUT_STYLES.value: {
                "get": getattr(operation_urls.filter(operation=OGCOperationEnum.PUT_STYLES.value, method="Get").first(), "url", None),
                "post": getattr(operation_urls.filter(operation=OGCOperationEnum.PUT_STYLES.value, method="Post").first(), "url", None),
            },
        })

        uris = operations.get(tag, {"get": "","post": ""})
        get_uri = uris.get("get", "")
        post_uri = uris.get("post", "")

        if OGCOperationEnum.GET_CAPABILITIES.value in tag:
            # GetCapabilities is always set to our internal systems uri!
            get_uri = SERVICE_OPERATION_URI_TEMPLATE.format(md.id)
            post_uri = SERVICE_OPERATION_URI_TEMPLATE.format(md.id)

        # Add all mime types that are supported by this operation
        supported_formats = service_mime_types.filter(
            operation=tag
        )
        for format in supported_formats:
            format_elem = xml_helper.create_subelement(operation_elem, "{}Format".format(self.default_ns))
            xml_helper.write_text_to_element(format_elem, txt=format.mime_type)

        # Add <DCPType> contents
        dcp_elem = xml_helper.create_subelement(operation_elem, "{}DCPType".format(self.default_ns))
        http_elem = xml_helper.create_subelement(dcp_elem, "{}HTTP".format(self.default_ns))
        get_elem = xml_helper.create_subelement(http_elem, "{}Get".format(self.default_ns))
        post_elem = xml_helper.create_subelement(http_elem, "{}Post".format(self.default_ns))
        if get_elem is not None and get_uri is not None:
            xml_helper.create_subelement(
                get_elem,
                "{}OnlineResource",
                attrib={
                    "{}href".format(self.xlink_ns): get_uri
                }
            )
        if post_elem is not None and post_uri is not None:
            xml_helper.create_subelement(
                post_elem,
                "{}OnlineResource",
                attrib={
                    "{}href".format(self.xlink_ns): post_uri
                }
            )

    def _generate_capability_layer_xml(self, layer_elem: Element, md: Metadata):
        """ Generate the 'Layer' subelement of a capability xml object

        Args:
            layer_elem (_Element): The layer xml element
        Returns:
            nothing
        """
        layer = Layer.objects.get(
            metadata=md
        )
        md = layer.metadata
        layer_elem = xml_helper.create_subelement(
            layer_elem,
            "{}Layer".format(self.default_ns),
            attrib={
                "queryable": str(int(layer.is_queryable)),
                "cascaded": str(int(layer.is_cascaded)),
                "opaque": str(int(layer.is_opaque)),
                "noSubsets": str(int(False)),  # ToDo: Implement this in registration!
                "fixedWith": str(int(False)),  # ToDo: Implement this in registration!
                "fixedHeight": str(int(False)),  # ToDo: Implement this in registration!
            }
        )

        if layer.identifier is not None:
            elem = xml_helper.create_subelement(layer_elem, "{}Name".format(self.default_ns))
            xml_helper.write_text_to_element(elem, txt=layer.identifier)

        elem = xml_helper.create_subelement(layer_elem, "{}Title".format(self.default_ns))
        xml_helper.write_text_to_element(elem, txt=md.title)

        elem = xml_helper.create_subelement(layer_elem, "{}Abstract".format(self.default_ns))
        xml_helper.write_text_to_element(elem, txt=md.abstract)

        # KeywordList
        self._generate_keyword_xml(layer_elem, layer.metadata)

        # SRS|CRS
        self._generate_capability_layer_srs_xml(layer_elem, layer)

        # Bounding Box
        self._generate_capability_layer_bounding_box_xml(layer_elem, layer)

        # Dimension
        self._generate_capability_layer_dimension_xml(layer_elem, layer)

        # Attribution
        elem = xml_helper.create_subelement(layer_elem, "{}Attribution".format(self.default_ns))
        xml_helper.write_text_to_element(elem, txt="")  # We do not provide this. Leave it empty

        # AuthorityURL
        elem = xml_helper.create_subelement(layer_elem, "{}AuthorityURL".format(self.default_ns))
        xml_helper.write_text_to_element(elem, txt="")  # We do not provide this. Leave it empty

        # Identifier
        elem = xml_helper.create_subelement(layer_elem, "{}Identifier".format(self.default_ns))
        xml_helper.write_text_to_element(elem, txt="")  # We do not provide this. Leave it empty

        # MetadataURL
        self._generate_capability_layer_metadata_url_xml(layer_elem, layer)

        # DataURL
        elem = xml_helper.create_subelement(layer_elem, "{}DataURL".format(self.default_ns))
        xml_helper.write_text_to_element(elem, txt="")  # We do not provide this. Leave it empty

        # FeatureListURL
        elem = xml_helper.create_subelement(layer_elem, "{}FeatureListURL".format(self.default_ns))
        xml_helper.write_text_to_element(elem, txt="")

        # Style
        self._generate_capability_layer_style_xml(layer_elem, layer.get_style())

        # Various
        self._generate_capability_version_specific(layer_elem, layer)

        # Recall the function with the children as input
        layer_children = layer.get_children()
        for layer_child in layer_children:
            self._generate_capability_layer_xml(layer_elem, layer_child.metadata)

    def _generate_keyword_xml(self, upper_elem, md: Metadata):
        """ Generate the 'KeywordList' subelement of a layer xml object and it's subelements

        Args:
            upper_elem (_Element): The upper xml element (service or layer level)

        Returns:
            nothing
        """
        keywords = md.keywords.all()
        if keywords.count() > 0:
            elem = xml_helper.create_subelement(upper_elem, "{}KeywordList".format(self.default_ns))
            for kw in keywords:
                kw_element = xml_helper.create_subelement(elem, "{}Keyword".format(self.default_ns))
                xml_helper.write_text_to_element(kw_element, txt=kw.keyword)

    def _generate_capability_layer_srs_xml(self, layer_elem, layer: Layer):
        """ Generate the 'SRS|CRS' subelement of a layer xml object

        Args:
            layer_elem (_Element): The layer xml element
        Returns:
            nothing
        """
        reference_systems = layer.get_inherited_reference_systems()
        for crs in reference_systems:
            crs_element = xml_helper.create_subelement(layer_elem, "{}SRS".format(self.default_ns))
            xml_helper.write_text_to_element(crs_element, txt="{}{}".format(crs.prefix, crs.code))

    def _generate_capability_layer_bounding_box_xml(self, layer_elem, layer: Layer):
        """ Generate the 'LatLonBoundingBox' subelement of a layer xml object

        Args:
            layer_elem (_Element): The layer xml element
        Returns:
            nothing
        """
        md = layer.metadata
        reference_systems = layer.get_inherited_reference_systems()

        # Get bounding geometry object
        bounding_geometry = md.bounding_geometry
        bbox = md.bounding_geometry.extent

        # Prevent a situation where the bbox would be 0, by taking the parent service bbox.
        # We must(!) take the parent service root layer bounding geometry, since this information is the most reliable
        # if this service is compared with another copy of itself!
        if bbox == (0.0, 0.0, 0.0, 0.0):
            bounding_geometry = layer.get_inherited_bounding_geometry()
            bbox = bounding_geometry.extent

        # Make sure EPSG:4326 is used for this element!
        if bounding_geometry.srid != 4326:
            bounding_geometry.transform(4326)
            bbox = bounding_geometry.extent

        # LatLonBoundingBox (default is EPSG:4326)
        bbox_content = OrderedDict({
            "{}minx": str(bbox[0]),
            "{}miny": str(bbox[2]),
            "{}maxx": str(bbox[1]),
            "{}maxy": str(bbox[3]),
        })
        xml_helper.create_subelement(
            layer_elem,
            "{}LatLonBoundingBox".format(self.default_ns),
            attrib=bbox_content
        )

        # wms:BoundingBox
        # We must provide appropriate bounding boxes for all supported reference systems, since we can not be sure the
        # client may transform a bounding box by itself.
        epsg_handler = EpsgApi()
        for reference_system in reference_systems:
            try:
                bounding_geometry.transform(reference_system.code)
                bbox = list(bounding_geometry.extent)

                switch_axis = epsg_handler.check_switch_axis_order(self.service_type, self.service_version, reference_system.code)
                if switch_axis:
                    for i in range(0, len(bbox), 2):
                        tmp = bbox[i]
                        bbox[i] = bbox[i+1]
                        bbox[i+1] = tmp
            except GDALException:
                # Some srs can not be transformed, like EPSG:31467
                bbox = list(bounding_geometry.extent)

            xml_helper.create_subelement(
                layer_elem,
                "{}BoundingBox".format(self.default_ns),
                attrib=OrderedDict({
                    "SRS": "EPSG:{}".format(str(bounding_geometry.srid)),
                    "minx": str(bbox[0]),
                    "miny": str(bbox[1]),
                    "maxx": str(bbox[2]),
                    "maxy": str(bbox[3]),
                })
            )

    def _generate_capability_layer_dimension_xml(self, layer_elem, layer: Layer):
        """ Generate the 'Dimension' subelement of a xml capability layer object

        Since not all information of the original Dimension object are persisted, we simply take the Dimension/Extent
        elements from the original.

        Args:
            layer_elem (_Element): The layer xml element
            layer (Layer): The layer object
        Returns:
            nothing
        """

        if self.original_doc is None:
            return

        try:
            original_layer_elem = xml_helper.find_element_where_text(self.original_doc, layer.identifier)[0]
        except IndexError:
            original_layer_elem = None

        if original_layer_elem is None:
            return

        original_dimension_elems = xml_helper.try_get_element_from_xml(
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("Dimension"),
            original_layer_elem
        )
        original_extent_elems = xml_helper.try_get_element_from_xml(
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("Extent"),
            original_layer_elem
        )
        elems = original_dimension_elems + original_extent_elems

        for elem in elems:
            xml_helper.add_subelement(
                layer_elem,
                elem
            )

    def _generate_capability_layer_metadata_url_xml(self, layer_elem, layer):
        """ Generate the 'MetadataURL' subelement of a layer xml object

        Args:
            layer_elem (_Element): The layer xml element
        Returns:
            nothing
        """
        md = layer.metadata

        dataset_md = md.get_related_dataset_metadata()
        if dataset_md is None:
            return

        metadata_elem = xml_helper.create_subelement(
            layer_elem,
            "{}MetadataURL".format(self.default_ns),
            attrib={
                "type": "ISO19115:2003"
            }
        )
        elem = xml_helper.create_subelement(
            metadata_elem,
            "{}Format".format(self.default_ns)
        )
        xml_helper.write_text_to_element(elem, txt="text/xml")

        uri = dataset_md.metadata_url
        xml_helper.create_subelement(
            metadata_elem,
            "{}OnlineResource".format(self.default_ns),
            attrib={
                "{}type".format(self.xlink_ns): "simple",
                "{}href".format(self.xlink_ns): uri,
            }
        )

    def _generate_capability_layer_style_xml(self, layer_elem: Element, styles: QuerySet):
        """ Generate the 'Style' subelement of a layer xml object

        Args:
            layer_elem (_Element): The layer xml element
        Returns:
            nothing
        """
        for style in styles:
            style_elem = xml_helper.create_subelement(layer_elem, "{}Style".format(self.default_ns))
            elem = xml_helper.create_subelement(style_elem, "{}Name".format(self.default_ns))
            xml_helper.write_text_to_element(elem,txt=style.name)
            elem = xml_helper.create_subelement(style_elem, "{}Title".format(self.default_ns))
            xml_helper.write_text_to_element(elem, txt=style.title)
            legend_url_elem = xml_helper.create_subelement(
                style_elem,
                "{}LegendURL".format(self.default_ns),
                attrib=OrderedDict({
                    "width": str(style.width),
                    "height": str(style.height),
                })
            )
            elem = xml_helper.create_subelement(legend_url_elem, "{}Format".format(self.default_ns))
            xml_helper.write_text_to_element(elem, txt=style.mime_type)

            uri = style.legend_uri

            xml_helper.create_subelement(
                legend_url_elem,
                "{}OnlineResource".format(self.default_ns),
                attrib={
                    "{}type".format(self.xlink_ns): "simple",
                    "{}href".format(self.xlink_ns): uri
                }
            )

    def _generate_capability_version_specific(self, upper_elem: Element, layer: Layer):
        """ Has to be implemented in each CapabilityBuilder version specific implementation

        Generates/Modifies <Capability> content that is specific for this wms version

        Args:
            upper_elem: The layer xml element
            layer: The layer object
        Returns:

        """
        pass

    def _generate_service_version_specific(self, upper_elem: Element, md: Metadata):
        """ Has to be implemented in each CapabilityBuilder version specific implementation

        Generates/Modifies <Service> content that is specific for this wms version

        Args:
            upper_elem: The layer xml element
            layer: The layer object
        Returns:

        """
        pass

    def _generate_capability_layer_scale_hint(self, upper_elem: Element, layer: Layer):
        """ Generate the 'ScaleHint' subelement of a layer xml object

        Args:
            upper_elem (Element): The upper xml element
            layer (Layer): The layer object
        Returns:

        """
        # ScaleHint
        if layer.scale_min is not None and layer.scale_max is not None:
            scale_hint = OrderedDict(
                {
                    "min": str(layer.scale_min),
                    "max": str(layer.scale_max),
                }
            )
        else:
            scale_hint = {}
        xml_helper.create_subelement(
            upper_elem,
            "{}ScaleHint".format(self.default_ns),
            attrib=scale_hint
        )


class CapabilityWMS100Builder(CapabilityWMSBuilder):
    """

    Creates a xml document, according to the specification of WMS 1.0.0
    http://schemas.opengis.net/wms/1.0.0/capabilities_1_0_0.dtd

    """
    def __init__(self, metadata: Metadata, force_version: str = None):
        super().__init__(metadata=metadata, force_version=force_version)
        self.schema_location = "http://schemas.opengis.net/wms/1.0.0/capabilities_1_0_0.dtd"

        # Since we have to fetch some elements from the original document, we simply load it on construction
        try:
            self.original_doc = self.metadata.get_remote_original_capabilities_document(self.service_version)
            self.original_doc = xml_helper.parse_xml(self.original_doc)
        except ConnectionError as e:
            service_logger.error(e)
            self.original_doc = None

    def _generate_keyword_xml(self, upper_elem, md: Metadata):
        """ Generates the 'Keywords' subelement of a wms 1.0.0 service

        Args:
            upper_elem (Element): The upper xml element
            md (Metadata): The metadata object
        Returns:

        """
        kw_elem = xml_helper.create_subelement(
            upper_elem,
            "{}Keywords".format(self.default_ns)
        )
        keywords = " ".join([kw.keyword for kw in md.keywords.all()])
        xml_helper.write_text_to_element(kw_elem, txt=keywords)

    def _generate_service_version_specific(self, upper_elem: Element, layer: Layer):
        """ Generate different subelements of a service xml object, which are specific for version 1.0.0

        Args:
            upper_elem (_Element): The upper xml element (service or layer level)
        Returns:
            nothing
        """
        # The <ContactInformation> element has been created. WMS 1.0.0 does not include this element, so we delete it again.
        # Yes, we could simply create an own _generate_service_xml() implementation, where we ignore this element, but
        # this increases the code length and maintain work. Furthermore ... seriously... wo uses WMS 1.0.0? Do not overengineer in here...
        contact_info_elem = xml_helper.try_get_single_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("ContactInformation"),
            upper_elem
        )
        xml_helper.remove_element(contact_info_elem)

    def _generate_capability_request_xml(self, request_elem: Element):
        """ Generate the 'Request' subelement of a xml capability object

        Args:
            request_elem (_Element): The request xml element
        Returns:
            nothing
        """

        if self.original_doc is None:
            return

        original_request_elem = xml_helper.try_get_single_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("Request"),
            self.original_doc
        )
        for elem in original_request_elem.getchildren():
            xml_helper.add_subelement(
                request_elem,
                elem
            )

    def _generate_capability_exception_xml(self, capability_elem: Element):
        """ Generate the 'Exception' subelement of a xml capability object

        Args:
            capability_elem (_Element): The request xml element
        Returns:
            nothing
        """

        if self.original_doc is None:
            return

        original_exception_elem = xml_helper.try_get_single_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("Exception"),
            self.original_doc
        )
        xml_helper.add_subelement(
            capability_elem,
            original_exception_elem
        )

    def _generate_capability_layer_xml(self, layer_elem: Element, md: Metadata):
        """ Generate the 'Layer' subelement of a capability xml object

        Args:
            layer_elem (_Element): The layer xml element
        Returns:
            nothing
        """
        layer = Layer.objects.get(
            metadata=md
        )
        md = layer.metadata
        layer_elem = xml_helper.create_subelement(
            layer_elem,
            "{}Layer".format(self.default_ns),
            attrib={
                "queryable": str(int(layer.is_queryable)),
            }
        )

        elem = xml_helper.create_subelement(layer_elem, "{}Name".format(self.default_ns))
        xml_helper.write_text_to_element(elem, txt=layer.identifier)

        elem = xml_helper.create_subelement(layer_elem, "{}Title".format(self.default_ns))
        xml_helper.write_text_to_element(elem, txt=md.title)

        elem = xml_helper.create_subelement(layer_elem, "{}Abstract".format(self.default_ns))
        xml_helper.write_text_to_element(elem, txt=md.abstract)

        # KeywordList
        self._generate_keyword_xml(layer_elem, layer.metadata)

        # SRS|CRS
        self._generate_capability_layer_srs_xml(layer_elem, layer)

        # Bounding Box
        self._generate_capability_layer_bounding_box_xml(layer_elem, layer)
        # DataURL
        elem = xml_helper.create_subelement(layer_elem, "{}DataURL".format(self.default_ns))
        xml_helper.write_text_to_element(elem, txt="")  # We do not provide this. Leave it empty

        # Style
        self._generate_capability_layer_style_xml(layer_elem, layer.get_style())

        # Various
        self._generate_capability_version_specific(layer_elem, layer)

        # Recall the function with the children as input
        layer_children = layer.get_children()
        for layer_child in layer_children:
            self._generate_capability_layer_xml(layer_elem, layer_child.metadata)

    def _generate_capability_layer_srs_xml(self, layer_elem, layer: Layer):
        """ Generate the 'SRS' subelement of a layer xml object

        Args:
            layer_elem (_Element): The layer xml element
        Returns:
            nothing
        """
        reference_systems = layer.get_inherited_reference_systems()
        srs_element = xml_helper.create_subelement(layer_elem, "{}SRS".format(self.default_ns))
        srs_list = ["{}{}".format(srs.prefix, srs.code) for srs in reference_systems]
        srs_list = " ".join(srs_list)
        xml_helper.write_text_to_element(srs_element, txt=srs_list)

    def _generate_online_resource_xml(self, upper_elem: Element, md: Metadata):
        """ Generate the 'OnlineResource' subelement of a xml object

        Args:
            upper_elem (Element): The capability xml element
            md (Metadata): The metadata element (for OnlineResource it's the parent of the regular metadata)
        Returns:
            nothing
        """
        online_resource_elem = xml_helper.create_subelement(
            upper_elem,
            "{}OnlineResource".format(self.default_ns)
        )
        xml_helper.write_text_to_element(
            online_resource_elem,
            txt=SERVICE_OPERATION_URI_TEMPLATE.format(md.id),
        )

    def _generate_capability_version_specific(self, upper_elem: Element, layer: Layer):
        """ Generate different subelements of a layer xml object, which are specific for version 1.0.0

        Args:
            upper_elem (_Element): The layer xml element
        Returns:
            nothing
        """
        self._generate_capability_layer_scale_hint(upper_elem, layer)


class CapabilityWMS111Builder(CapabilityWMSBuilder):
    """

    Creates a xml document, according to the specification of WMS 1.1.1
    http://schemas.opengis.net/wms/1.1.1/capabilities_1_1_1.xml

    """
    def __init__(self, metadata: Metadata, force_version: str = None):
        super().__init__(metadata=metadata, force_version=force_version)
        self.schema_location = "http://schemas.opengis.net/wms/1.1.1/capabilities_1_1_1.dtd"

    def _generate_capability_version_specific(self, upper_elem: Element, layer: Layer):
        """ Generate different subelements of a layer xml object, which are specific for version 1.1.1

        Args:
            upper_elem (_Element): The layer xml element
        Returns:
            nothing
        """
        self._generate_capability_layer_scale_hint(upper_elem, layer)


class CapabilityWMS130Builder(CapabilityWMSBuilder):
    """

    Creates a xml document, according to the specification of WMS 1.3.0
    http://schemas.opengis.net/wms/1.3.0/capabilities_1_3_0.xsd

    """

    def __init__(self, metadata: Metadata, force_version: str = None):
        super().__init__(metadata=metadata, force_version=force_version)

        self.namespaces[None] = XML_NAMESPACES["wms"]
        self.default_ns = "{" + self.namespaces.get(None) + "}"
        self.schema_location = "http://schemas.opengis.net/wms/1.3.0/capabilities_1_3_0.xsd"

    def _generate_service_xml(self, service_elem: Element):
        """ Generate the 'Service' subelement of a xml service object

        Args:
            service_elem (_Element): The service xml element
        Returns:
            nothing
        """
        md = self.metadata
        service_md = self.service.metadata

        #Create start of <Service> elements
        contents = OrderedDict({
            "{}Name": service_md.identifier,
            "{}Title": service_md.title,
            "{}Abstract": service_md.abstract,
        })
        self._generate_simple_elements_from_dict(service_elem, contents)

        # Add keywords to <wms:KeywordList>
        self._generate_keyword_xml(service_elem, service_md)

        # OnlineResource
        self._generate_online_resource_xml(service_elem, service_md)

        # Fill in the data for <ContactInformation>
        self._generate_service_contact_information_xml(service_elem)

        # Create end of <Service> elements
        fees, access_constraints = self._generate_licence_related_constraints()
        contents = OrderedDict({
            "{}Fees": fees,
            "{}AccessConstraints": access_constraints,
            "{}MaxWidth": "",  # ToDo: Implement md.service.max_width in registration
            "{}MaxHeight": "",  # ToDo: Implement md.service.max_height in registration
        })
        self._generate_simple_elements_from_dict(service_elem, contents)

    def _generate_capability_xml(self, capability_elem: Element):
        """ Generate the 'Capability' subelement of a xml object

        Args:
            capability_elem (_Element): The capability xml element
        Returns:
            nothing
        """
        md = self.metadata

        # Layers are not included in this contents dict, since they will be appended separately at the end
        contents = OrderedDict({
            "{}Request": "",
        })
        self._generate_simple_elements_from_dict(capability_elem, contents)

        request_elem = xml_helper.try_get_single_element_from_xml(
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("Request"),
            capability_elem
        )

        self._generate_capability_request_xml(request_elem)

        self._generate_capability_exception_xml(capability_elem)

        self._generate_capability_layer_xml(capability_elem, md)

        self._generate_vendor_specific_capabilities_xml(capability_elem, self.inspire_vs_ns)

    def _generate_capability_layer_bounding_box_xml(self, layer_elem, layer: Layer):
        """ Generate the 'LatLonBoundingBox' subelement of a layer xml object

        Args:
            layer_elem (_Element): The layer xml element
        Returns:
            nothing
        """

        md = layer.metadata
        reference_systems = layer.get_inherited_reference_systems()

        # wms:EX_GeographicBoundingBox
        bounding_geometry = md.bounding_geometry
        bbox = md.bounding_geometry.extent

        # Prevent a situation where the bbox would be 0, by taking the parent service bbox.
        # We must(!) take the parent service root layer bounding geometry, since this information is the most reliable
        # if this service is compared with another copy of itself!
        if bbox == (0.0, 0.0, 0.0, 0.0):
            bounding_geometry = layer.get_inherited_bounding_geometry()
            bbox = bounding_geometry.extent

        bbox_content = OrderedDict({
            "{}westBoundLongitude": str(bbox[0]),
            "{}eastBoundLongitude": str(bbox[2]),
            "{}southBoundLatitude": str(bbox[1]),
            "{}northBoundLatitude": str(bbox[3]),
        })
        elem = xml_helper.create_subelement(layer_elem, "{}EX_GeographicBoundingBox".format(self.default_ns))
        self._generate_simple_elements_from_dict(elem, bbox_content)

        # wms:BoundingBox
        # We must provide appropriate bounding boxes for all supported reference systems, since we can not be sure the
        # client may transform a bounding box by itself.
        epsg_handler = EpsgApi()
        for reference_system in reference_systems:
            bounding_geometry.transform(reference_system.code)
            bbox = list(bounding_geometry.extent)

            switch_axis = epsg_handler.check_switch_axis_order(self.service_type, self.service_version, reference_system.code)
            if switch_axis:
                for i in range(0, len(bbox), 2):
                    tmp = bbox[i]
                    bbox[i] = bbox[i + 1]
                    bbox[i + 1] = tmp

            xml_helper.create_subelement(
                layer_elem,
                "{}BoundingBox".format(self.default_ns),
                attrib=OrderedDict({
                    "CRS": "EPSG:{}".format(str(bounding_geometry.srid)),
                    "minx": str(bbox[0]),
                    "miny": str(bbox[1]),
                    "maxx": str(bbox[2]),
                    "maxy": str(bbox[3]),
                })
            )

    def _generate_capability_version_specific(self, upper_elem: Element, layer: Layer):
        """ Generate different subelements of a layer xml object, which are specific for version 1.3.0

        Args:
            upper_elem (_Element): The layer xml element
        Returns:
            nothing
        """
        # MinScaleDenominator
        elem = xml_helper.create_subelement(upper_elem, "{}MinScaleDenominator".format(self.default_ns))
        xml_helper.write_text_to_element(elem, txt="")

        # MaxScaleDenominator
        elem = xml_helper.create_subelement(upper_elem, "{}MaxScaleDenominator".format(self.default_ns))
        xml_helper.write_text_to_element(elem, txt="")


class CapabilityWFSBuilder(CapabilityXMLBuilder):
    """ Base class for WFS capabilities building

    Wraps all basic capabilities generating methods

    Follows the standard specifications from
    http://schemas.opengis.net/ows/
    http://schemas.opengis.net/wfs/

    """
    def __init__(self, metadata: Metadata, force_version: str=None):
        super().__init__(metadata=metadata, force_version=force_version)

        # Remove possible default namespace, since this does not seem to exist in WFS > 1.1.0
        try:
            del self.namespaces[None]
        except KeyError:
            pass

        self.namespaces["ows"] = XML_NAMESPACES["ows"]
        self.namespaces["ogc"] = XML_NAMESPACES["ogc"]
        self.namespaces["gml"] = XML_NAMESPACES["gml"]
        self.namespaces[None] = XML_NAMESPACES["wfs"]

        self.default_ns = "{" + XML_NAMESPACES["ows"] + "}"
        self.wfs_ns = "{" + XML_NAMESPACES["wfs"] + "}"

        self.rs_declaration = "SRS"

        self.feature_type_list = []
        if self.metadata.is_metadata_type(MetadataEnum.FEATURETYPE):
            self.feature_type_list = FeatureType.objects.filter(
                metadata=metadata,
            )
        else:
            self.feature_type_list = FeatureType.objects.filter(
                parent_service=self.parent_service
            )

    def _generate_xml(self):
        """ Generate an xml capabilities document from the metadata object

        Args:

        Returns:
             nothing
        """
        root = Element(
            '{}WFS_Capabilities'.format(self.wfs_ns),
            attrib={
                "version": self.service_version,
                "{}schemaLocation".format(self.xsi_ns): self.schema_location,
            },
            nsmap=self.namespaces
        )
        self.xml_doc_obj = root

        start_time = time()
        self._generate_service_identification_xml(root)
        service_logger.debug("ServiceIdentification creation took {} seconds".format((time() - start_time)))

        start_time = time()
        self._generate_service_provider_xml(root)
        service_logger.debug("ServiceProvider creation took {} seconds".format(time() - start_time))

        start_time = time()
        self._generate_operations_metadata_xml(root)
        service_logger.debug("OperationsMetadata creation took {} seconds".format(time() - start_time))

        start_time = time()
        self._generate_feature_type_list_xml(root)
        service_logger.debug("FeatureTypeList creation took {} seconds".format(time() - start_time))

        start_time = time()
        self._generate_filter_capabilities_xml(root)
        service_logger.debug("Filter_Capabilities creation took {} seconds".format(time() - start_time))

        start_time = time()
        xml = xml_helper.xml_to_string(root, pretty_print=False)
        service_logger.debug("Rendering to string took {} seconds".format((time() - start_time)))

        return xml

    def _generate_keyword_xml(self, upper_elem, md: Metadata):
        """ Generate the 'Keywords' subelement of a wfs xml object

        Args:
            upper_elem (_Element): The upper xml element

        Returns:
            nothing
        """
        keywords_elem = xml_helper.create_subelement(
            upper_elem,
            "{}Keywords".format(self.default_ns)
        )
        for kw in md.keywords.all():
            keyword = kw.keyword
            kw_elem = xml_helper.create_subelement(
                keywords_elem,
                "{}Keyword".format(self.default_ns)
            )
            xml_helper.write_text_to_element(
                kw_elem,
                txt=keyword
            )

    def _generate_service_identification_xml(self, upper_elem: Element):
        """ Generate the 'Service' subelement of a xml service object

        Args:
            upper_elem (_Element): The upper xml element
        Returns:
            nothing
        """
        service_elem = xml_helper.create_subelement(
            upper_elem,
            "{}ServiceIdentification".format(self.default_ns)
        )

        contents = OrderedDict({
            "{}Title": self.service.metadata.title,
            "{}Abstract": self.service.metadata.abstract,
        })
        self._generate_simple_elements_from_dict(service_elem, contents)
        self._generate_keyword_xml(service_elem, self.service.metadata)
        self._generate_service_type(service_elem)

        fees, access_constraints = self._generate_licence_related_constraints()
        contents = OrderedDict({
            "{}ServiceTypeVersion": self.service_version,
            "{}Fees": fees,
            "{}AccessConstraints": access_constraints,
        })
        self._generate_simple_elements_from_dict(service_elem, contents)

    def _generate_service_type(self, upper_elem: Element):
        """ Generate the 'ServiceType' subelement of a xml service object

        Args:
            upper_elem (_Element): The upper xml element
        Returns:
            nothing
        """
        service_type_elem = xml_helper.create_subelement(
            upper_elem,
            "{}ServiceType".format(self.default_ns),
            attrib={
                "codeSpace": "OGC"
            }
        )
        xml_helper.write_text_to_element(
            service_type_elem,
            txt="OGC WFS"
        )

    def _generate_service_provider_xml(self, upper_elem: Element):
        """ Generate the 'Capability' subelement of a xml service object

        Args:
            upper_elem (_Element): The upper xml element
        Returns:
            nothing
        """
        # Again, we simply take the original information!
        # Since these informations can not be changed by our metadata editor, we have this freedom.
        self._fetch_original_xml(upper_elem, "ServiceProvider")

    def _generate_operations_metadata_xml(self, upper_elem: Element):
        """ Generate the 'Capability' subelement of a xml service object

        Args:
            upper_elem (_Element): The upper xml element
        Returns:
            nothing
        """
        # Again, we simply take the original information!
        # Since these informations can not be changed by our metadata editor, we have this freedom.
        self._fetch_original_xml(upper_elem, "OperationsMetadata")

        # Auto secure GetCapabilities links
        get_cap_element = xml_helper.find_element_where_attr(
            upper_elem,
            "name",
            "GetCapabilities"
        )
        if len(get_cap_element) != 0:
            get_cap_element = get_cap_element[0]
        get_elem = xml_helper.try_get_single_element_from_xml(
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("Get"),
            get_cap_element
        )
        post_elem = xml_helper.try_get_single_element_from_xml(
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("Post"),
            get_cap_element
        )

        xml_helper.set_attribute(
            get_elem,
            "{}href".format(self.xlink_ns),
            SERVICE_OPERATION_URI_TEMPLATE.format(self.metadata.id)
        )

        xml_helper.set_attribute(
            post_elem,
            "{}href".format(self.xlink_ns),
            SERVICE_OPERATION_URI_TEMPLATE.format(self.metadata.id)
        )

        operations_metadata_elem = xml_helper.try_get_single_element_from_xml(
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("OperationsMetadata"),
            upper_elem
        )

        extended_capabilities_elem = xml_helper.create_subelement(
            operations_metadata_elem,
            "{}ExtendedCapabilities".format(self.default_ns)
        )
        self._generate_extended_capabilities_xml(extended_capabilities_elem, self.inspire_dls_ns)

    def _generate_feature_type_list_xml(self, upper_elem: Element):
        """ Generate the 'FeatureTypeList' subelement of a xml service object

        Args:
            upper_elem (_Element): The upper xml element
        Returns:
            nothing
        """
        feature_type_list_elem = xml_helper.create_subelement(
            upper_elem,
            "{}FeatureTypeList".format(self.wfs_ns)
        )

        # Fetch original <Operations> element
        self._fetch_original_xml(
            feature_type_list_elem,
            "Operations"
        )

        self._generate_feature_type_list_feature_type_xml(feature_type_list_elem)

    def _generate_feature_type_list_feature_type_xml(self, upper_elem):
        """ Generate the 'FeatureType' subelement of a xml service object

        Args:
            upper_elem (_Element): The upper xml element
        Returns:
            nothing
        """
        for feature_type_obj in self.feature_type_list:
            feature_type_elem = xml_helper.create_subelement(
                upper_elem,
                "{}FeatureType".format(self.wfs_ns)
            )

            # Generate dynamic contents
            contents = OrderedDict({
                "{}Name": feature_type_obj.metadata.identifier,
                "{}Title": feature_type_obj.metadata.title,
                "{}Abstract": feature_type_obj.metadata.abstract,
            })
            self._generate_simple_elements_from_dict(
                feature_type_elem,
                contents,
                self.wfs_ns
            )

            # ows:Keywords
            self._generate_keyword_xml(feature_type_elem, feature_type_obj.metadata)

            # DefaultSRS | OtherSRS
            self._generate_feature_type_list_feature_type_srs_xml(feature_type_elem, feature_type_obj)

            # OutputFormats
            self._generate_feature_type_list_feature_type_formats_xml(feature_type_elem, feature_type_obj)

            # ows:WGS84BoundingBox
            self._generate_feature_type_list_feature_type_bbox_xml(feature_type_elem, feature_type_obj)

            # MetadataURL
            self._generate_feature_type_list_feature_type_metadata_url(feature_type_elem, feature_type_obj)

    def _generate_feature_type_list_feature_type_srs_xml(self, upper_elem, feature_type_obj: FeatureType):
        """ Generate the 'DefaultSRS|OtherSRS' subelement of a xml service object

        Args:
            upper_elem (_Element): The upper xml element
        Returns:
            nothing
        """
        # DefaultSRS
        elem = xml_helper.create_subelement(
            upper_elem,
            "{}Default{}".format(self.wfs_ns, self.rs_declaration)
        )
        xml_helper.write_text_to_element(
            elem,
            txt="{}{}".format(feature_type_obj.default_srs.prefix, feature_type_obj.default_srs.code)
        )
        other_ref_systems = feature_type_obj.metadata.reference_system.all()
        for srs in other_ref_systems:
            # OtherSRS
            elem = xml_helper.create_subelement(
                upper_elem,
                "{}Other{}".format(self.wfs_ns, self.rs_declaration)
            )
            xml_helper.write_text_to_element(
                elem,
                txt="{}{}".format(srs.prefix, srs.code)
            )

    def _generate_feature_type_list_feature_type_formats_xml(self, upper_elem: Element, feature_type_obj: FeatureType):
        """ Generate the 'OutputFormats' subelement of a xml service object

        Args:
            upper_elem (_Element): The upper xml element
        Returns:
            nothing
        """
        output_format_elem = xml_helper.create_subelement(
            upper_elem,
            "{}OutputFormats".format(self.wfs_ns)
        )
        formats = feature_type_obj.metadata.get_formats()
        for format in formats:
            elem = xml_helper.create_subelement(
                output_format_elem,
                "{}Format".format(self.wfs_ns)
            )
            xml_helper.write_text_to_element(elem, txt=format.mime_type)

    def _generate_feature_type_list_feature_type_bbox_xml(self, upper_elem: Element, feature_type_obj: FeatureType):
        """ Generate the 'WGS84BoundingBox' subelement of a xml service object

        Args:
            upper_elem (_Element): The upper xml element
        Returns:
            nothing
        """
        try:
            bbox = feature_type_obj.metadata.bounding_geometry.extent
            bbox_elem = xml_helper.create_subelement(
                upper_elem,
                "{}WGS84BoundingBox".format(self.default_ns),
                attrib={
                    "dimensions": "2"
                }
            )

            lower_corner_elem = xml_helper.create_subelement(
                bbox_elem,
                "{}LowerCorner".format(self.default_ns)
            )
            xml_helper.write_text_to_element(
                lower_corner_elem,
                txt="{} {}".format(
                    str(bbox[0]),
                    str(bbox[1])
                )
            )

            upper_corner_elem = xml_helper.create_subelement(
                bbox_elem,
                "{}UpperCorner".format(self.default_ns)
            )
            xml_helper.write_text_to_element(
                upper_corner_elem,
                txt="{} {}".format(
                    str(bbox[2]),
                    str(bbox[3])
                )
            )
        except AttributeError:
            pass

    def _generate_feature_type_list_feature_type_metadata_url(self, upper_elem, feature_type_obj: FeatureType):
        """ Generate the 'MetadataURL' subelement of a xml feature type list object

        Args:
            upper_elem (_Element): The upper xml element
        Returns:
            nothing
        """
        dataset_mds = feature_type_obj.metadata.related_metadata.filter(
            metadata_to__metadata_type=MetadataEnum.DATASET.value,
        )
        for dataset_md in dataset_mds:
            try:
                metadata_url_elem = xml_helper.create_subelement(
                    upper_elem,
                    "{}MetadataURL".format(self.default_ns),
                    attrib=OrderedDict({
                        "type": "TC211",
                        "format": "text/xml",
                    })
                )
                xml_helper.write_text_to_element(
                    metadata_url_elem,
                    txt=dataset_md.metadata_to.metadata_url
                )
            except ObjectDoesNotExist:
                continue

    def _generate_filter_capabilities_xml(self, upper_elem: Element):
        """ Generate the 'Filter_Capabilities' subelement of a xml service object

        Args:
            upper_elem (_Element): The upper xml element
        Returns:
            nothing
        """
        # This is a completely technical element, without any information that might be edited using the metadata editor.
        # We can simply take the original content!
        self._fetch_original_xml(
            upper_elem,
            "Filter_Capabilities"
        )


class CapabilityWFS100Builder(CapabilityWFSBuilder):
    def __init__(self, metadata: Metadata, force_version: str = None):
        super().__init__(metadata=metadata, force_version=force_version)
        self.schema_location = "http://schemas.opengis.net/wfs/1.0.0/WFS-capabilities.xsd"

        # Remove regular "wfs" namespace and add it as default for wfs 1.0.0
        try:
            del self.namespaces["wfs"]
        except KeyError:
            pass
        self.namespaces[None] = XML_NAMESPACES["wfs"]
        self.default_ns = "{" + XML_NAMESPACES["wfs"] + "}"

        # WFS 1.0.0 expects a /Service/Name
        self.default_identifier = "WFS"

    def _generate_xml(self):
        """ Generate an xml capabilities document from the metadata object

        Args:

        Returns:
             nothing
        """
        root = Element(
            '{}WFS_Capabilities'.format(self.default_ns),
            attrib={
                "version": self.service_version,
                "{}schemaLocation".format(self.xsi_ns): self.schema_location,
            },
            nsmap=self.namespaces
        )
        self.xml_doc_obj = root

        start_time = time()
        self._generate_service_xml(root)
        service_logger.debug("Service creation took {} seconds".format((time() - start_time)))

        start_time = time()
        self._generate_capability_xml(root)
        service_logger.debug("Capabilities creation took {} seconds".format(time() - start_time))

        start_time = time()
        self._generate_feature_type_list_xml(root)
        service_logger.debug("FeatureTypeList creation took {} seconds".format(time() - start_time))

        start_time = time()
        self._generate_filter_capabilities_xml(root)
        service_logger.debug("Filter_Capabilities creation took {} seconds".format(time() - start_time))

        start_time = time()
        xml = xml_helper.xml_to_string(root, pretty_print=False)
        service_logger.debug("Rendering to string took {} seconds".format((time() - start_time)))

        return xml

    def _generate_service_xml(self, upper_elem: Element):
        """ Generate the 'Service' subelement of a xml service object

        Args:
            service_elem (_Element): The service xml element
        Returns:
            nothing
        """
        service_md = self.service.metadata

        service_elem = xml_helper.create_subelement(upper_elem, "{}Service".format(self.default_ns))
        # Create generic xml starter elements
        contents = OrderedDict({
            "{}Name": service_md.identifier or self.default_identifier,
            "{}Title": service_md.title,
            "{}Abstract": service_md.abstract,
        })
        self._generate_simple_elements_from_dict(service_elem, contents)

        # KeywordList and keywords
        self._generate_keyword_xml(service_elem, service_md)

        # OnlineResource
        self._generate_online_resource_xml(service_elem, service_md)

        # Create generic xml end elements
        fees, access_constraints = self._generate_licence_related_constraints()
        contents = OrderedDict({
            "{}Fees": fees,
            "{}AccessConstraints": access_constraints,
        })
        self._generate_simple_elements_from_dict(service_elem, contents)

    def _generate_online_resource_xml(self, upper_elem: Element, md: Metadata):
        """ Generate the 'OnlineResource' subelement of a xml object

        Args:
            upper_elem (Element): The capability xml element
            md (Metadata): The metadata element (for OnlineResource it's the parent of the regular metadata)
        Returns:
            nothing
        """
        online_resource_elem = xml_helper.create_subelement(
            upper_elem,
            "{}OnlineResource".format(self.default_ns)
        )
        xml_helper.write_text_to_element(
            online_resource_elem,
            txt=SERVICE_OPERATION_URI_TEMPLATE.format(md.id),
        )

    def _generate_keyword_xml(self, upper_elem, md: Metadata):
        """ Generate the 'Keywords' subelement of a wfs xml object

        Args:
            upper_elem (_Element): The upper xml element

        Returns:
            nothing
        """
        keywords = md.keywords.all()
        elem = xml_helper.create_subelement(upper_elem, "{}Keywords".format(self.default_ns))
        keyword_text = " ".join([kw.keyword for kw in keywords])
        xml_helper.write_text_to_element(elem, txt=keyword_text)

    def _generate_capability_xml(self, upper_elem):
        """ Generate the 'Capability' subelement of a layer xml object and it's subelements

        Args:
            upper_elem (_Element): The upper xml element

        Returns:
            nothing
        """
        capability_elem = xml_helper.create_subelement(upper_elem, "{}Capability".format(self.default_ns))

        # Request
        self._generate_capability_request_xml(capability_elem)

        # VendorSpecificCapabilities
        self._generate_vendor_specific_capabilities_xml(capability_elem, ns=self.inspire_dls_ns)

    def _generate_capability_request_xml(self, upper_elem: Element):
        """ Generate the 'Request' subelement of a xml capability object

        Args:
            upper_elem (_Element): The request xml element
        Returns:
            nothing
        """

        # Due to strange Format declarations in WMS 1.0.0 we prefer to use the original <Request> content and modify the
        # GetCapabilities links to match our internal uri
        self._fetch_original_xml(upper_elem, "Request")

        # Auto secure GetCapabilities links
        get_cap_element = xml_helper.try_get_single_element_from_xml(
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("GetCapabilities"),
            upper_elem
        )
        get_elem = xml_helper.try_get_single_element_from_xml(
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("Get"),
            get_cap_element
        )
        post_elem = xml_helper.try_get_single_element_from_xml(
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("Post"),
            get_cap_element
        )

        xml_helper.set_attribute(
            get_elem,
            "onlineResource",
            SERVICE_OPERATION_URI_TEMPLATE.format(self.metadata.id)
        )

        xml_helper.set_attribute(
            post_elem,
            "onlineResource",
            SERVICE_OPERATION_URI_TEMPLATE.format(self.metadata.id)
        )

    def _generate_capability_operation_xml(self, upper_elem: Element, get_uri: str, post_uri: str):
        """ Generate the various operation subelements of a xml capability object

        Args:
            upper_elem (_Element): The operation xml element
        Returns:
            nothing
        """
        md = self.metadata
        service = self.service
        tag = QName(upper_elem).localname

        if OGCOperationEnum.GET_CAPABILITIES.value in tag:
            # GetCapabilities is always set to our internal systems uri, we do not touch it!
            get_uri = SERVICE_OPERATION_URI_TEMPLATE.format(md.id)
            post_uri = SERVICE_OPERATION_URI_TEMPLATE.format(md.id)

        # Add all mime types that are supported by this operation
        supported_formats = service.metadata.get_formats().filter(
            operation=tag
        )
        for format in supported_formats:
            format_elem = xml_helper.create_subelement(upper_elem, "{}Format".format(self.default_ns))
            xml_helper.write_text_to_element(format_elem, txt=format.mime_type)

        # Add <DCPType> contents
        dcp_elem = xml_helper.create_subelement(upper_elem, "{}DCPType".format(self.default_ns))
        http_elem = xml_helper.create_subelement(dcp_elem, "{}HTTP".format(self.default_ns))

        xml_helper.create_subelement(
            http_elem,
            "{}Get".format(self.default_ns),
            attrib={
                "onlineResource": get_uri
            }
        )
        xml_helper.create_subelement(
            http_elem,
            "{}Post".format(self.default_ns),
            attrib={
                "onlineResource": post_uri
            }
        )

    def _generate_feature_type_list_xml(self, upper_elem: Element):
        """ Generate the 'FeatureTypeList' subelement of a xml capability object

        Args:
            upper_elem (_Element): The upper xml element
        Returns:
            nothing
        """
        feature_type_list_elem = xml_helper.create_subelement(
            upper_elem,
            "{}FeatureTypeList".format(self.default_ns)
        )
        self._generate_feature_type_list_operations(feature_type_list_elem)
        self._generate_feature_type_list_feature_type(feature_type_list_elem)

    def _generate_feature_type_list_operations(self, upper_elem: Element):
        """ Generate the 'Operation' subelement of a xml feature type list object

        Args:
            upper_elem (_Element): The upper xml element
        Returns:
            nothing
        """
        # Since these are technical information, which are not editable using the metadata editor, we can again simply
        # take the content from the original and insert it in our document
        self._fetch_original_xml(upper_elem, "Operations")

    def _generate_feature_type_list_feature_type(self, upper_elem: Element):
        """ Generate the 'Operation' subelement of a xml feature type list object

        Args:
            upper_elem (_Element): The upper xml element
        Returns:
            nothing
        """
        feature_type_elem = xml_helper.create_subelement(
            upper_elem,
            "{}FeatureType".format(self.default_ns)
        )
        contents = {
            "{}Name": self.metadata.identifier,
            "{}Title": self.metadata.title,
            "{}Abstract": self.metadata.abstract,
        }
        for key, val in contents.items():
            k = key.format(self.default_ns)
            elem = xml_helper.create_subelement(feature_type_elem, k)
            xml_helper.write_text_to_element(elem, txt=val)

        self._generate_keyword_xml(feature_type_elem, md=self.metadata)
        self._generate_feature_type_list_feature_type_srs(feature_type_elem)
        self._generate_feature_type_list_feature_type_bbox(feature_type_elem)
        self._generate_feature_type_list_feature_type_metadata_url(feature_type_elem)

    def _generate_feature_type_list_feature_type_srs(self, upper_elem):
        """ Generate the 'SRS' subelement of a xml feature type list object

        Args:
            upper_elem (_Element): The upper xml element
        Returns:
            nothing
        """
        # In WFS 1.0.0 only one (the default) srs will be shown in the capabilities document
        srs = self.feature_type_list.default_srs
        srs_elem = xml_helper.create_subelement(
            upper_elem,
            "{}SRS".format(self.default_ns)
        )
        xml_helper.write_text_to_element(
            srs_elem,
            txt="{}{}".format(srs.prefix, srs.code)
        )

    def _generate_feature_type_list_feature_type_bbox(self, upper_elem):
        """ Generate the 'LatLongBoundingBox' subelement of a xml feature type list object

        Args:
            upper_elem (_Element): The upper xml element
        Returns:
            nothing
        """
        bounding_geom = self.metadata.bounding_geometry
        bounding_geom.transform(self.feature_type_list.default_srs.code)
        extent = bounding_geom.extent
        xml_helper.create_subelement(
            upper_elem,
            "{}LatLongBoundingBox".format(self.default_ns),
            attrib=OrderedDict({
                "minx": str(extent[0]),
                "miny": str(extent[1]),
                "maxx": str(extent[2]),
                "maxy": str(extent[3]),
            })
        )

class CapabilityWFS110Builder(CapabilityWFSBuilder):
    def __init__(self, metadata: Metadata, force_version: str = None):
        super().__init__(metadata=metadata, force_version=force_version)
        self.schema_location = "http://schemas.opengis.net/wfs/1.1.0/wfs.xsd"

    def _generate_feature_type_list_feature_type_metadata_url(self, upper_elem, feature_type_obj: FeatureType):
        """ Generate the 'MetadataURL' subelement of a xml feature type list object

        Args:
            upper_elem (_Element): The upper xml element
        Returns:
            nothing
        """
        dataset_mds = self.metadata.related_metadata.filter(
            metadata_to__metadata_type=MetadataEnum.DATASET.value,
        )
        for dataset_md in dataset_mds:
            try:
                metadata_url_elem = xml_helper.create_subelement(
                    upper_elem,
                    "{}MetadataURL".format(self.default_ns),
                    attrib=OrderedDict({
                        "type": "TC211",
                        "format": "text/xml",
                    })
                )
                xml_helper.write_text_to_element(
                    metadata_url_elem,
                    txt=dataset_md.metadata_to.metadata_url
                )
            except ObjectDoesNotExist:
                continue

class CapabilityWFS200Builder(CapabilityWFSBuilder):
    def __init__(self, metadata: Metadata, force_version: str = None):
        super().__init__(metadata=metadata, force_version=force_version)

        self.namespaces[None] = "http://www.opengis.net/wfs/2.0"
        self.namespaces["ows"] = "http://www.opengis.net/ows/1.1"
        self.namespaces["fes"] = "http://www.opengis.net/fes/2.0"

        self.default_ns = "{" + self.namespaces["ows"] + "}"
        self.wfs_ns = "{" + self.namespaces[None] + "}"

        self.schema_location = "http://schemas.opengis.net/wfs/2.0/wfs.xsd"

        self.rs_declaration = "CRS"

    def _generate_service_type(self, upper_elem: Element):
        """ Generate the 'ServiceType' subelement of a xml service object

        Args:
            upper_elem (_Element): The upper xml element
        Returns:
            nothing
        """
        service_type_elem = xml_helper.create_subelement(
            upper_elem,
            "{}ServiceType".format(self.default_ns),
            attrib={
                "codeSpace": "OGC"
            }
        )
        xml_helper.write_text_to_element(
            service_type_elem,
            txt="WFS"
        )

    def _generate_feature_type_list_operations(self, upper_element: Element):
        """ Generate the 'Operations' subelement of a xml feature type list object

        This element does not exist since WFS 2.0.0 anymore. We need this method to overwrite the default creation.

        Args:
            upper_elem (_Element): The upper xml element
        Returns:
            nothing
        """
        pass

    def _generate_feature_type_list_feature_type_metadata_url(self, upper_elem, feature_type_obj: FeatureType = None):
        """ Generate the 'MetadataURL' subelement of a xml feature type list object

        Args:
            upper_elem (_Element): The upper xml element
        Returns:
            nothing
        """
        dataset_mds = self.metadata.related_metadata.filter(
            metadata_to__metadata_type=MetadataEnum.DATASET.value,
        )
        for dataset_md in dataset_mds:
            try:
                metadata_url_elem = xml_helper.create_subelement(
                    upper_elem,
                    "{}MetadataURL".format(self.default_ns),
                    attrib=OrderedDict({
                        "{}href".format(self.xlink_ns): dataset_md.metadata_to.metadata_url,
                    })
                )
            except ObjectDoesNotExist:
                continue


class CapabilityWFS202Builder(CapabilityWFSBuilder):
    def __init__(self, metadata: Metadata, force_version: str = None):
        super().__init__(metadata=metadata, force_version=force_version)

        self.namespaces[None] = "http://www.opengis.net/wfs/2.0"
        self.namespaces["ows"] = "http://www.opengis.net/ows/1.1"
        self.namespaces["fes"] = "http://www.opengis.net/fes/2.0"

        self.default_ns = "{" + self.namespaces["ows"] + "}"
        self.wfs_ns = "{" + self.namespaces[None] + "}"

        self.schema_location = "http://schemas.opengis.net/wfs/2.0/wfs.xsd"

        self.rs_declaration = "CRS"

    def _generate_service_type(self, upper_elem: Element):
        """ Generate the 'ServiceType' subelement of a xml service object

        Args:
            upper_elem (_Element): The upper xml element
        Returns:
            nothing
        """
        service_type_elem = xml_helper.create_subelement(
            upper_elem,
            "{}ServiceType".format(self.default_ns),
            attrib={
                "codeSpace": "OGC"
            }
        )
        xml_helper.write_text_to_element(
            service_type_elem,
            txt="WFS"
        )

    def _generate_feature_type_list_operations(self, upper_element: Element):
        """ Generate the 'Operations' subelement of a xml feature type list object

        This element does not exist since WFS 2.0.0 anymore. We need this method to overwrite the default creation.

        Args:
            upper_elem (_Element): The upper xml element
        Returns:
            nothing
        """
        pass

    def _generate_feature_type_list_feature_type_metadata_url(self, upper_elem, feature_type_obj: FeatureType = None):
        """ Generate the 'MetadataURL' subelement of a xml feature type list object

        Args:
            upper_elem (_Element): The upper xml element
        Returns:
            nothing
        """
        dataset_mds = self.metadata.related_metadata.filter(
            metadata_to__metadata_type=MetadataEnum.DATASET.value,
        )
        for dataset_md in dataset_mds:
            try:
                metadata_url_elem = xml_helper.create_subelement(
                    upper_elem,
                    "{}MetadataURL".format(self.default_ns),
                    attrib=OrderedDict({
                        "{}href".format(self.xlink_ns): dataset_md.metadata_to.metadata_url,
                    })
                )
            except ObjectDoesNotExist:
                continue