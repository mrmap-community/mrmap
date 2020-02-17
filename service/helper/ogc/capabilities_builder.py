"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 31.07.19

"""
from abc import abstractmethod
from collections import OrderedDict
from time import time

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import QuerySet
from lxml.etree import Element, QName

from MapSkinner.settings import XML_NAMESPACES, GENERIC_NAMESPACE_TEMPLATE, HTTP_OR_SSL, HOST_NAME
from MapSkinner.utils import print_debug_mode
from service.helper import xml_helper
from service.helper.enums import OGCServiceVersionEnum, OGCServiceEnum, OGCOperationEnum
from service.helper.epsg_api import EpsgApi
from service.models import Service, Metadata, Layer, Document

from structure.models import Contact


class CapabilityXMLBuilder:
    def __init__(self, service: Service, force_version: str = None):
        self.service = service
        self.metadata = service.metadata

        self.service_type = service.servicetype.name
        self.service_version = force_version or service.servicetype.version

        self.proxy_operations_uri_template = "{}{}/service/metadata/".format(HTTP_OR_SSL, HOST_NAME) + "{}/operation?"
        self.proxy_legend_uri = "{}{}/service/metadata/{}/legend/".format(HTTP_OR_SSL, HOST_NAME, self.service.parent_service.metadata.id)

        self.namespaces = {
            "sld": XML_NAMESPACES["sld"],
            "xlink": XML_NAMESPACES["xlink"],
            "xsi": XML_NAMESPACES["xsi"],
        }

        self.default_ns = ""
        self.xlink_ns = "{" + XML_NAMESPACES["xlink"] + "}"
        self.xsi_ns = "{" + XML_NAMESPACES["xsi"] + "}"
        self.schema_location = ""

    @abstractmethod
    def generate_xml(self):
        xml_builder = None
        xml = ""

        if self.service_type == OGCServiceEnum.WMS.value:

            if self.service_version == OGCServiceVersionEnum.V_1_0_0.value:
                xml_builder = CapabilityWMS100Builder(self.service, self.service_version)

            elif self.service_version == OGCServiceVersionEnum.V_1_1_1.value:
                xml_builder = CapabilityWMS111Builder(self.service, self.service_version)

            elif self.service_version == OGCServiceVersionEnum.V_1_3_0.value:
                xml_builder = CapabilityWMS130Builder(self.service, self.service_version)

        elif self.service_type == OGCServiceEnum.WFS.value:

            if self.service_version == OGCServiceVersionEnum.V_1_0_0.value:
                xml_builder = CapabilityWFS100Builder(self.service, self.service_version)

            elif self.service_version == OGCServiceVersionEnum.V_1_1_0.value:
                xml_builder = CapabilityWFS110Builder(self.service, self.service_version)

            elif self.service_version == OGCServiceVersionEnum.V_2_0_0.value:
                xml_builder = CapabilityWFS200Builder(self.service, self.service_version)

            elif self.service_version == OGCServiceVersionEnum.V_2_0_2.value:
                xml_builder = CapabilityWFS202Builder(self.service, self.service_version)

        xml = xml_builder._generate_xml()
        return xml

    @abstractmethod
    def _generate_xml(self):
        """ Generate an xml capabilities document from the metadata object

        Args:
            metadata (Metadata): Metadata of the requested service
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
        print_debug_mode("Service creation took {} seconds".format((time() - start_time)))

        start_time = time()
        capability =  xml_helper.create_subelement(root, "{}Capability".format(self.default_ns))
        self._generate_capability_xml(capability)
        print_debug_mode("Capabilities creation took {} seconds".format(time() - start_time))

        start_time = time()
        xml = xml_helper.xml_to_string(root, pretty_print=False)
        print_debug_mode("Rendering to string took {} seconds".format((time() - start_time)))

        return xml

    def _generate_simple_elements_from_dict(self, upper_elem: Element, contents: dict):
        """ Generate multiple subelements of a xml object

        Variable `contents` contains key-value pairs of Element tag names and their text content.
        This method creates only simple xml elements, which have a tag name and the text value set.

        Args:
            upper_elem (_Element): The upper xml element
            contents (dict): The content dict
        Returns:
            nothing
        """
        for key, val in contents.items():
            k = key.format(self.default_ns)
            elem = xml_helper.create_subelement(upper_elem, k)
            xml_helper.write_text_to_element(elem, txt=val)


    @abstractmethod
    def _generate_service_xml(self, service_elem: Element):
        """ Generate the 'Service' subelement of a xml service object

        Args:
            service_elem (_Element): The service xml element
        Returns:
            nothing
        """
        md = self.metadata
        parent_md = md.service.parent_service.metadata

        # Create generic xml starter elements
        contents = OrderedDict({
            "{}Name": parent_md.identifier,
            "{}Title": parent_md.title,
            "{}Abstract": parent_md.abstract,
        })
        self._generate_simple_elements_from_dict(service_elem, contents)

        # KeywordList and keywords
        self._generate_keyword_xml(service_elem, parent_md)

        # OnlineResource
        self._generate_online_resource_xml(service_elem, parent_md)

        # Fill in the data for <ContactInformation>
        self._generate_service_contact_information_xml(service_elem)

        # Create generic xml end elements
        contents = OrderedDict({
            "{}Fees": parent_md.fees,
            "{}AccessConstraints": parent_md.access_constraints,
        })
        self._generate_simple_elements_from_dict(service_elem, contents)

    @abstractmethod
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
                "{}href".format(self.xlink_ns): self.proxy_operations_uri_template.format(md.id)
            }
        )

    @abstractmethod
    def _generate_service_contact_information_xml(self, service_elem):
        """ Generate the 'ContactInformation' subelement of a xml service object

        Args:
            service_elem (_Element): The service xml element
        Returns:
            nothing
        """
        md = self.metadata
        contact = md.contact
        contact: Contact

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

    @abstractmethod
    def _generate_service_contact_person_primary_xml(self, contact_person_primary_elem: Element):
        """ Generate the 'ContactPersonPrimary' subelement of a xml service object

        Args:
            contact_person_primary_elem (_Element): The <ContactPersonPrimary> xml element
        Returns:
            nothing
        """
        md = self.metadata
        contact = md.contact
        contact: Contact

        contents = OrderedDict({
            "{}ContactPerson": contact.person_name,
            "{}ContactPosition": "",
        })
        self._generate_simple_elements_from_dict(contact_person_primary_elem, contents)

    @abstractmethod
    def _generate_service_contact_address_xml(self, address_elem: Element):
        """ Generate the 'ContactAddress' subelement of a xml service object

        Args:
            address_elem (_Element): The address xml element
        Returns:
            nothing
        """
        md = self.metadata
        contact = md.contact
        contact: Contact

        contents = {
            "{}AddressType": contact.address_type,
            "{}Address": contact.address,
            "{}City": contact.city,
            "{}StateOrProvince": contact.state_or_province,
            "{}PostCode": contact.postal_code,
            "{}Country": contact.country,
        }
        self._generate_simple_elements_from_dict(address_elem, contents)

    @abstractmethod
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
            "{}VendorSpecificCapabilities": "",
            "{}UserDefinedSymbolization": "",
        })
        self._generate_simple_elements_from_dict(capability_elem, contents)

        request_elem = xml_helper.try_get_single_element_from_xml(
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("Request"),
            capability_elem
        )

        self._generate_capability_request_xml(request_elem)

        self._generate_capability_exception_xml(capability_elem)

        self._generate_capability_layer_xml(capability_elem, md)

    @abstractmethod
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
                related_metadata=self.metadata.service.parent_service.metadata,
            ).original_capability_document
        except ObjectDoesNotExist as e:
            return
        original_doc = xml_helper.parse_xml(original_doc)
        original_exception_elem = xml_helper.try_get_single_element_from_xml(
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("Capability")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("Exception"),
            original_doc
        )
        xml_helper.add_subelement(capability_elem, original_exception_elem)

    @abstractmethod
    def _generate_capability_request_xml(self, request_elem: Element):
        """ Generate the 'Request' subelement of a xml capability object

        Args:
            request_elem (_Element): The request xml element
        Returns:
            nothing
        """
        md = self.metadata
        service = md.service
        service: Service

        contents = OrderedDict({
            "{}GetCapabilities": "",
            "{}GetMap": "",
            "{}GetFeatureInfo": "",
        })

        additional_contents = OrderedDict({
            OGCOperationEnum.DESCRIBE_LAYER.value: {
                "get": service.describe_layer_uri_GET,
                "post": service.describe_layer_uri_POST,
            },
            OGCOperationEnum.GET_LEGEND_GRAPHIC.value: {
                "get": service.get_legend_graphic_uri_GET,
                "post": service.get_legend_graphic_uri_POST,
            },
            OGCOperationEnum.GET_STYLES.value: {
                "get": service.get_styles_uri_GET,
                "post": service.get_styles_uri_POST,
            },
            OGCOperationEnum.PUT_STYLES.value: {
                "get": "",  # ToDo: Implement putStyles in registration
                "post": "",
            },
        })

        # Put additional contents (if they are valid) in the regular contents
        for key, val in additional_contents.items():
            post_uri = val.get("post", "")
            get_uri = val.get("get", "")
            if len(post_uri) > 0 or len(get_uri) > 0:
                contents.update({"{}" + key: ""})

        # Create xml elements
        for key, val in contents.items():
            k = key.format(self.default_ns)
            elem = xml_helper.create_subelement(request_elem, k)
            self._generate_capability_operation_xml(elem)

    @abstractmethod
    def _generate_capability_operation_xml(self, operation_elem: Element):
        """ Generate the various operation subelements of a xml capability object

        Args:
            operation_elem (_Element): The operation xml element
        Returns:
            nothing
        """
        md = self.metadata
        service = md.service
        tag = QName(operation_elem).localname

        operations = OrderedDict({
            OGCOperationEnum.GET_CAPABILITIES.value: {
                "get": service.get_capabilities_uri_GET,
                "post": service.get_capabilities_uri_POST,
            },
            OGCOperationEnum.GET_MAP.value: {
                "get": service.get_map_uri_GET,
                "post": service.get_map_uri_POST,
            },
            OGCOperationEnum.GET_FEATURE_INFO.value: {
                "get": service.get_feature_info_uri_GET,
                "post": service.get_feature_info_uri_POST,
            },
            OGCOperationEnum.DESCRIBE_LAYER.value: {
                "get": service.describe_layer_uri_GET,
                "post": service.describe_layer_uri_POST,
            },
            OGCOperationEnum.GET_LEGEND_GRAPHIC.value: {
                "get": service.get_legend_graphic_uri_GET,
                "post": service.get_legend_graphic_uri_POST,
            },
            OGCOperationEnum.GET_STYLES.value: {
                "get": service.get_styles_uri_GET,
                "post": service.get_styles_uri_POST,
            },
            OGCOperationEnum.PUT_STYLES.value: {
                "get": "",  # ToDo: Implement putStyles in registration
                "post": "",
            },
        })

        uris = operations.get(tag, {"get": "","post": ""})
        get_uri = uris.get("get", "")
        post_uri = uris.get("post", "")

        if OGCOperationEnum.GET_CAPABILITIES.value in tag:
            # GetCapabilities is always set to our internal systems uri!
            get_uri = self.proxy_operations_uri_template.format(md.id)
            post_uri = self.proxy_operations_uri_template.format(md.id)

        # Add all mime types that are supported by this operation
        supported_formats = service.formats.filter(
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
        xml_helper.create_subelement(
            get_elem,
            "{}OnlineResource",
            attrib={
                "{}href".format(self.xlink_ns): get_uri
            }
        )
        xml_helper.create_subelement(
            post_elem,
            "{}OnlineResource",
            attrib={
                "{}href".format(self.xlink_ns): post_uri
            }
        )

    @abstractmethod
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
        elem = xml_helper.create_subelement(layer_elem, "{}Dimension".format(self.default_ns))
        xml_helper.write_text_to_element(elem, txt=md.dimension)

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

        self._generate_capability_version_specific(layer_elem, layer)

        # Recall the function with the children as input
        layer_children = layer.get_children()
        for layer_child in layer_children:
            self._generate_capability_layer_xml(layer_elem, layer_child.metadata)

    @abstractmethod
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

    @abstractmethod
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

    @abstractmethod
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
            bounding_geometry.transform(reference_system.code)
            bbox = list(bounding_geometry.extent)

            switch_axis = epsg_handler.switch_axis_order(self.service_type, self.service_version, reference_system.code)
            if switch_axis:
                for i in range(0, len(bbox), 2):
                    tmp = bbox[i]
                    bbox[i] = bbox[i+1]
                    bbox[i+1] = tmp

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

    @abstractmethod
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
        try:
            doc = Document.objects.get(
                related_metadata=dataset_md
            )
        except ObjectDoesNotExist as e:
            # If there is no related Metadata, we can skip this element
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

        uri = doc.related_metadata.metadata_url
        xml_helper.create_subelement(
            metadata_elem,
            "{}OnlineResource".format(self.default_ns),
            attrib={
                "{}type".format(self.xlink_ns): "simple",
                "{}href".format(self.xlink_ns): uri,
            }
        )

    @abstractmethod
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

            elem = xml_helper.create_subelement(
                legend_url_elem,
                "{}OnlineResource".format(self.default_ns),
                attrib={
                    "{}type".format(self.xlink_ns): "simple",
                    "{}href".format(self.xlink_ns): uri
                }
            )

    @abstractmethod
    def _generate_capability_version_specific(self, layer_elem: Element, layer: Layer):
        """ Has to be implemented in each CapabilityBuilder version specific implementation

        Args:
            layer_elem: The layer xml element
            layer: The layer object
        Returns:

        """
        pass


class CapabilityWMS100Builder(CapabilityXMLBuilder):
    def __init__(self, service: Service, force_version: str = None):
        super().__init__(service=service, force_version=force_version)
        self.schema_location = "http://schemas.opengis.net/wms/1.0.0/capabilities_1_0_0.dtd"




class CapabilityWMS111Builder(CapabilityXMLBuilder):
    """

    Creates a xml document, according to the specification of WMS 1.3.0
    http://schemas.opengis.net/wms/1.1.1/capabilities_1_1_1.xml

    """
    def __init__(self, service: Service, force_version: str = None):
        super().__init__(service=service, force_version=force_version)
        self.schema_location = "http://schemas.opengis.net/wms/1.1.1/capabilities_1_1_1.dtd"


    @abstractmethod
    def _generate_capability_version_specific(self, layer_elem: Element, layer: Layer):
        """ Generate different subelements of a layer xml object, which are specific for version 1.1.1

        Args:
            layer_elem (_Element): The layer xml element
        Returns:
            nothing
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
            layer_elem,
            "{}ScaleHint".format(self.default_ns),
            attrib=scale_hint
        )


class CapabilityWMS130Builder(CapabilityXMLBuilder):
    """

    Creates a xml document, according to the specification of WMS 1.3.0
    http://schemas.opengis.net/wms/1.3.0/capabilities_1_3_0.xsd

    """

    def __init__(self, service: Service, force_version: str = None):
        super().__init__(service=service, force_version=force_version)

        self.namespaces[None] = XML_NAMESPACES["wms"]
        self.default_ns = "{" + self.namespaces.get(None) + "}"
        self.schema_location = "http://schemas.opengis.net/wms/1.3.0/capabilities_1_3_0.xsd"

    @abstractmethod
    def _generate_service_xml(self, service_elem: Element):
        """ Generate the 'Service' subelement of a xml service object

        Args:
            service_elem (_Element): The service xml element
        Returns:
            nothing
        """
        md = self.metadata
        parent_md = md.service.parent_service.metadata

        #Create start of <Service> elements
        contents = OrderedDict({
            "{}Name": parent_md.identifier,
            "{}Title": parent_md.title,
            "{}Abstract": parent_md.abstract,
            "{}OnlineResource": self.proxy_operations_uri_template.format(parent_md.id),
        })
        self._generate_simple_elements_from_dict(service_elem, contents)

        # Add keywords to <wms:KeywordList>
        self._generate_keyword_xml(service_elem, parent_md)

        # Fill in the data for <ContactInformation>
        self._generate_service_contact_information_xml(service_elem)

        # Create end of <Service> elements
        contents = OrderedDict({
            "{}Fees": parent_md.fees,
            "{}AccessConstraints": parent_md.access_constraints,
            "{}MaxWidth": "",  # ToDo: Implement md.service.max_width in registration
            "{}MaxHeight": "",  # ToDo: Implement md.service.max_height in registration
        })
        self._generate_simple_elements_from_dict(service_elem, contents)

    @abstractmethod
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
            "{}ExtendedCapabilities": "",
        })
        self._generate_simple_elements_from_dict(capability_elem, contents)

        request_elem = xml_helper.try_get_single_element_from_xml(
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("Request"),
            capability_elem
        )

        self._generate_capability_request_xml(request_elem)

        self._generate_capability_exception_xml(capability_elem)

        self._generate_capability_layer_xml(capability_elem, md)

    @abstractmethod
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

            switch_axis = epsg_handler.switch_axis_order(self.service_type, self.service_version, reference_system.code)
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

    @abstractmethod
    def _generate_capability_version_specific(self, layer_elem: Element, layer: Layer):
        """ Generate different subelements of a layer xml object, which are specific for version 1.3.0

        Args:
            layer_elem (_Element): The layer xml element
        Returns:
            nothing
        """
        # MinScaleDenominator
        elem = xml_helper.create_subelement(layer_elem, "{}MinScaleDenominator".format(self.default_ns))
        xml_helper.write_text_to_element(elem, txt="")

        # MaxScaleDenominator
        elem = xml_helper.create_subelement(layer_elem, "{}MaxScaleDenominator".format(self.default_ns))
        xml_helper.write_text_to_element(elem, txt="")


class CapabilityWFS100Builder(CapabilityXMLBuilder):
    def __init__(self, service: Service, force_version: str = None):
        super().__init__(service=service, force_version=force_version)

    def _generate_xml(self):
        xml = ""
        return xml

class CapabilityWFS110Builder(CapabilityXMLBuilder):
    def __init__(self, service: Service, force_version: str = None):
        super().__init__(service=service, force_version=force_version)

    def _generate_xml(self):
        xml = ""
        return xml

class CapabilityWFS200Builder(CapabilityXMLBuilder):
    def __init__(self, service: Service, force_version: str = None):
        super().__init__(service=service, force_version=force_version)

    def _generate_xml(self):
        xml = ""
        return xml

class CapabilityWFS202Builder(CapabilityXMLBuilder):
    def __init__(self, service: Service, force_version: str = None):
        super().__init__(service=service, force_version=force_version)

    def _generate_xml(self):
        xml = ""
        return xml