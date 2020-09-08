# common classes for handling of WMS (OGC WebMapServices)
# http://www.opengeospatial.org/standards/wms
"""Common classes to handle WMS (OGC WebMapServices).

.. moduleauthor:: Armin Retterath <armin.retterath@gmail.com>

"""
import uuid
from abc import abstractmethod

import time

from threading import Thread

from celery import Task
from django.db import transaction

from MrMap.messages import SERVICE_NO_ROOT_LAYER
from service.settings import SERVICE_OPERATION_URI_TEMPLATE, PROGRESS_STATUS_AFTER_PARSING, SERVICE_METADATA_URI_TEMPLATE, HTML_METADATA_URI_TEMPLATE, service_logger
from MrMap.settings import EXEC_TIME_PRINT, MULTITHREADING_THRESHOLD, \
    XML_NAMESPACES, GENERIC_NAMESPACE_TEMPLATE
from MrMap import utils
from MrMap.utils import execute_threads
from service.helper.crypto_handler import CryptoHandler
from service.helper.enums import OGCServiceVersionEnum, MetadataEnum, OGCOperationEnum, ResourceOriginEnum, \
    MetadataRelationEnum
from service.helper.epsg_api import EpsgApi
from service.helper.iso.iso_19115_metadata_parser import ISOMetadata
from service.helper.ogc.ows import OGCWebService
from service.helper.ogc.layer import OGCLayer

from service.helper import xml_helper, task_helper
from service.models import ServiceType, Service, Metadata, MimeType, Keyword, \
    MetadataRelation, Style, ExternalAuthentication, ServiceUrl, RequestOperation
from structure.models import Organization, MrMapGroup
from structure.models import MrMapUser


class OGCWebMapServiceFactory:
    """ Creates the correct OGCWebMapService objects

    """
    def get_ogc_wms(self, version: OGCServiceVersionEnum, service_connect_url=None, external_auth: ExternalAuthentication = None):
        """ Returns the correct implementation of an OGCWebMapService according to the given version

        Args:
            version: The version number of the service
            service_connect_url: The capabilities request uri
        Returns:
            An OGCWebMapService
        """
        if version is OGCServiceVersionEnum.V_1_0_0:
            return OGCWebMapService_1_0_0(service_connect_url=service_connect_url, external_auth=external_auth)
        if version is OGCServiceVersionEnum.V_1_1_0:
            return OGCWebMapService_1_1_0(service_connect_url=service_connect_url, external_auth=external_auth)
        if version is OGCServiceVersionEnum.V_1_1_1:
            return OGCWebMapService_1_1_1(service_connect_url=service_connect_url, external_auth=external_auth)
        if version is OGCServiceVersionEnum.V_1_3_0:
            return OGCWebMapService_1_3_0(service_connect_url=service_connect_url, external_auth=external_auth)


