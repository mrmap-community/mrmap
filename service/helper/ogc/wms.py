# common classes for handling of WMS (OGC WebMapServices)
# http://www.opengeospatial.org/standards/wms
"""Common classes to handle WMS (OGC WebMapServices).

.. moduleauthor:: Armin Retterath <armin.retterath@gmail.com>

"""
import uuid
from abc import abstractmethod

import time

from copy import copy
from threading import Thread

from celery import Task
from django.contrib.gis.geos import Polygon
from django.db import transaction

from service.settings import EXTERNAL_AUTHENTICATION_FILEPATH, SERVICE_OPERATION_URI_TEMPLATE, \
    SERVICE_METADATA_URI_TEMPLATE, HTML_METADATA_URI_TEMPLATE
from MapSkinner.settings import EXEC_TIME_PRINT, MULTITHREADING_THRESHOLD, \
    PROGRESS_STATUS_AFTER_PARSING, XML_NAMESPACES, HTTP_OR_SSL, HOST_NAME, GENERIC_NAMESPACE_TEMPLATE
from MapSkinner import utils
from MapSkinner.utils import execute_threads, print_debug_mode
from service.helper.crypto_handler import CryptoHandler
from service.helper.enums import OGCServiceVersionEnum, MetadataEnum, OGCOperationEnum
from service.helper.epsg_api import EpsgApi
from service.helper.iso.iso_metadata import ISOMetadata
from service.helper.ogc.ows import OGCWebService
from service.helper.ogc.layer import OGCLayer

from service.helper import xml_helper, task_helper
from service.models import ServiceType, Service, Metadata, Layer, MimeType, Keyword, ReferenceSystem, \
    MetadataRelation, MetadataOrigin, MetadataType, Style, ExternalAuthentication, Dimension
