from typing import List

from django.contrib.gis.geos import Polygon as GeosPolygon
from eulxml.xmlmap import (NodeField, NodeListField, StringField,
                           StringListField, XmlObject)
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

    def __init__(self, srid=None, coords=None, node=None, context=None, **kwargs):
        super().__init__(node, context, **kwargs)
        if srid:
            self.srs_name = srid
        if coords:
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
        position_list = ""
        for x, y in coords[0]:
            position_list += f"{x} {y} "
        self._position_list = position_list[:-1]


class WithinCondition(XmlObject):
    ROOT_NS = "fes"
    ROOT_NAME = "Within"
    ROOT_NAMESPACES = {
        "fes": FES_2_0_NAMEPSACE,
        "gml": GML_3_2_2_NAMESPACE
    }

    value_reference = StringField(xpath="./fes:ValueReference")
    polygon_filter = NodeField(xpath="./gml:Polygon", node_class=PolygonFilter)


class AndCondition(XmlObject):
    ROOT_NS = "fes"
    ROOT_NAME = "And"
    ROOT_NAMESPACES = {
        "fes": FES_2_0_NAMEPSACE,
    }


class OrCondition(XmlObject):
    ROOT_NS = "fes"
    ROOT_NAME = "Or"
    ROOT_NAMESPACES = {
        "fes": FES_2_0_NAMEPSACE,
    }

    within_conditons = NodeListField(
        xpath="./fes:Within", node_class=WithinCondition)


class Filter(XmlObject):
    ROOT_NS = "fes"
    ROOT_NAME = "Filter"
    XSD_SCHEMA = "http://schemas.opengis.net/filter/2.0/filter.xsd"
    ROOT_NAMESPACES = {
        "fes": FES_2_0_NAMEPSACE,
        "gml": GML_3_2_2_NAMESPACE
    }

    ressource_ids = StringListField(xpath="./fes:ResourceId/@rid")

    and_condition = NodeField(xpath="./fes:And", node_class=AndCondition)


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

    queries = NodeListField(xpath="./wfs:Query", node_class=Query)

    def construct_polygon_filter_xml_node(self, polygon: GeosPolygon, value_reference: str) -> XmlObject:
        if len(polygon.coords) == 1:
            within_condition = WithinCondition()
            within_condition.value_reference = value_reference
            within_condition.polygon_filter = PolygonFilter(
                srid=polygon.srid, coords=polygon.coords)
            return within_condition
        elif len(polygon.coords) > 1:
            atomic_polygon_filter: List[WithinCondition] = []
            for coords in polygon.coords:
                within_condition = WithinCondition()
                within_condition.value_reference = value_reference
                within_condition.polygon_filter = PolygonFilter(
                    srid=polygon.srid, coords=coords)
                atomic_polygon_filter.append(within_condition)
            condition = OrCondition()
            condition.within_conditons = atomic_polygon_filter
            return condition

    def secure_spatial(self, value_reference, polygon: GeosPolygon, axis_order_correction: bool = True) -> None:
        spatial_filter = self.construct_polygon_filter_xml_node(
            polygon=polygon, value_reference=value_reference)
        for query in self.queries:
            if query.filter.and_condition:
                # append geometry filter as sub element
                and_condition.node.append(spatial_filter.node)

            else:
                # old_filter = copy.deepcopy(query.filter.node)
                and_condition = AndCondition()
                and_condition.node.extend(
                    [child for child in query.filter.node])
                and_condition.node.append(spatial_filter.node)
                new_filter = Filter()
                new_filter.and_condition = and_condition

                # self.append_filter_nodes(
                #     filter_nodes=spatial_filter, node=and_condition.node)

                query.filter = new_filter

                # add new <fes:And></fes:And> around current node
                # after that, append geometry filter as sub element
                # query.filter.node.getparent().replace(query.filter.node, new_filter.node)