class OGCWebMapService(OGCWebService):
    """Base class for OGC WebMapServices."""

    # define layers as array of OGCWebMapServiceLayer objects
    # Using None here to avoid mutable appending of infinite layers (python specific)
    # Using None here to avoid mutable appending of infinite layers (python specific)
    # For further details read: http://effbot.org/zone/default-values.htm
    layers = None
    epsg_api = EpsgApi()

    class Meta:
        abstract = True

    def get_layer_by_identifier(self, identifier: str):
        """ Returns the layer identified by the parameter 'identifier' as OGCWebMapServiceLayer object

        Args:
            identifier (str): The identifier as string
        Returns:
             layer_obj (OGCWebMapServiceLayer): The found and parsed layer
        """
        if self.service_capabilities_xml is None:
            # load xml, might have been forgotten
            self.get_capabilities()
        layer_xml = xml_helper.parse_xml(xml=self.service_capabilities_xml)
        layer_xml = xml_helper.try_get_element_from_xml(xml_elem=layer_xml, elem="//Layer/Name[text()='{}']/parent::Layer".format(identifier))
        if len(layer_xml) > 0:
            layer_xml = layer_xml[0]
        else:
            return None
        return self._start_single_layer_parsing(layer_xml)

    @abstractmethod
    def create_from_capabilities(self, metadata_only: bool = False, async_task: Task = None, external_auth: ExternalAuthentication = None):
        """ Fills the object with data from the capabilities document

        Returns:
             nothing
        """
        # get xml as iterable object
        xml_obj = xml_helper.parse_xml(xml=self.service_capabilities_xml)

        start_time = time.time()
        self.get_service_metadata_from_capabilities(xml_obj=xml_obj, async_task=async_task)

        # check if 'real' service metadata exist
        service_metadata_uri = xml_helper.try_get_text_from_xml_element(xml_elem=xml_obj, elem="//VendorSpecificCapabilities/inspire_vs:ExtendedCapabilities/inspire_common:MetadataUrl/inspire_common:URL")
        if service_metadata_uri is not None:
            self.get_service_metadata(uri=service_metadata_uri, async_task=async_task)

        service_logger.debug(EXEC_TIME_PRINT % ("service metadata", time.time() - start_time))

        # check possible operations on this service
        start_time = time.time()
        self.get_service_operations_and_formats(xml_obj)
        service_logger.debug(EXEC_TIME_PRINT % ("service operation checking", time.time() - start_time))

        # parse possible linked dataset metadata
        start_time = time.time()
        self.get_service_dataset_metadata(xml_obj=xml_obj)
        service_logger.debug(EXEC_TIME_PRINT % ("service iso metadata", time.time() - start_time))

        self.get_version_specific_metadata(xml_obj=xml_obj)

        if not metadata_only:
            start_time = time.time()
            self._parse_layers(xml_obj=xml_obj, async_task=async_task)
            service_logger.debug(EXEC_TIME_PRINT % ("layer metadata", time.time() - start_time))

    def get_service_operations_and_formats(self, xml_obj):
        """ Creates table records from <Capability><Request></Request></Capability contents

        Creates MimeType records

        Args:
            xml_obj: The xml document object
        Returns:

        """
        cap_request = xml_helper.try_get_single_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("Capability") +
            "/" + GENERIC_NAMESPACE_TEMPLATE.format("Request"),
            xml_obj
        )
        operations = cap_request.getchildren()
        for operation in operations:
            RequestOperation.objects.get_or_create(
                operation_name=operation.tag,
            )
            # Parse formats
            formats = xml_helper.try_get_element_from_xml(
                "./" + GENERIC_NAMESPACE_TEMPLATE.format("Format"),
                operation
            )
            formats = [f.text for f in formats]
            self.operation_format_map[operation.tag] = formats

    ### DATASET METADATA ###
    def parse_dataset_md(self, layer, layer_obj):
        # check for possible dataset metadata
        if self.has_dataset_metadata(layer):
            iso_metadata_xml_elements = xml_helper.try_get_element_from_xml(
                xml_elem=layer,
                elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("MetadataURL") +
                      "/" + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource")
            )
            for iso_xml in iso_metadata_xml_elements:
                iso_uri = xml_helper.get_href_attribute(xml_elem=iso_xml)
                try:
                    iso_metadata = ISOMetadata(uri=iso_uri, origin="capabilities")
                except Exception as e:
                    # there are iso metadatas that have been filled wrongly -> if so we will drop them
                    continue
                layer_obj.iso_metadata.append(iso_metadata)

    ### IDENTIFIER ###
    def parse_identifier(self, layer, layer_obj):
        layer_obj.identifier = xml_helper.try_get_text_from_xml_element(
            elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("Name"),
            xml_elem=layer)

    ### KEYWORDS ###
    def parse_keywords(self, layer, layer_obj):
        keywords = xml_helper.try_get_element_from_xml(
            elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("KeywordList") +
                 "/" + GENERIC_NAMESPACE_TEMPLATE.format("Keyword"),
            xml_elem=layer
        )
        for keyword in keywords:
            layer_obj.capability_keywords.append(keyword.text)

    ### ABSTRACT ###
    def parse_abstract(self, layer, layer_obj):
        layer_obj.abstract = xml_helper.try_get_text_from_xml_element(
            elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("Abstract"),
            xml_elem=layer
        )

    ### TITLE ###
    def parse_title(self, layer, layer_obj):
        layer_obj.title = xml_helper.try_get_text_from_xml_element(
            elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("Title"),
            xml_elem=layer
        )

    ### SRS/CRS     PROJECTION SYSTEM ###
    def parse_projection_system(self, layer, layer_obj):
        srs = xml_helper.try_get_element_from_xml(
            elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("SRS"),
            xml_elem=layer
        )
        for elem in srs:
            layer_obj.capability_projection_system.append(elem.text)

    ### BOUNDING BOX    LAT LON ###
    def parse_lat_lon_bounding_box(self, layer, layer_obj):
        try:
            bbox = xml_helper.try_get_element_from_xml(
                elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("LatLonBoundingBox"),
                xml_elem=layer
            )[0]
            attrs = ["minx", "miny", "maxx", "maxy"]
            for attr in attrs:
                val = bbox.get(attr, 0)
                if val is None:
                    val = 0
                layer_obj.capability_bbox_lat_lon[attr] = val
        except IndexError:
            pass

    ### BOUNDING BOX ###
    def parse_bounding_box_generic(self, layer, layer_obj, elem_name):
        bboxs = xml_helper.try_get_element_from_xml(
            elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("BoundingBox"),
            xml_elem=layer
        )
        for bbox in bboxs:
            srs = bbox.get(elem_name)
            srs_dict = {
                "minx": "",
                "miny": "",
                "maxx": "",
                "maxy": "",
            }
            attrs = ["minx", "miny", "maxx", "maxy"]
            for attr in attrs:
                srs_dict[attr] = bbox.get(attr)
            layer_obj.capability_bbox_srs[srs] = srs_dict

    def parse_bounding_box(self, layer, layer_obj):
        # switch depending on service version
        elem_name = "SRS"
        if self.service_version is OGCServiceVersionEnum.V_1_3_0:
            elem_name = "CRS"
        self.parse_bounding_box_generic(layer=layer, layer_obj=layer_obj, elem_name=elem_name)

    ### SCALE HINT ###
    def parse_scale_hint(self, layer, layer_obj):
        try:
            scales = xml_helper.try_get_element_from_xml(
                elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("ScaleHint"),
                xml_elem=layer
            )[0]
            attrs = ["min", "max"]
            for attr in attrs:
                layer_obj.capability_scale_hint[attr] = scales.get(attr)
        except IndexError:
            pass

    ### IS QUERYABLE ###
    def parse_queryable(self, layer, layer_obj):
            try:
                is_queryable = layer.get("queryable")
                if is_queryable is None:
                    is_queryable = False
                else:
                    is_queryable = utils.resolve_boolean_attribute_val(is_queryable)
                layer_obj.is_queryable = is_queryable
            except AttributeError:
                pass

    ### IS OPAQUE ###
    def parse_opaque(self, layer, layer_obj):
            try:
                is_opaque = layer.get("opaque")
                if is_opaque is None:
                    is_opaque = False
                else:
                    is_opaque = utils.resolve_boolean_attribute_val(is_opaque)
                layer_obj.is_opaque = is_opaque
            except AttributeError:
                pass

    ### IS CASCADED ###
    def parse_cascaded(self, layer, layer_obj):
            try:
                is_opaque = layer.get("cascaded")
                if is_opaque is None:
                    is_opaque = False
                else:
                    is_opaque = utils.resolve_boolean_attribute_val(is_opaque)
                layer_obj.is_cascaded = is_opaque
            except AttributeError:
                pass

    ### REQUEST URIS ###
    def parse_request_uris(self, layer, layer_obj):
        suffix_get = GENERIC_NAMESPACE_TEMPLATE.format("DCPType") + \
                     "/" + GENERIC_NAMESPACE_TEMPLATE.format("HTTP") + \
                     "/" + GENERIC_NAMESPACE_TEMPLATE.format("Get") + \
                     "/" + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource")
        suffix_post = GENERIC_NAMESPACE_TEMPLATE.format("DCPType") + \
                      "/" + GENERIC_NAMESPACE_TEMPLATE.format("HTTP") + \
                      "/" + GENERIC_NAMESPACE_TEMPLATE.format("Post") + \
                      "/" + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource")

        # shortens the usage of our constant values
        get_cap = OGCOperationEnum.GET_CAPABILITIES.value
        get_map = OGCOperationEnum.GET_MAP.value
        get_feat = OGCOperationEnum.GET_FEATURE_INFO.value
        descr_lay = OGCOperationEnum.DESCRIBE_LAYER.value
        get_leg = OGCOperationEnum.GET_LEGEND_GRAPHIC.value
        get_sty = OGCOperationEnum.GET_STYLES.value

        attributes = {
            "cap_GET": "//" + GENERIC_NAMESPACE_TEMPLATE.format(get_cap) + "/" + suffix_get,
            "cap_POST": "//" + GENERIC_NAMESPACE_TEMPLATE.format(get_cap) + "/" + suffix_post,
            "map_GET": "//" + GENERIC_NAMESPACE_TEMPLATE.format(get_map) + "/" + suffix_get,
            "map_POST": "//" + GENERIC_NAMESPACE_TEMPLATE.format(get_map) + "/" + suffix_post,
            "feat_GET": "//" + GENERIC_NAMESPACE_TEMPLATE.format(get_feat) + "/" + suffix_get,
            "feat_POST": "//" + GENERIC_NAMESPACE_TEMPLATE.format(get_feat) + "/" + suffix_post,
            "desc_GET": "//" + GENERIC_NAMESPACE_TEMPLATE.format(descr_lay) + "/" + suffix_get,
            "desc_POST": "//" + GENERIC_NAMESPACE_TEMPLATE.format(descr_lay) + "/" + suffix_post,
            "leg_GET": "//" + GENERIC_NAMESPACE_TEMPLATE.format(get_leg) + "/" + suffix_get,
            "leg_POST": "//" + GENERIC_NAMESPACE_TEMPLATE.format(get_leg) + "/" + suffix_post,
            "style_GET": "//" + GENERIC_NAMESPACE_TEMPLATE.format(get_sty) + "/" + suffix_get,
            "style_POST": "//" + GENERIC_NAMESPACE_TEMPLATE.format(get_sty) + "/" + suffix_post,
        }
        for key, val in attributes.items():
            try:
                tmp = layer.xpath(val)[0]
                link = xml_helper.get_href_attribute(tmp)
                attributes[key] = link
            except (AttributeError, IndexError) as error:
                attributes[key] = None

        layer_obj.get_capabilities_uri_GET = attributes.get("cap_GET")
        layer_obj.get_capabilities_uri_POST = attributes.get("cap_POST")
        layer_obj.get_map_uri_GET = attributes.get("map_GET")
        layer_obj.get_map_uri_POST = attributes.get("map_POST")
        layer_obj.get_feature_info_uri_GET = attributes.get("feat_GET")
        layer_obj.get_feature_info_uri_POST = attributes.get("feat_POST")
        layer_obj.describe_layer_uri_GET = attributes.get("desc_GET")
        layer_obj.describe_layer_uri_POST = attributes.get("desc_POST")
        layer_obj.get_legend_graphic_uri_GET = attributes.get("leg_GET")
        layer_obj.get_legend_graphic_uri_POST = attributes.get("leg_POST")
        layer_obj.get_styles_uri_GET = attributes.get("style_GET")
        layer_obj.get_styles_uri_POST = attributes.get("style_POST")

    ### FORMATS ###
    def parse_formats(self, layer, layer_obj):
        actions = ["GetMap", "GetCapabilities", "GetFeatureInfo", "DescribeLayer", "GetLegendGraphic", "GetStyles"]
        results = {}
        for action in actions:
            try:
                results[action] = []
                format_list = xml_helper.try_get_element_from_xml(
                    elem="//" + GENERIC_NAMESPACE_TEMPLATE.format(action) +
                         "/" + GENERIC_NAMESPACE_TEMPLATE.format("Format"),
                    xml_elem=layer
                )
                for format in format_list:
                    results[action].append(format.text)
            except AttributeError:
                pass
        layer_obj.format_list = results

    ### DIMENSIONS ###
    def parse_dimension(self, layer, layer_obj):
        dim_list = []
        try:
            dims = xml_helper.try_get_element_from_xml(
                elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("Dimension"),
                xml_elem=layer
            )
            for dim in dims:
                ext = xml_helper.try_get_single_element_from_xml(
                    elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("Extent")+ '[@name="' + dim.get('name') + '"]',
                    xml_elem=layer
                )
                dim_dict = {
                    "type": dim.get("name"),
                    "units": dim.get("units"),
                    "extent": ext.text,
                }
                dim_list.append(dim_dict)
        except (IndexError, AttributeError) as error:
            pass
        layer_obj.dimension_list = dim_list

    ### STYLES ###
    def parse_style(self, layer, layer_obj):
        style_xml = xml_helper.try_get_single_element_from_xml(
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("Style"),
            layer
        )

        if style_xml is None:
            # no <Style> element found
            return

        style_obj = Style()

        style_obj.name = xml_helper.try_get_text_from_xml_element(
            style_xml,
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("Name")
        )
        style_obj.title = xml_helper.try_get_text_from_xml_element(
            style_xml,
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("Title")
        )
        legend_elem = xml_helper.try_get_single_element_from_xml(
            elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("LegendURL") +
                 "/" + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource"),
            xml_elem=style_xml
        )
        style_obj.legend_uri = xml_helper.get_href_attribute(legend_elem)
        style_obj.width = int(xml_helper.try_get_attribute_from_xml_element(
            style_xml,
            "width",
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("LegendURL")
        ) or 0)
        style_obj.height = int(xml_helper.try_get_attribute_from_xml_element(
            style_xml,
            "height",
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("LegendURL")
        ) or 0)
        style_obj.mime_type = MimeType.objects.filter(
            mime_type=xml_helper.try_get_text_from_xml_element(
                style_xml,
                "./" + GENERIC_NAMESPACE_TEMPLATE.format("LegendURL") +
                "/ " + GENERIC_NAMESPACE_TEMPLATE.format("Format"))
        ).first()

        layer_obj.style = style_obj

    def _start_single_layer_parsing(self, layer_xml):
        """ Runs the complete parsing process for a single layer

        Args:
            layer_xml: The xml element of the desired layer
        Returns:
             layer_obj (OGCWebMapServiceLayer): The layer object containing all metadata information
        """
        layer_obj = OGCWebMapServiceLayer()
        # iterate over single parsing functions -> improves maintainability
        parse_functions = [
            self.parse_keywords,
            self.parse_abstract,
            self.parse_title,
            self.parse_projection_system,
            self.parse_lat_lon_bounding_box,
            self.parse_bounding_box,
            self.parse_scale_hint,
            self.parse_queryable,
            self.parse_opaque,
            self.parse_cascaded,
            self.parse_request_uris,
            self.parse_dimension,
            self.parse_style,
            self.parse_identifier,
            self.parse_dataset_md,
        ]
        for func in parse_functions:
            func(layer=layer_xml, layer_obj=layer_obj)

        return layer_obj

    def _parse_single_layer(self, layer, parent, position, step_size: float = None, async_task: Task = None):
        """ Parses data from an xml <Layer> element into the OGCWebMapLayer object.

        Runs recursive through own children for further parsing

        Args:
            layer: The layer xml element
            parent: The parent OGCWebMapLayer object
            position: The current position of this layer object in relation to it's siblings
        Returns:
            nothing
        """
        # iterate over all top level layer and find their children
        layer_obj = self._start_single_layer_parsing(layer)

        if step_size is not None and async_task is not None:
            task_helper.update_progress_by_step(async_task, step_size)
            task_helper.update_service_description(async_task, None, "Parsing {}".format(layer_obj.title))

        layer_obj.parent = parent
        layer_obj.position = position
        if self.layers is None:
            self.layers = []
        self.layers.append(layer_obj)
        sublayers = xml_helper.try_get_element_from_xml(
            elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("Layer"),
            xml_elem=layer
        )
        if parent is not None:
            parent.child_layers.append(layer_obj)
        position += 1

        self._parse_layers_recursive(layers=sublayers, parent=layer_obj, step_size=step_size, async_task=async_task)

    def _parse_layers_recursive(self, layers, parent=None, position=0, step_size: float = None, async_task: Task = None):
        """ Recursive Iteration over all children and subchildren.

        Creates OGCWebMapLayer objects for each xml layer and fills it with the layer content.

        Args:
            layers: An array of layers (In fact the children of the parent layer)
            parent: The parent layer. If no parent exist it means we are in the root layer
            position: The position inside the layer tree, which is more like an order number
        Returns:
            nothing
        """

        # decide whether to user multithreading or iterative approach
        if len(layers) > MULTITHREADING_THRESHOLD:
            thread_list = []
            for layer in layers:
                thread_list.append(
                    Thread(target=self._parse_single_layer,
                           args=(layer, parent, position))
                )
                position += 1
            execute_threads(thread_list)
        else:
            for layer in layers:
                self._parse_single_layer(layer, parent, position, step_size=step_size, async_task=async_task)
                position += 1

    def _parse_layers(self, xml_obj, async_task: Task = None):
        """ Parses all layers of a service and creates OGCWebMapLayer objects from each.

        Uses recursion on the inside to get all children.

        Args:
            xml_obj: The iterable xml tree
        Returns:
             nothing
        """
        # get most upper parent layer, which normally lives directly in <Capability>
        layers = xml_helper.try_get_element_from_xml(
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("Capability") +
                 "/" + GENERIC_NAMESPACE_TEMPLATE.format("Layer"),
            xml_elem=xml_obj
        )
        total_layers = xml_helper.try_get_element_from_xml(
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("Layer"),
            xml_elem=xml_obj
        )

        # calculate the step size for an async call
        # 55 is the diff from the last process update (10) to the next static one (65)
        len_layers = len(total_layers)
        if len_layers == 0:
            # No division by zero!
            len_layers = 1
        step_size = float(PROGRESS_STATUS_AFTER_PARSING / len_layers)
        service_logger.debug("Total number of layers: {}. Step size: {}".format(len_layers, step_size))

        self._parse_layers_recursive(layers, step_size=step_size, async_task=async_task)

    def get_service_metadata_from_capabilities(self, xml_obj, async_task: Task = None):
        """ Parses all <Service> element information which can be found in every wms specification since 1.0.0

        Args:
            xml_obj: The iterable xml object tree
            async_task: The task object
        Returns:
            Nothing
        """
        service_xml = xml_helper.try_get_single_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("Service"),
            xml_obj
        )

        self.service_file_identifier = xml_helper.try_get_text_from_xml_element(
            service_xml,
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("Name")
        )
        self.service_identification_abstract = xml_helper.try_get_text_from_xml_element(
            service_xml,
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("Abstract")
        )
        self.service_identification_title = xml_helper.try_get_text_from_xml_element(
            service_xml,
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("Title")
        )

        if async_task is not None:
            task_helper.update_service_description(async_task, self.service_identification_title, phase_descr="Parsing main capabilities")

        self.service_identification_fees = xml_helper.try_get_text_from_xml_element(
            service_xml,
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("Fees")
        )
        self.service_identification_accessconstraints = xml_helper.try_get_text_from_xml_element(
            service_xml,
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("AccessConstraints")
        )
        self.service_provider_providername = xml_helper.try_get_text_from_xml_element(
            service_xml,
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("ContactInformation")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("ContactPersonPrimary")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("ContactOrganization")

        )
        authority_elem = xml_helper.try_get_single_element_from_xml(
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("AuthorityURL"),
            xml_elem=xml_obj
        )
        self.service_provider_url = xml_helper.get_href_attribute(authority_elem)
        self.service_provider_contact_contactinstructions = xml_helper.try_get_text_from_xml_element(
            xml_elem=service_xml,
            elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("ContactInformation")
        )
        self.service_provider_responsibleparty_individualname = xml_helper.try_get_text_from_xml_element(
            service_xml,
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("ContactInformation")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("ContactPersonPrimary")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("ContactPerson")
        )
        self.service_provider_responsibleparty_positionname = xml_helper.try_get_text_from_xml_element(
            service_xml,
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("ContactInformation")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("ContactPersonPrimary")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("ContactPosition")
        )
        self.service_provider_telephone_voice = xml_helper.try_get_text_from_xml_element(
            service_xml,
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("ContactInformation")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("ContactVoiceTelephone")
        )
        self.service_provider_telephone_facsimile = xml_helper.try_get_text_from_xml_element(
            service_xml,
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("ContactInformation")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("ContactFacsimileTelephone")
        )
        self.service_provider_address_electronicmailaddress = xml_helper.try_get_text_from_xml_element(
            service_xml,
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("ContactInformation")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("ContactElectronicMailAddress")
        )

        keywords = xml_helper.try_get_element_from_xml(
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("KeywordList")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("Keyword"),
            service_xml
        )

        kw = []
        for keyword in keywords:
            if keyword is None:
                continue
            kw.append(keyword.text)
        self.service_identification_keywords = kw

        online_res_elem = xml_helper.try_get_single_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("Service") +
            "/" + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource"),
            xml_obj)
        link = xml_helper.get_href_attribute(online_res_elem)
        self.service_provider_onlineresource_linkage = link

        self.service_provider_address_country = xml_helper.try_get_text_from_xml_element(
            service_xml,
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("ContactInformation") +
            "/" + GENERIC_NAMESPACE_TEMPLATE.format("ContactAddress") +
            "/" + GENERIC_NAMESPACE_TEMPLATE.format("Country")
        )
        self.service_provider_address_postalcode = xml_helper.try_get_text_from_xml_element(
            service_xml,
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("ContactInformation") +
             "/" + GENERIC_NAMESPACE_TEMPLATE.format("ContactAddress") +
             "/" + GENERIC_NAMESPACE_TEMPLATE.format("PostCode")
        )
        self.service_provider_address_city = xml_helper.try_get_text_from_xml_element(
            service_xml,
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("ContactInformation") +
             "/" + GENERIC_NAMESPACE_TEMPLATE.format("ContactAddress") +
             "/" + GENERIC_NAMESPACE_TEMPLATE.format("City")
        )
        self.service_provider_address_state_or_province = xml_helper.try_get_text_from_xml_element(
            service_xml,
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("ContactInformation") +
             "/" + GENERIC_NAMESPACE_TEMPLATE.format("ContactAddress") +
             "/" + GENERIC_NAMESPACE_TEMPLATE.format("StateOrProvince")
        )
        self.service_provider_address = xml_helper.try_get_text_from_xml_element(
            service_xml,
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("ContactInformation") +
             "/" + GENERIC_NAMESPACE_TEMPLATE.format("ContactAddress") +
             "/" + GENERIC_NAMESPACE_TEMPLATE.format("Address")
        )

        # parse request uris from capabilities document
        self.parse_request_uris(xml_obj, self)

    @transaction.atomic
    def create_service_model_instance(self, user: MrMapUser, register_group: MrMapGroup, register_for_organization: Organization, external_auth: ExternalAuthentication = None, is_update_candidate_for: Service = None):
        """ Persists the web map service and all of its related content and data

        Args:
            user (MrMapUser): The action performing user
            register_group (MrMapGroup): The group for which the service shall be registered
            register_for_organization (Organization): The organization for which the service shall be registered
            external_auth (ExternalAuthentication): An external authentication object holding information
        Returns:
             service (Service): Service instance, contains all information, ready for persisting!

        """
        orga_published_for = register_for_organization
        group = register_group

        # Contact
        contact = self._create_organization_contact_record()

        # Metadata
        metadata = self._create_metadata_record(contact, group)

        # Process external authentication
        self._process_external_authentication(metadata, external_auth)

        # Service
        service = self._create_service_record(group, orga_published_for, metadata, is_update_candidate_for)

        # Additionals (keywords, mimetypes, ...)
        self._create_additional_records(service, metadata, group)

        # Begin creation of Layer records. Calling the found root layer will
        # iterate through all parent-child related layer objects
        try:
            root_layer = self.layers[0]
            root_layer.create_layer_record(
                parent_service=service,
                group=group,
                user=user,
                parent_layer=None,
                epsg_api=self.epsg_api
            )
        except KeyError:
            raise IndexError(SERVICE_NO_ROOT_LAYER)
        return service

    def _create_organization_contact_record(self):
        """ Creates a Organization record from the OGCWebMapService

        Returns:
             contact (Organization): The persisted organization contact record
        """
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
        """ Creates a Metadata record from the OGCWebMapService

        Args:
            contact (Organization): The contact organization for this metadata record
            group (MrMapGroup): The owner/creator group
        Returns:
             metadata (Metadata): The persisted metadata record
        """
        metadata = Metadata()
        md_type = MetadataEnum.SERVICE.value
        metadata.metadata_type = md_type
        if self.service_file_iso_identifier is None:
            # We didn't found any file identifier in the document -> we create one
            self.service_file_iso_identifier = uuid.uuid4()
        metadata.title = self.service_identification_title
        metadata.abstract = self.service_identification_abstract
        metadata.online_resource = self.service_provider_onlineresource_linkage
        metadata.capabilities_original_uri = self.service_connect_url
        metadata.access_constraints = self.service_identification_accessconstraints
        metadata.fees = self.service_identification_fees
        if self.service_bounding_box is not None:
            metadata.bounding_geometry = self.service_bounding_box
        metadata.identifier = self.service_file_identifier
        metadata.is_active = False
        metadata.created_by = group
        metadata.contact = contact

        # Save metadata instance to be able to add M2M entities
        metadata.save()

        return metadata

    def _create_service_record(self, group: MrMapGroup, orga_published_for: Organization, metadata: Metadata, is_update_candidate_for: Service):
        """ Creates a Service object from the OGCWebFeatureService object

        Args:
            group (MrMapGroup): The owner/creator group
            orga_published_for (Organization): The organization for which the service is published
            orga_publisher (Organization): THe organization that publishes
            metadata (Metadata): The describing metadata
        Returns:
             service (Service): The persisted service object
        """

        ## Create ServiceType record if it doesn't exist yet
        service_type = ServiceType.objects.get_or_create(
            name=self.service_type.value,
            version=self.service_version.value
        )[0]
        service = Service()
        service.availability = 0.0
        service.is_available = False
        service.service_type = service_type
        service.published_for = orga_published_for
        service.created_by = group
        operation_urls = [
            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_CAPABILITIES.value,
                url=self.get_capabilities_uri_GET,
                method="Get"
            )[0],
            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_CAPABILITIES.value,
                url=self.get_capabilities_uri_POST,
                method="Post"
            )[0],

            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_FEATURE_INFO.value,
                url=self.get_feature_info_uri_GET,
                method="Get"
            )[0],
            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_FEATURE_INFO.value,
                url=self.get_feature_info_uri_POST,
                method="Post"
            )[0],

            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.DESCRIBE_LAYER.value,
                url=self.describe_layer_uri_GET,
                method="Get"
            )[0],
            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.DESCRIBE_LAYER.value,
                url=self.describe_layer_uri_POST,
                method="Post"
            )[0],

            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_STYLES.value,
                url=self.get_styles_uri_GET,
                method="Get"
            )[0],
            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_STYLES.value,
                url=self.get_styles_uri_POST,
                method="Post"
            )[0],

            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_LEGEND_GRAPHIC.value,
                url=self.get_legend_graphic_uri_GET,
                method="Get"
            )[0],
            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_LEGEND_GRAPHIC.value,
                url=self.get_legend_graphic_uri_POST,
                method="Post"
            )[0],

            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_MAP.value,
                url=self.get_map_uri_GET,
                method="Get"
            )[0],
            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_MAP.value,
                url=self.get_map_uri_POST,
                method="Post"
            )[0],

        ]

        service.operation_urls.add(*operation_urls)
        service.metadata = metadata
        service.is_root = True
        service.is_update_candidate_for=is_update_candidate_for

        service.save()

        # Persist capabilities document
        service.persist_original_capabilities_doc(self.service_capabilities_xml)

        return service

    def _create_additional_records(self, service: Service, metadata: Metadata, group: MrMapGroup):
        """ Creates additional records like linked service metadata, keywords or MimeTypes/Formats

        Args:
            service (Service): The service record
            metadata (Metadata): THe metadata record
        Returns:

        """
        # Keywords
        for kw in self.service_identification_keywords:
            if kw is None:
                continue
            keyword = Keyword.objects.get_or_create(keyword=kw)[0]
            metadata.keywords.add(keyword)

        # MimeTypes / Formats
        for operation, formats in self.operation_format_map.items():
            for format in formats:
                mime_type = MimeType.objects.get_or_create(
                    operation=operation,
                    mime_type=format,
                    created_by=group
                )[0]
                metadata.formats.add(mime_type)

        # Check for linked service metadata that might be found during parsing
        if self.linked_service_metadata is not None:
            service.linked_service_metadata = self.linked_service_metadata.to_db_model(MetadataEnum.SERVICE.value, created_by=metadata.created_by)
            md_relation = MetadataRelation()
            md_relation.metadata_to = service.linked_service_metadata
            md_relation.origin = ResourceOriginEnum.CAPABILITIES.value
            md_relation.relation_type = MetadataRelationEnum.VISUALIZES.value
            md_relation.save()
            metadata.related_metadata.add(md_relation)


