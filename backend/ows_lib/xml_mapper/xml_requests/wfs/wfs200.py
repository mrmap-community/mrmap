import copy

from django.contrib.gis.geos import Polygon as GeosPolygon
from eulxml.xmlmap import (NodeField, NodeListField, StringField,
                           StringListField, XmlObject)
from ows_lib.xml_mapper.namespaces import (FES_2_0_NAMEPSACE,
                                           GML_3_2_2_NAMESPACE,
                                           WFS_2_0_0_NAMESPACE)


class PolygonFilter(XmlObject):
    ROOT_NS = GML_3_2_2_NAMESPACE
    ROOT_NAME = "Within"
    ROOT_NAMESPACES = {
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
    ROOT_NS = FES_2_0_NAMEPSACE
    ROOT_NAME = "Within"
    ROOT_NAMESPACES = {
        "fes": FES_2_0_NAMEPSACE,
        "gml": GML_3_2_2_NAMESPACE
    }

    value_reference = StringField(xpath="./fes:ValueReference")
    polygon_filter = NodeField(xpath="./gml:Polygon", node_class=PolygonFilter)


class OrCondition(XmlObject):
    ROOT_NS = FES_2_0_NAMEPSACE
    ROOT_NAME = "Or"
    ROOT_NAMESPACES = {
        "fes": FES_2_0_NAMEPSACE,
    }

    within_conditions = NodeListField(
        xpath="./fes:Within", node_class=WithinCondition)
    or_conditions = NodeListField(xpath="./fes:Or", node_class="self")


class AndCondition(XmlObject):
    ROOT_NS = FES_2_0_NAMEPSACE
    ROOT_NAME = "And"
    ROOT_NAMESPACES = {
        "fes": FES_2_0_NAMEPSACE,
    }

    within_conditions = NodeListField(
        xpath="./fes:Within", node_class=WithinCondition)
    and_conditions = NodeListField(xpath="./fes:And", node_class="self")
    or_conditions = NodeListField(xpath="./fes:Or", node_class=OrCondition)


class Filter(XmlObject):
    ROOT_NS = FES_2_0_NAMEPSACE
    ROOT_NAME = "Filter"
    XSD_SCHEMA = "http://schemas.opengis.net/filter/2.0/filter.xsd"
    ROOT_NAMESPACES = {
        "fes": FES_2_0_NAMEPSACE,
        "gml": GML_3_2_2_NAMESPACE
    }

    ressource_ids = StringListField(xpath="./fes:ResourceId/@rid")

    # FIXME: multiple and and or conditions are possible
    and_condition = NodeField(xpath="./fes:And", node_class=AndCondition)
    or_condition = NodeField(xpath="./fes:Or", node_class=OrCondition)


class Query(XmlObject):
    ROOT_NS = WFS_2_0_0_NAMESPACE
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
    ROOT_NS = WFS_2_0_0_NAMESPACE
    ROOT_NAME = "GetFeature"
    XSD_SCHEMA = "http://schemas.opengis.net/wfs/2.0/wfs.xsd"
    ROOT_NAMESPACES = {
        "wfs": WFS_2_0_0_NAMESPACE,
        "fes": FES_2_0_NAMEPSACE,
        "gml": GML_3_2_2_NAMESPACE
    }

    queries = NodeListField(xpath="./wfs:Query", node_class=Query)

    def _construct_within_condition(self, srid: str, value_reference: str, coords, parent_condition: (AndCondition | OrCondition)) -> None:
        within_condition = WithinCondition()
        within_condition.value_reference = value_reference
        within_condition.polygon_filter = PolygonFilter(
            srid=srid, coords=coords)
        parent_condition.within_conditions.append(within_condition)

    def _append_spatial_filter_condition(self, polygon: GeosPolygon, value_reference: str, and_condition: AndCondition) -> None:
        if len(polygon.coords) == 1:
            self._construct_within_condition(
                srid=polygon.srid, value_reference=value_reference, coords=polygon.coords, parent_condition=and_condition)
        elif len(polygon.coords) > 1:
            or_condition = OrCondition()
            for coords in polygon.coords:
                self._construct_within_condition(
                    srid=polygon.srid, value_reference=value_reference, coords=coords, parent_condition=or_condition)
            and_condition.or_conditions.append(or_condition)

    def secure_spatial(self, value_reference, polygon: GeosPolygon) -> None:

        for query in self.queries:
            if not query.filter.and_condition:
                # Sourround the old filter with a fes:And node first to combine them binary together
                old_filter = copy.deepcopy(query.filter.node)
                query.filter = Filter()
                query.filter.and_condition = AndCondition()
                query.filter.and_condition.node.extend(
                    [child for child in old_filter])

            self._append_spatial_filter_condition(
                polygon=polygon, value_reference=value_reference, and_condition=query.filter.and_condition)
