
from django.contrib.gis.geos import Polygon


def bbox_to_polygon(values):
    """
    Erwartet values als Sequenz: (minx, maxx, miny, maxy)
    Gibt ein Polygon zurück.
    """
    if len(values) != 4:
        raise ValueError(
            "bbox_to_polygon expects 4 inputs (minx, maxx, miny, maxy)")
    # Umwandlung in float
    try:
        minx, maxx, miny, maxy = map(float, values)
    except (TypeError, ValueError) as e:
        raise ValueError(
            f"bbox_to_polygon: unable to parse floats from {values}: {e}")
    # GEOS from_bbox expects (xmin, ymin, xmax, ymax)
    return Polygon.from_bbox((minx, miny, maxx, maxy))


def polygon_to_bbox(polygon):
    """
    Erwartet ein GEOS Polygon,
    gibt eine Liste von Strings zurück: [minx, maxx, miny, maxy]
    passend zu den XML-@Attribute Inputs.
    """
    if polygon is None:
        return [None, None, None, None]
    try:
        # extent: (xmin, ymin, xmax, ymax)
        xmin, ymin, xmax, ymax = polygon.extent
    except AttributeError as e:
        raise ValueError(
            f"polygon_to_bbox: expected polygon, got {polygon}: {e}")
    return [str(xmin), str(xmax), str(ymin), str(ymax)]
