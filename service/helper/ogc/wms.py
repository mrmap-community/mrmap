# common classes for handling of WMS (OGC WebMapServices)
# http://www.opengeospatial.org/standards/wms
"""Common classes to handle WMS (OGC WebMapServices).

.. moduleauthor:: Armin Retterath <armin.retterath@gmail.com>

"""
import time
from threading import Thread

from MapSkinner.utils import execute_threads
from service.helper.enums import VersionTypes
from service.helper.ogc.ows import OGCWebService
from service.helper.ogc.layer import OGCLayer

from lxml import etree
import re

from service.helper import service_helper


class OGCWebMapServiceFactory:
    """ Creates the correct OGCWebMapService objects

    """
    def get_ogc_wms(self, version: VersionTypes, service_connect_url: str):
        """ Returns the correct implementation of an OGCWebMapService according to the given version

        Args:
            version: The version number of the service
            service_connect_url: The capabilities request uri
        Returns:
            An OGCWebMapService
        """
        if version is VersionTypes.V_1_0_0:
            return OGCWebMapService_1_0_0(service_connect_url=service_connect_url)
        if version is VersionTypes.V_1_1_0:
            return OGCWebMapService_1_1_0(service_connect_url=service_connect_url)
        if version is VersionTypes.V_1_1_1:
            return OGCWebMapService_1_1_1(service_connect_url=service_connect_url)
        if version is VersionTypes.V_1_3_0:
            return OGCWebMapService_1_3_0(service_connect_url=service_connect_url)


class OGCWebMapService(OGCWebService):
    """Base class for OGC WebMapServices."""

    # define layers as array of OGCWebMapServiceLayer objects
    # Using None here to avoid mutable appending of infinite layers (python specific)
    # For further details read: http://effbot.org/zone/default-values.htm
    layers = None

    class Meta:
        abstract = True

    def __parse_identifier(self, layer, layer_obj):
            try:
                name = layer.xpath("./Name")[0].text
                layer_obj.identifier = name
            except IndexError:
                pass

    def __parse_keywords(self, layer, layer_obj):
            try:
                keywords = layer.xpath("./KeywordList/Keyword")
                for keyword in keywords:
                    layer_obj.capability_keywords.append(keyword.text)
            except AttributeError:
                pass

    def __parse_abstract(self, layer, layer_obj):
            try:
                abstract = layer.xpath("./Abstract")[0].text
                layer_obj.abstract = abstract
            except IndexError:
                pass

    def __parse_title(self, layer, layer_obj):
            try:
                title = layer.xpath("./Title")[0].text
                layer_obj.title = title
            except IndexError:
                pass

    def __parse_srs(self, layer, layer_obj):
            try:
                srs = layer.xpath("./SRS")
                for elem in srs:
                    layer_obj.capability_srs.append(elem.text)
            except IndexError:
                pass

    def __parse_lat_lon_bounding_box(self, layer, layer_obj):
            try:
                bbox = layer.xpath("./LatLonBoundingBox")[0]
                attrs = ["minx", "miny", "maxx", "maxy"]
                for attr in attrs:
                    layer_obj.capability_bbox_lat_lon[attr] = bbox.get(attr)
            except IndexError:
                pass

    def __parse_bounding_box(self, layer, layer_obj):
            try:
                bboxs = layer.xpath("./BoundingBox")
                for bbox in bboxs:
                    srs = bbox.get("SRS")
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
            except IndexError:
                pass

    def __parse_scale_hint(self, layer, layer_obj):
            try:
                scales = layer.xpath("./ScaleHint")[0]
                attrs = ["min", "max"]
                for attr in attrs:
                    layer_obj.capability_scale_hint[attr] = scales.get(attr)
            except IndexError:
                pass

    def __parse_queryable(self, layer, layer_obj):
            try:
                is_queryable = layer.get("queryable")
                if is_queryable is None:
                    is_queryable = False
                else:
                    is_queryable = service_helper.resolve_boolean_attribute_val(is_queryable)
                layer_obj.is_queryable = is_queryable
            except AttributeError:
                pass

    def __parse_opaque(self, layer, layer_obj):
            try:
                is_opaque = layer.get("opaque")
                if is_opaque is None:
                    is_opaque = False
                else:
                    is_opaque = service_helper.resolve_boolean_attribute_val(is_opaque)
                layer_obj.is_opaque = is_opaque
            except AttributeError:
                pass

    def __parse_cascaded(self, layer, layer_obj):
            try:
                is_opaque = layer.get("cascaded")
                if is_opaque is None:
                    is_opaque = False
                else:
                    is_opaque = service_helper.resolve_boolean_attribute_val(is_opaque)
                layer_obj.is_cascaded = is_opaque
            except AttributeError:
                pass

    def __parse_request_uris(self, layer, layer_obj):
        try:
            get_capabilities_uri = layer.xpath("//GetCapabilities/DCPType/HTTP/Get/OnlineResource")[0].get("{http://www.w3.org/1999/xlink}href")
            get_map_uri = layer.xpath("//GetMap/DCPType/HTTP/Get/OnlineResource")[0].get("{http://www.w3.org/1999/xlink}href")
            get_feature_info_uri = layer.xpath("//GetFeatureInfo/DCPType/HTTP/Get/OnlineResource")[0].get("{http://www.w3.org/1999/xlink}href")
            describe_layer_uri = layer.xpath("//DescribeLayer/DCPType/HTTP/Get/OnlineResource")[0].get("{http://www.w3.org/1999/xlink}href")
            get_legend_graphic_uri = layer.xpath("//GetLegendGraphic/DCPType/HTTP/Get/OnlineResource")[0].get("{http://www.w3.org/1999/xlink}href")
            get_styles_uri = layer.xpath("//GetStyles/DCPType/HTTP/Get/OnlineResource")[0].get("{http://www.w3.org/1999/xlink}href")

            layer_obj.get_capabilities_uri = get_capabilities_uri
            layer_obj.get_map_uri = get_map_uri
            layer_obj.get_feature_info_uri = get_feature_info_uri
            layer_obj.describe_layer_uri = describe_layer_uri
            layer_obj.get_legend_graphic_uri = get_legend_graphic_uri
            layer_obj.get_styles_uri = get_styles_uri

        except AttributeError:
            pass

    def __parse_formats(self, layer, layer_obj):
        try:
            format_list = layer.xpath("//GetMap/Format")
            f_l = []
            for format in format_list:
                f_l.append(format.text)
            layer_obj.format_list = f_l
        except AttributeError:
            pass


    def __get_layers_recursive(self, layers, parent=None, position=0):
        """ Recursive Iteration over all children and subchildren.

        Creates OGCWebMapLayer objects for each xml layer and fills it with the layer content.

        Args:
            layers: An array of layers (In fact the children of the parent layer)
            parent: The parent layer. If no parent exist it means we are in the root layer
            position: The position inside the layer tree, which is more like an order number
        :return:
        """
        for layer in layers:
            # iterate over all top level layer and find their children
            layer_obj = OGCWebMapServiceLayer()
            layer_obj.parent = parent
            layer_obj.position = position
            # iterate over single parsing functions -> improves maintainability
            parse_functions = [
                self.__parse_identifier,
                self.__parse_keywords,
                self.__parse_abstract,
                self.__parse_title,
                self.__parse_srs,
                self.__parse_lat_lon_bounding_box,
                self.__parse_bounding_box,
                self.__parse_scale_hint,
                self.__parse_queryable,
                self.__parse_opaque,
                self.__parse_cascaded,
                self.__parse_request_uris,
                self.__parse_formats,
            ]
            for func in parse_functions:
                func(layer=layer, layer_obj=layer_obj)

            if self.layers is None:
                self.layers = []
            self.layers.append(layer_obj)
            sublayers = layer.xpath("./Layer")
            position += 1
            self.__get_layers_recursive(layers=sublayers, parent=layer_obj, position=position)

    def get_layers(self, xml_obj):
        """ Parses all layers of a service and creates objects for it.

        Uses recursion on the inside to get all children.

        Args:
            xml_obj: The iterable xml tree
        Returns:
             nothing
        """
        # get most upper parent layer, which normally lives directly in <Capability>
        layers = xml_obj.xpath("//Capability/Layer")
        self.__get_layers_recursive(layers)

    def create_from_capabilities(self):
        """ Fills the object with data from the capabilities document

        Returns:
             nothing
        """
        # get xml as iterable object
        xml_obj = service_helper.parse_xml(xml=self.service_capabilities_xml)
        if self.service_version is VersionTypes.V_1_0_0:
            self.get_service_metadata_v100(xml_obj=xml_obj)
        if self.service_version is VersionTypes.V_1_1_0:
            self.get_service_metadata_v110(xml_obj=xml_obj)
        if self.service_version is VersionTypes.V_1_1_1:
            self.get_service_metadata_v111(xml_obj=xml_obj)
        if self.service_version is VersionTypes.V_1_3_0:
            self.get_service_metadata_v130(xml_obj=xml_obj)
        self.get_layers(xml_obj=xml_obj)