class OGCWebMapServiceLayer(OGCLayer):
    """ The OGCWebMapServiceLayer class

    """


class OGCWebMapService_1_0_0(OGCWebMapService):
    """ The WMS class for standard version 1.0.0

    """
    def __init__(self, service_connect_url, external_auth: ExternalAuthentication):
        super().__init__(service_connect_url=service_connect_url, external_auth=external_auth)
        self.service_version = OGCServiceVersionEnum.V_1_0_0
        XML_NAMESPACES["schemaLocation"] = "http://schemas.opengis.net/wms/1.0.0/capabilities_1_0_0.xml"

    def parse_formats(self, layer, layer_obj):
        actions = ["Map", "Capabilities", "FeatureInfo"]
        results = {}
        for action in actions:
            try:
                results[action] = []
                format_list = layer.xpath(
                    "//" + GENERIC_NAMESPACE_TEMPLATE.format("Request") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format(action) +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("Format")
                ).getchildren()
                for format in format_list:
                    results[action].append(format.text)
            except AttributeError:
                pass
        layer_obj.format_list = results

    def get_version_specific_metadata(self, xml_obj):
        service_xml = xml_helper.try_get_single_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("Service"),
            xml_obj
        )
        # Keywords
        # Keywords are not separated in single <Keyword> elements.
        # There is a single <Keywords> element, containing a continuous string, where keywords are space separated
        keywords = xml_helper.try_get_text_from_xml_element(
            service_xml,
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("Keywords")
        )
        keywords = keywords.split(" ")
        tmp = []
        for kw in keywords:
            kw = kw.strip()
            if len(kw) != 0:
               tmp.append(kw)
        self.service_identification_keywords = tmp

        # Online Resource
        # The online resource is not found as an attribute of an element.
        # It is the text of the <OnlineResource> element
        online_resource = xml_helper.try_get_text_from_xml_element(
            service_xml,
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource")
        )
        self.service_provider_onlineresource_linkage = online_resource


