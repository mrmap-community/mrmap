from django.contrib.gis.geos import MultiPolygon, Polygon, Point
from django.contrib.gis.gdal.geometries import MultiPolygon as GdalMultiPolygon, Polygon as GdalPolygon, \
    Point as GdalPoint
from axis_order_cache.registry import Registry


def get_epsg_srid(srs_name):
    """Parse a given srs name in different possible formats

    WFS 1.1.0 supports (see 9.2, page 36):
    * EPSG:<EPSG code>
    * URI Style 2
    * urn:EPSG:geographicCRS:<epsg code>

    :param srs_name: the Coordinate reference system. Examples:
          * EPSG:<EPSG code>
          * http://www.opengis.net/def/crs/EPSG/0/<EPSG code> (URI Style 1)
          * http://www.opengis.net/gml/srs/epsg.xml#<EPSG code> (URI Style 2)
          * urn:EPSG:geographicCRS:<epsg code>
          * urn:ogc:def:crs:EPSG::4326
          * urn:ogc:def:crs:EPSG:4326
    :return: the authority and the srid
    :rtype: tuple
    """
    authority = None
    srid = None
    values = srs_name.split(':')
    if srs_name.find('/def/crs/') != -1:  # URI Style 1
        vals = srs_name.split('/')
        authority = vals[5].upper()
        srid = int(vals[-1])
    elif srs_name.find('#') != -1:  # URI Style 2
        vals = srs_name.split('#')
        authority = vals[0].split('/')[-1].split('.')[0].upper()
        srid = int(vals[-1])
    elif len(values) > 2:  # it's a URN style
        if len(values) == 3:  # bogus
            pass
        else:
            authority = values[4].upper()
        # code is always the last value
        try:
            srid = int(values[-1])
        except Exception:
            srid = values[-1]
    elif len(values) == 2:  # it's an authority:code code
        authority = values[0].upper()

        try:
            srid = int(values[1])
        except Exception:
            srid = values[1]
    return authority, srid


def switch_axis_order(geometry):
    if isinstance(geometry, Polygon) or isinstance(geometry, GdalPolygon):
        coords = []
        for _polygon in geometry.coords:
            for coord in _polygon:
                coords.append((coord[1], coord[0]))
        return Polygon(tuple(coords), srid=geometry.srid)
    elif isinstance(geometry, MultiPolygon) or isinstance(geometry, GdalMultiPolygon):
        polygons = []
        for _polygon in geometry.coords:
            coords = []
            for coord in _polygon[0]:
                coords.append((coord[1], coord[0]))
            polygons.append(Polygon(tuple(coords), srid=geometry.srid))
        return MultiPolygon(polygons, srid=geometry.srid)
    elif isinstance(geometry, Point) or isinstance(geometry, GdalPoint):
        Point(x=geometry.y, y=geometry.x, srid=geometry.srid)


def adjust_axis_order(geometry):
    registry = Registry()
    epsg_sr = registry.get(srid=geometry.srid)
    if epsg_sr.is_yx_order:
        geometry = switch_axis_order(geometry)
    return geometry