class OGCWebMapServiceLayer(OGCLayer):
    """ The OGCWebMapServiceLayer class

    """


class OGCWebMapService_1_0_0(OGCWebMapService):
    """ The WMS class for standard version 1.0.0

    """


class OGCWebMapService_1_1_0(OGCWebMapService):
    """ The WMS class for standard version 1.1.0

    """


class OGCWebMapService_1_1_1(OGCWebMapService):
    """ The WMS class for standard version 1.1.1

    """


class OGCWebMapService_1_3_0(OGCWebMapService):
    """ The WMS class for standard version 1.3.0

    """
            
    # https://stackoverflow.com/questions/34009992/python-elementtree-default-namespace
    # def create_from_capabilities(self):
    #     # Remove the default namespace definition (xmlns="http://some/namespace")
    #     xmlstring = re.sub(r'\sxmlns="[^"]+"', '', self.service_capabilities_xml, count=1)
    #     root = etree.XML(str.encode(xmlstring))
    #     tree = etree.ElementTree(root)
    #     # service metadata
    #     r = tree.xpath('/WMS_Capabilities/Service/Title')
    #     self.service_identification_title = r[0].text
    #     r = tree.xpath('/WMS_Capabilities/Service/Abstract')
    #     self.service_identification_abstract = r[0].text
    #     r = tree.xpath('/WMS_Capabilities/Service/KeywordList/Keyword')
    #     for keyword in r:
    #         self.service_identification_keywords.append(keyword.text)
    #         # print(keyword.text)
    #     r = tree.xpath('/WMS_Capabilities/Service/Fees')
    #     self.service_identification_fees = r[0].text
    #     r = tree.xpath('/WMS_Capabilities/Service/AccessConstraints')
    #     self.service_identification_accessconstraints = r[0].text
    #
    #     #p arse layer objects recursive
    #     layers = tree.xpath('/WMS_Capabilities/Capability/Layer')
    #     for layer in layers:
    #         self.parse_layers_recursive(etree.tostring(layer), 0)
    #     # transform to mptt
    #
    #     # debug output
    #     for layer in self.layers:
    #         print(layer.position, layer.parent, layer.title)
