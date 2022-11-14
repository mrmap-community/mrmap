from axis_order_cache.utils import adjust_axis_order
from django.contrib.gis.geos import Polygon as GeosPolygon
from django.template.loader import render_to_string
from eulxml.xmlmap import (NodeField, NodeListField, StringField,
                           StringListField, XmlObject)
from lxml import etree
from ows_lib.xml_mapper.namespaces import (FES_2_0_NAMEPSACE,
                                           GML_3_2_2_NAMESPACE,
                                           WFS_2_0_0_NAMESPACE)


class PolygonFilter(XmlObject):
    ROOT_NS = "fes"
    ROOT_NAME = "Within"
    ROOT_NAMESPACES = {
        "fes": FES_2_0_NAMEPSACE,
        "gml": GML_3_2_2_NAMESPACE
    }

    _srs_name = StringField(xpath="./@srsName")
    _position_list = StringField(
        xpath="./gml:exterior/gml:LinearRing/gml:posList")

    def __init__(self, srid, coords, node=None, context=None, **kwargs):
        super().__init__(node, context, **kwargs)
        self.srs_name = srid
        self.position_list = coords

    @property
    def srs_name(self):
        return self._srs_name

    @srs_name.setter
    def srs_name(self, srid):
        self._srs_name = f"urn:x-ogc:def:crs:EPSG:{srid}"

    @property
    def position_list(self):
        return self._position_list

    @position_list.setter
    def position_list(self, coords):
        self._position_list = " ".join(f"{coords[0][0][0]} {coords[0][0][1]}")


class Filter(XmlObject):
    ROOT_NS = "fes"
    ROOT_NAME = "Filter"
    XSD_SCHEMA = "http://schemas.opengis.net/filter/2.0/filter.xsd"
    ROOT_NAMESPACES = {
        "fes": FES_2_0_NAMEPSACE,
        "gml": GML_3_2_2_NAMESPACE
    }

    ressource_ids = StringListField(xpath="./fes:ResourceId/@rid")

    condition = StringField(xpath=".")

    @classmethod
    def init_within_filter_node(cls,
                                value_reference,
                                polygon: GeosPolygon,
                                filter_namespace: str,
                                filter_namespace_url: str,
                                gml_namespace_url: str,
                                axis_order_correction: bool = True):
        if axis_order_correction:
            polygon = adjust_axis_order(polygon)
        within_filter = render_to_string(template_name="registry/xml/wfs/filter_within_v2.xml",
                                         context={"value_reference": value_reference,
                                                  "polygon": polygon,
                                                  "filter_namespace": filter_namespace,
                                                  "filter_namespace_url": filter_namespace_url,
                                                  "gml_namespace_url": gml_namespace_url})
        return etree.fromstring(within_filter)

    @classmethod
    def init_secured_filter_node(cls,
                                 value_reference,
                                 polygon: GeosPolygon,
                                 filter_namespace: str = "ogc",
                                 filter_namespace_url: str = "http://www.opengis.net/ogc",
                                 gml_namespace_url: str = "http://www.opengis.net/gml",
                                 axis_order_correction: bool = True):

        if axis_order_correction:
            polygon = adjust_axis_order(polygon)
        filter_node = render_to_string(template_name="registry/xml/wfs/filter_v2.xml",
                                       context={"value_reference": value_reference,
                                                "polygon": polygon,
                                                "filter_namespace": filter_namespace,
                                                "filter_namespace_url": filter_namespace_url,
                                                "gml_namespace_url": gml_namespace_url})
        return etree.fromstring(filter_node)

    def secure_spatial(self, value_reference, polygon: GeosPolygon, axis_order_correction: bool = True):
        gml_namespace_url = self.context['namespaces'].get(
            "gml", "http://www.opengis.net/gml")

        if len(polygon.coords) == 1:
            PolygonFilter(srid=polygon.srid, coords=polygon.coords)
        elif len(polygon.coords) > 1:
            for coords in polygon.coords:
                PolygonFilter(srid=polygon.srid, coords=coords)

        within_tree = self.init_within_filter_node(value_reference=value_reference,
                                                   polygon=polygon,
                                                   filter_namespace=filter_namespace,
                                                   filter_namespace_url=filter_namespace_url,
                                                   axis_order_correction=axis_order_correction,
                                                   gml_namespace_url=gml_namespace_url)

        if "And" in self.name:
            # append geometry filter as sub element
            self.node.append(within_tree)
        else:
            old_filter = copy.deepcopy(self.node)
            if filter_namespace:
                and_element = etree.Element("{" + self.context['namespaces'].get(filter_namespace) + "}And",
                                            nsmap=self.context["namespaces"])
            else:
                and_element = etree.Element("And")
            and_element.append(old_filter)
            and_element.append(within_tree)
            # add new <fes:And></fes:And> around current node
            # after that, append geometry filter as sub element
            self.node.getparent().replace(self.node, and_element)


class Query(XmlObject):
    ROOT_NS = "wfs"
    ROOT_NAME = "Query"
    XSD_SCHEMA = "http://schemas.opengis.net/wfs/2.0/wfs.xsd"
    ROOT_NAMESPACES = {
        "wfs": WFS_2_0_0_NAMESPACE,
        "fes": FES_2_0_NAMEPSACE
    }

    type_names = StringField(xpath="./@typeNames")
    property_names = StringListField(xpath="./wfs:PropertyName")
    filter = NodeField(xpath="./fes:Filter", node_class=Filter)


class GetFeatureRequest(XmlObject):
    ROOT_NS = "wfs"
    ROOT_NAME = "GetFeature"
    XSD_SCHEMA = "http://schemas.opengis.net/wfs/2.0/wfs.xsd"
    ROOT_NAMESPACES = {
        "wfs": WFS_2_0_0_NAMESPACE,
        "fes": FES_2_0_NAMEPSACE
    }

    query = NodeListField(xpath="./wfs:Query", node_class=Query)