from service.settings import MD_RELATION_TYPE_VISUALIZES, MD_RELATION_TYPE_DESCRIBED_BY, ALLOWED_SRS
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

        print_debug_mode(EXEC_TIME_PRINT % ("service metadata", time.time() - start_time))

        # check possible operations on this service
        start_time = time.time()
        self.get_service_operations(xml_obj)
        print_debug_mode(EXEC_TIME_PRINT % ("service operation checking", time.time() - start_time))

        # parse possible linked dataset metadata
        start_time = time.time()
        self.get_service_dataset_metadata(xml_obj=xml_obj)
        print_debug_mode(EXEC_TIME_PRINT % ("service iso metadata", time.time() - start_time))

        self.get_version_specific_metadata(xml_obj=xml_obj)

        if not metadata_only:
            start_time = time.time()
            self._parse_layers(xml_obj=xml_obj, async_task=async_task)
            print_debug_mode(EXEC_TIME_PRINT % ("layer metadata", time.time() - start_time))

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
        if layer_obj.identifier is None:
            u = str(uuid.uuid4())
            sec_handler = CryptoHandler()
            layer_obj.identifier = sec_handler.sha256(u)

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
            self.parse_formats,
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
        if step_size is not None and async_task is not None:
            task_helper.update_progress_by_step(async_task, step_size)

        # iterate over all top level layer and find their children
        layer_obj = self._start_single_layer_parsing(layer)
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
            parent.child_layer.append(layer_obj)
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
        print_debug_mode("Total number of layers: {}. Step size: {}".format(len_layers, step_size))

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
            task_helper.update_service_description(async_task, self.service_identification_title)

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

    def _create_single_layer_model_instance(self, layer_obj, layers: list, service_type: ServiceType, wms: Service, creator: MrMapGroup, publisher: Organization,
                                            published_for: Organization, root_md: Metadata, user: MrMapUser, contact, parent=None):
        """ Transforms a OGCWebMapLayer object to Layer model (models.py)

        Args:
            layer_obj (OGCWebMapServiceLayer): The OGCWebMapLayer object which holds all data
            layers (list): A list of layers
            service_type (ServiceType): The type of the service this function has to deal with
            wms (Service): The root or parent service which holds all these layers
            creator (MrMapGroup): The group that started the registration process
            publisher (Organization): The organization that publishes the service
            published_for (Organization): The organization for which the first organization publishes this data (e.g. 'in the name of')
            root_md (Metadata): The metadata of the root service (parameter 'wms')
            user (MrMapUser): The performing user
            contact (Contact): The contact object (Organization)
            parent: The parent layer object to this layer
        Returns:
            nothing
        """
        metadata = Metadata()
        md_type = MetadataType.objects.get_or_create(type=MetadataEnum.LAYER.value)[0]
        metadata.metadata_type = md_type
        metadata.title = layer_obj.title
        metadata.uuid = uuid.uuid4()
        metadata.abstract = layer_obj.abstract
        metadata.online_resource = root_md.online_resource
        metadata.capabilities_original_uri = root_md.capabilities_original_uri
        metadata.capabilities_uri = root_md.capabilities_original_uri
        metadata.identifier = layer_obj.identifier
        metadata.contact = contact
        metadata.access_constraints = root_md.access_constraints
        metadata.is_active = False
        metadata.created_by = creator
        metadata.capabilities_uri = SERVICE_OPERATION_URI_TEMPLATE.format(metadata.id) + "request={}".format(
            OGCOperationEnum.GET_CAPABILITIES.value)
        metadata.service_metadata_uri = SERVICE_METADATA_URI_TEMPLATE.format(metadata.id)
        metadata.html_metadata_uri = HTML_METADATA_URI_TEMPLATE.format(metadata.id)

        metadata.save()

        # Keywords
        for kw in layer_obj.capability_keywords:
            keyword = Keyword.objects.get_or_create(keyword=kw)[0]
            metadata.keywords.add(keyword)

        # handle reference systems
        for sys in layer_obj.capability_projection_system:
            parts = self.epsg_api.get_subelements(sys)
            # check if this srs is allowed for us. If not, skip it!
            if parts.get("code") not in ALLOWED_SRS:
                continue
            ref_sys = ReferenceSystem.objects.get_or_create(code=parts.get("code"), prefix=parts.get("prefix"))[0]
            metadata.reference_system.add(ref_sys)

        # Layer
        layer = Layer()
        layer.uuid = uuid.uuid4()
        layer.metadata = metadata
        layer.identifier = layer_obj.identifier
        layer.servicetype = service_type
        layer.position = layer_obj.position
        layer.parent_layer = parent
        layer.parent_service = wms
        layer.is_queryable = layer_obj.is_queryable
        layer.is_cascaded = layer_obj.is_cascaded
        layer.registered_by = creator
        layer.is_opaque = layer_obj.is_opaque
        layer.scale_min = layer_obj.capability_scale_hint.get("min")
        layer.scale_max = layer_obj.capability_scale_hint.get("max")

        # Save model so M2M relations can be used
        layer.save()

        # If parent layer is a real layer, we add the current layer as a child to the parent layer
        if layer.parent_layer is not None:
            layer.parent_layer.child_layer.add(layer)

        if layer_obj.style is not None:
            layer.tmp_style = layer_obj.style

        # create bounding box polygon
        bounding_points = (
            (float(layer_obj.capability_bbox_lat_lon["minx"]), float(layer_obj.capability_bbox_lat_lon["miny"])),
            (float(layer_obj.capability_bbox_lat_lon["minx"]), float(layer_obj.capability_bbox_lat_lon["maxy"])),
            (float(layer_obj.capability_bbox_lat_lon["maxx"]), float(layer_obj.capability_bbox_lat_lon["maxy"])),
            (float(layer_obj.capability_bbox_lat_lon["maxx"]), float(layer_obj.capability_bbox_lat_lon["miny"])),
            (float(layer_obj.capability_bbox_lat_lon["minx"]), float(layer_obj.capability_bbox_lat_lon["miny"]))
        )
        layer.bbox_lat_lon = Polygon(bounding_points)
        metadata.bounding_geometry = layer.bbox_lat_lon
        layer.created_by = creator
        layer.published_for = published_for
        layer.published_by = publisher
        layer.parent_service = wms
        layer.get_styles_uri_GET = layer_obj.get_styles_uri_GET
        layer.get_styles_uri_POST = layer_obj.get_styles_uri_POST
        layer.get_legend_graphic_uri_GET = layer_obj.get_legend_graphic_uri_GET
        layer.get_legend_graphic_uri_POST = layer_obj.get_legend_graphic_uri_POST
        layer.get_feature_info_uri_GET = layer_obj.get_feature_info_uri_GET
        layer.get_feature_info_uri_POST = layer_obj.get_feature_info_uri_POST
        layer.get_map_uri_GET = layer_obj.get_map_uri_GET
        layer.get_map_uri_POST = layer_obj.get_map_uri_POST
        layer.describe_layer_uri_GET = layer_obj.describe_layer_uri_GET
        layer.describe_layer_uri_POST = layer_obj.describe_layer_uri_POST
        layer.get_capabilities_uri_GET = layer_obj.get_capabilities_uri_GET
        layer.get_capabilities_uri_POST = layer_obj.get_capabilities_uri_POST

        for iso_md in layer_obj.iso_metadata:
            iso_md = iso_md.to_db_model()
            metadata_relation = MetadataRelation()
            metadata_relation.metadata_from = metadata
            metadata_relation.metadata_to = iso_md
            metadata_relation.origin = MetadataOrigin.objects.get_or_create(
                name=iso_md.origin
            )[0]
            metadata_relation.relation_type = MD_RELATION_TYPE_DESCRIBED_BY
            metadata_relation.save()

        # Dimensions
        for dimension in layer_obj.dimension_list:
            dim = Dimension.objects.get_or_create(
                type=dimension.get("type"),
                units=dimension.get("units"),
                extent=dimension.get("extent"),
            )[0]
            layer.metadata.dimensions.add(dim)

        if wms.root_layer is None:
            # no root layer set yet
            wms.root_layer = layer

        # iterate over all available mime types and actions
        for action, format_list in layer_obj.format_list.items():
            for _format in format_list:
                service_to_format = MimeType.objects.get_or_create(
                    operation=action,
                    mime_type=_format,
                    created_by=creator
                )[0]
                layer.formats.add(service_to_format)

        # Final save before continue
        metadata.save()
        layer.save()

        # Create layer DB records
        if len(layer_obj.child_layer) > 0:
            parent_layer = copy(layer)
            self._create_layer_model_instance(
                layers=layer_obj.child_layer,
                service_type=service_type,
                wms=wms,
                creator=creator,
                root_md=root_md,
                publisher=publisher,
                published_for=published_for,
                parent=parent_layer,
                user=user,
                contact=contact
            )

    def _create_layer_model_instance(self, layers: list, service_type: ServiceType, wms: Service, creator: MrMapGroup, publisher: Organization,
                                     published_for: Organization, root_md: Metadata, user: MrMapUser, contact, parent=None):
        """ Iterates over all layers given by the service and persist them, including additional data like metadata and so on.

        Args:
            layers (list): A list of layers
            service_type (ServiceType): The type of the service this function has to deal with
            wms (Service): The root or parent service which holds all these layers
            creator (MrMapGroup): The group that started the registration process
            publisher (Organization): The organization that publishes the service
            published_for (Organization): The organization for which the first organization publishes this data (e.g. 'in the name of')
            root_md (Metadata): The metadata of the root service (parameter 'wms')
            user (MrMapUser): The performing user
            contact (Contact): The contact object (Organization)
            parent: The parent layer object to this layer
        Returns:
            nothing
        """
        # Iterate over all layers and create DB records
        for layer_obj in layers:
            self._create_single_layer_model_instance(
                layer_obj,
                layers,
                service_type,
                wms,
                creator,
                publisher,
                published_for,
                root_md,
                user,
                contact,
                parent,
            )

    @transaction.atomic
    def create_service_model_instance(self, user: MrMapUser, register_group: MrMapGroup, register_for_organization: Organization, external_auth: ExternalAuthentication = None):
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
        orga_publisher = user.organization
        group = register_group

        # fill objects
        # Create ServiceType record if it doesn't exist yet
        service_type = ServiceType.objects.get_or_create(
            name=self.service_type.value,
            version=self.service_version.value
        )[0]

        # Metadata
        metadata = Metadata()
        md_type = MetadataType.objects.get_or_create(type=MetadataEnum.SERVICE.value)[0]
        metadata.metadata_type = md_type
        if self.service_file_iso_identifier is None:
            # We didn't found any file identifier in the document -> we create one
            self.service_file_iso_identifier = uuid.uuid4()
        metadata.uuid = self.service_file_iso_identifier
        metadata.title = self.service_identification_title
        metadata.abstract = self.service_identification_abstract
        metadata.online_resource = self.service_provider_onlineresource_linkage
        metadata.capabilities_original_uri = self.service_connect_url
        metadata.capabilities_uri = self.service_connect_url
        metadata.access_constraints = self.service_identification_accessconstraints
        metadata.fees = self.service_identification_fees
        metadata.bounding_geometry = self.service_bounding_box
        metadata.identifier = self.service_file_identifier
        metadata.is_active = False
        metadata.created_by = group

        if external_auth is not None:
            external_auth.metadata = metadata
            crypt_handler = CryptoHandler()
            key = crypt_handler.generate_key()
            crypt_handler.write_key_to_file("{}/md_{}.key".format(EXTERNAL_AUTHENTICATION_FILEPATH, metadata.id), key)
            external_auth.encrypt(key)
            external_auth.save()

        metadata.capabilities_uri = SERVICE_OPERATION_URI_TEMPLATE.format(metadata.id) + "request={}".format(OGCOperationEnum.GET_CAPABILITIES.value)
        metadata.service_metadata_uri = SERVICE_METADATA_URI_TEMPLATE.format(metadata.id)
        metadata.html_metadata_uri = HTML_METADATA_URI_TEMPLATE.format(metadata.id)

        # Save metadata instance to be able to add M2M entities
        metadata.save()

        # Keywords
        for kw in self.service_identification_keywords:
            if kw is None:
                continue
            keyword = Keyword.objects.get_or_create(keyword=kw)[0]
            metadata.keywords.add(keyword)

        # Contact
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
        metadata.contact = contact

        metadata.save()

        # Service
        service = Service()
        service.availability = 0.0
        service.is_available = False
        service.servicetype = service_type
        service.published_for = orga_published_for
        service.published_by = orga_publisher
        service.created_by = group
        service.get_capabilities_uri_GET = self.get_capabilities_uri_GET
        service.get_capabilities_uri_POST = self.get_capabilities_uri_POST
        service.get_feature_info_uri_GET = self.get_feature_info_uri_GET
        service.get_feature_info_uri_POST = self.get_feature_info_uri_POST
        service.describe_layer_uri_GET = self.describe_layer_uri_GET
        service.describe_layer_uri_POST = self.describe_layer_uri_POST
        service.get_styles_uri_GET = self.get_styles_uri_GET
        service.get_styles_uri_POST = self.get_styles_uri_POST
        service.get_legend_graphic_uri_GET = self.get_legend_graphic_uri_GET
        service.get_legend_graphic_uri_POST = self.get_legend_graphic_uri_POST
        service.get_map_uri_GET = self.get_map_uri_GET
        service.get_map_uri_POST = self.get_map_uri_POST
        service.metadata = metadata
        service.is_root = True

        service.save()

        # Check for linked service metadata that might be found during parsing
        if self.linked_service_metadata is not None:
            service.linked_service_metadata = self.linked_service_metadata.to_db_model(MetadataEnum.SERVICE.value)
            md_relation = MetadataRelation()
            md_relation.metadata_from = metadata
            md_relation.metadata_to = service.linked_service_metadata
            md_relation.origin = MetadataOrigin.objects.get_or_create(
                name='capabilities'
            )[0]
            md_relation.relation_type = MD_RELATION_TYPE_VISUALIZES
            md_relation.save()

        # Persist capabilities xml
        service.persist_capabilities_doc(self.service_capabilities_xml)

        # Begin creation of Layer records, starting with the root layer
        root_layer = self.layers[0]
        self._create_layer_model_instance(
            layers=[root_layer],
            service_type=service_type,
            wms=service,
            creator=group,
            root_md=copy(metadata),
            publisher=orga_publisher,
            published_for=orga_published_for,
            contact=contact,
            user=user
        )
        return service

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