class OGCWebMapService_1_1_0(OGCWebMapService):
    """ The WMS class for standard version 1.1.0

    """
    def __init__(self, service_connect_url, external_auth: ExternalAuthentication):
        super().__init__(service_connect_url=service_connect_url, external_auth=external_auth)
        self.service_version = OGCServiceVersionEnum.V_1_1_0
        XML_NAMESPACES["schemaLocation"] = "http://schemas.opengis.net/wms/1.1.0/capabilities_1_1_0.xml"

    def get_version_specific_metadata(self, xml_obj):
        # No version specific implementation needed
        pass


class OGCWebMapService_1_1_1(OGCWebMapService):
    """ The WMS class for standard version 1.1.1

    """
    def __init__(self, service_connect_url, external_auth: ExternalAuthentication):
        super().__init__(service_connect_url=service_connect_url, external_auth=external_auth)
        self.service_version = OGCServiceVersionEnum.V_1_1_1
        XML_NAMESPACES["default"] = XML_NAMESPACES["wms"]
        XML_NAMESPACES["schemaLocation"] = "http://schemas.opengis.net/wms/1.1.1/capabilities_1_1_1.xml"

    def get_version_specific_metadata(self, xml_obj):
        # No version specific implementation needed
        pass



class OGCWebMapService_1_3_0(OGCWebMapService):
    """ The WMS class for standard version 1.3.0

    """

    def __init__(self, service_connect_url, external_auth: ExternalAuthentication):
        super().__init__(service_connect_url=service_connect_url, external_auth=external_auth)
        self.service_version = OGCServiceVersionEnum.V_1_3_0
        self.layer_limit = None
        self.max_width = None
        self.max_height = None

        XML_NAMESPACES["schemaLocation"] = "http://schemas.opengis.net/wms/1.3.0/capabilities_1_3_0.xsd"
        XML_NAMESPACES["default"] = XML_NAMESPACES["wms"]

    def parse_lat_lon_bounding_box(self, layer, layer_obj):
        """ Version specific implementation of the bounding box parsing

        Args:
            layer: The xml element which holds the layer info (parsing from)
            layer_obj: The backend model which holds the layer data (parsing to)
        Returns:
             nothing
        """
        try:
            bbox = xml_helper.try_get_element_from_xml(
                "./" + GENERIC_NAMESPACE_TEMPLATE.format("EX_GeographicBoundingBox"),
                layer)[0]
            attrs = {
                "westBoundLongitude": "minx",
                "eastBoundLongitude": "maxx",
                "southBoundLatitude": "miny",
                "northBoundLatitude": "maxy",
            }
            for key, val in attrs.items():
                tmp = xml_helper.try_get_text_from_xml_element(
                    xml_elem=bbox,
                    elem="./" + GENERIC_NAMESPACE_TEMPLATE.format(key)
                )
                if tmp is None:
                    tmp = 0
                layer_obj.capability_bbox_lat_lon[val] = tmp
        except IndexError:
            pass

    def parse_projection_system(self, layer, layer_obj):
        """ Version specific implementation of the projection system parsing

        Args:
            layer: The xml element which holds the layer info (parsing from)
            layer_obj: The backend model which holds the layer data (parsing to)
        Returns:
             nothing
        """
        crs = xml_helper.try_get_element_from_xml(
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("CRS"),
            layer
        )
        for elem in crs:
            layer_obj.capability_projection_system.append(elem.text)

    def parse_dimension(self, layer, layer_obj):
        """ The version specific implementation of the dimension parsing

        Args:
            layer: The xml element which holds the layer info (parsing from)
            layer_obj: The backend model which holds the layer data (parsing to)
        Returns:
             nothing
        """
        dim_list = []
        try:
            dims = xml_helper.try_get_element_from_xml(
                elem="./" + GENERIC_NAMESPACE_TEMPLATE.format("Dimension"),
                xml_elem=layer
            )
            for dim in dims:
                dim_dict = {
                    "type": dim.get("name"),
                    "units": dim.get("units"),
                    "extent": dim.text,
                }
                dim_list.append(dim_dict)

        except (IndexError, AttributeError) as error:
            pass
        layer_obj.dimension_list = dim_list

    def get_version_specific_service_metadata(self, xml_obj):
        """ The version specific implementation of service metadata parsing

        There are elements in the <Service> part fo the GetCapabilities document which are not covered in the regular
        service metadata parsing due to the fact, they are only used in the newest version of WMS which is by far not
        regularly used.

        Args:
            xml_obj: The xml element
        Returns:
             nothing
        """
        # layer limit is new
        layer_limit = xml_helper.try_get_text_from_xml_element(
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("LayerLimit"),
            xml_elem=xml_obj
        )
        self.layer_limit = layer_limit

        # max height and width is new
        max_width = xml_helper.try_get_text_from_xml_element(
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("MaxWidth"),
            xml_elem=xml_obj
        )
        self.max_width = max_width

        max_height = xml_helper.try_get_text_from_xml_element(
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("MaxHeight"),
            xml_elem=xml_obj
        )
        self.max_height = max_height

        self._parse_layers(xml_obj=xml_obj)