import copy
from typing import List

from django.contrib.gis.geos import GEOSGeometry
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
    # FIXME: and_conditions are also possible


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

    and_condition = NodeField(xpath="./fes:And", node_class=AndCondition)
    or_condition = NodeField(xpath="./fes:Or", node_class=OrCondition)
    within_conditions = NodeListField(
        xpath="./fes:Within", node_class=WithinCondition)


class Query(XmlObject):
    ROOT_NS = WFS_2_0_0_NAMESPACE
    ROOT_NAME = "Query"
    XSD_SCHEMA = "http://schemas.opengis.net/wfs/2.0/wfs.xsd"
    ROOT_NAMESPACES = {
        "wfs": WFS_2_0_0_NAMESPACE,
        "fes": FES_2_0_NAMEPSACE
    }

    # single typenames are seperated by ,
    # example: <Query typeNames="ms:Erdbebenstation_Schutzbereich, ms:Erdbebenereignisse">
    _type_names = StringField(xpath="./@typeNames")

    property_names = StringListField(xpath="./wfs:PropertyName")
    filter = NodeField(xpath="./fes:Filter", node_class=Filter)

    @property
    def type_names(self) -> list[str]:
        return self._type_names.split(",")

    @type_names.setter
    def type_names(self, type_names: list[str]) -> None:
        self._type_names = ", ".join(type_names)


class GetFeatureRequest(XmlObject):
    ROOT_NS = WFS_2_0_0_NAMESPACE
    ROOT_NAME = "GetFeature"
    XSD_SCHEMA = "http://schemas.opengis.net/wfs/2.0/wfs.xsd"
    ROOT_NAMESPACES = {
        "wfs": WFS_2_0_0_NAMESPACE,
        "fes": FES_2_0_NAMEPSACE,
        "gml": GML_3_2_2_NAMESPACE
    }

    # is optional, but mapserver for example will report an server error if you dont pass it.
    # Default is application/gml+xml; version=3.2
    output_format = StringField(xpath="./@outputFormat")
    version = StringField(xpath="./@version")
    service_type = StringField(xpath="./@service")

    # wfs 1.1.0 spec 9.2:
    # "The <GetFeature> element contains one or more <Query> elements, each of which in turn contains the description of a query." 
    queries = NodeListField(xpath="./wfs:Query", node_class=Query)

    def _construct_within_condition(self, srid: str, value_reference: str, coords) -> WithinCondition:
        within_condition = WithinCondition()
        within_condition.value_reference = value_reference
        within_condition.polygon_filter = PolygonFilter(
            srid=srid, coords=coords)
        return within_condition

    def _construct_spatial_filter_condition(self, polygon: GeosPolygon, value_reference: str) -> (WithinCondition | OrCondition):
        if len(polygon.coords) == 1:
            return self._construct_within_condition(srid=polygon.srid, value_reference=value_reference, coords=polygon.coords)
        elif len(polygon.coords) > 1:
            or_condition = OrCondition()
            for coords in polygon.coords:
                or_condition.within_conditions.append(self._construct_within_condition(
                    srid=polygon.srid, value_reference=value_reference, coords=coords))
            return or_condition

    def _append_spatial_filter_condition(self, polygon: GeosPolygon, value_reference: str, query: Query):
        filter_condition = self._construct_spatial_filter_condition(
            polygon=polygon, value_reference=value_reference)

        xml_node = query.filter.and_condition if query.filter.and_condition else query.filter

        if isinstance(filter_condition, WithinCondition):
            xml_node.within_conditions.append(filter_condition)
        elif isinstance(filter_condition, OrCondition):
            xml_node.or_condition = filter_condition

    def _adjust_filter_node(self, query: Query) -> None:
        if not query.filter:
            query.filter = Filter()
        elif not query.filter.and_condition:
            # Sourround the old filter with a fes:And node first to combine them binary together and secure the request spatial
            old_filter = copy.deepcopy(query.filter.node)
            query.filter = Filter()
            query.filter.and_condition = AndCondition()
            query.filter.and_condition.node.extend(
                [child for child in old_filter])

    def secure_spatial(self, feature_types: list[dict]) -> None:

        lookup_dict = {}
        for feature_type in feature_types:
            try:
                lookup_dict.update({
                    feature_type.get("type_name"): {
                        "geometry_property_name": feature_type.get("geometry_property_name"),
                        "allowed_area_union": feature_type.get("allowed_area_union")
                    }})
            except AttributeError:
                raise AttributeError(
                    "feature_types list shall be provides as a list of dicts with kind {'type_name': val, 'geometry_property_name': val, 'allowed_area_union': val}")

        query: Query
        for query in self.queries:
            _feature_type = lookup_dict.get(query.type_names[0], {})
            _polygon = _feature_type.get(
                "allowed_area_union", GEOSGeometry("POLYGON EMPTY"))
            _geometry_property_name = _feature_type.get(
                "geometry_property_name", "THE_GEOM")

            if len(query.type_names) == 1 and _polygon and not _polygon.empty:
                self._adjust_filter_node(query=query)
                self._append_spatial_filter_condition(
                    polygon=_polygon, value_reference=_geometry_property_name, query=query)

            elif len(query.type_names) > 1:
                raise NotImplementedError(
                    "Currently we can't secure a query with multple type names in a single query node.")

    @property
    def requested_feature_types(self) -> List[str]:
        """Collect all typeNames of the request."""
        type_names = []
        for query in self.queries:
            for type_name in query.type_names:
                type_names.append(type_name)
        return type_names
