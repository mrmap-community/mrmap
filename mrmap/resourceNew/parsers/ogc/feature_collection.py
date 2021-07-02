from django.contrib.gis.gdal import SpatialReference
from django.contrib.gis.geos import Polygon
from eulxml import xmlmap

from epsg_registry_offline.registry import Registry
from epsg_registry_offline.utils import get_epsg_srid


class BoundingBox(xmlmap.XmlObject):
    srs_name = xmlmap.StringField(xpath="./@srsName")
    coordinates = xmlmap.StringField(xpath="./gml:coordinates")

    def get_polygon(self):
        """

        **GML 3.1.1 (see 12.4.1.3 page 113 of the OGC 03-105r1 document)**:
        Bearing in mind that the order of the coordinates in a coordinate tuple shall be the same as the defined order
        of the coordinate axes, the ‘i-th’ coordinate axis of a coordinate system is defined as the locus of points for
        which all coordinates with sequence number not equal to ‘i’, have a constant value locally (whereby i = 1 ...n,
        and n is the dimension of the coordinate space).

        """
        lat_point = self.coordinates.split(" ", 1)[0]
        lon_point = self.coordinates.split(" ", 1)[1]

        min_x = lat_point.split(",", 1)[0]
        min_y = lat_point.split(",", 1)[1]
        max_x = lon_point.split(",", 1)[0]
        max_y = lon_point.split(",", 1)[1]

        min_x = float(min_x)
        min_y = float(min_y)
        max_x = float(max_x)
        max_y = float(max_y)

        authority, srid = get_epsg_srid(self.srs_name)

        # dynamic axis order possible; we need to use the epsg api
        # gml 3.1.1 >= traditional without epsg api
        # gml > 3.1.1 epsg api request
        sr = SpatialReference(srs_input=srid)
        registry = Registry()
        epsg_sr = registry.get(srid=sr.srid)

        if epsg_sr.is_xy_order:
            return Polygon(((min_x, min_y), (min_x, max_y), (max_x, max_y), (max_x, min_y), (min_x, min_y)),
                           srid=int(srid))
        else:
            return Polygon(((min_y, min_x), (max_y, min_x), (max_y, max_x), (min_y, max_x), (min_y, min_x)),
                           srid=int(srid))


class FeatureCollection(xmlmap.XmlObject):
    bounded_by = xmlmap.NodeField(xpath="//gml:boundedBy/gml:Box", node_class=BoundingBox)
