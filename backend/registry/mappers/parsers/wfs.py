from lxml import etree
from registry.mappers.parsers.value import \
    bbox_to_polygon as bbox_value_to_polygon
from registry.mappers.parsers.value import srs_to_code, srs_to_prefix
from registry.models.metadata import ReferenceSystem
from registry.ows_lib.wfs.xml_builder import WFSBuilder


def parse_reference_system(mapper, el):
    if el.text:
        code = srs_to_code(mapper, el.text)
        prefix = srs_to_prefix(mapper, el.text)
        return ReferenceSystem(
            code=code,
            prefix=prefix
        )


def parse_reference_systems(mapper, el):
    """
    Parst alle DefaultCRS und OtherCRS des aktuellen FeatureType.

    """
    instances = []
    nsmap = mapper.mapping.get("_namespaces", None)

    for crs_el in el.xpath("./.", namespaces=nsmap):
        instances.append(
            parse_reference_system(mapper, crs_el)
        )

    return instances


def bbox_to_polygon(mapper, lower_corner, upper_corner):
    """
    Erwartet values als Sequenz: (minx, maxx, miny, maxy)
    Gibt ein Polygon zurück.
    """
    # GEOS from_bbox expects (xmin, ymin, xmax, ymax)
    minx = lower_corner.split(" ")[0]
    miny = lower_corner.split(" ")[1]
    maxx = upper_corner.split(" ")[0]
    maxy = upper_corner.split(" ")[1]
    return bbox_value_to_polygon(mapper, minx, miny, maxx, maxy)


def polygon_to_bbox(mapper, polygon) -> etree._Element:
    builder = WFSBuilder()
    builder.set_bbox(polygon, mapper.current_element)
