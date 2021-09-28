from django.contrib.gis.geos import GEOSGeometry
from eulxml import xmlmap
from axis_order_cache.utils import get_epsg_srid, adjust_axis_order


class Gml(xmlmap.XmlObject):
    srs_name = xmlmap.StringField(xpath="./@srsName")

    def to_gml(self) -> GEOSGeometry:
        return GEOSGeometry.from_gml(self.serialize())

    def get_geometry(self, axis_order_correction: bool = True):
        """Parse the gml found by xpath and return it as Point or Polygon

        .. warning: unclear which axis order in different versions of gml shall be used.
           **GML 3.1.1 (see 12.4.1.3 page 113 of the OGC 03-105r1 document)**:
           Bearing in mind that the order of the coordinates in a coordinate tuple shall be the same as the defined
           order of the coordinate axes, the ‘i-th’ coordinate axis of a coordinate system is defined as the locus of
           points for which all coordinates with sequence number not equal to ‘i’, have a constant value locally
           (whereby i = 1 ...n, and n is the dimension of the coordinate space).

           But wfs < 2.0.0, which also uses gml 3.1.1 version, uses the x, y (mathematical interpretation) axis
           ordering.

        The default handling is to parse the gml, instantiate a GEOSGeometry and request the epsg api how the
        coordinates of the parsed gml shall be interpreted. IF the epsg api tells us that the axis order is y, x
        (mathematical interpretation), the axis order will be switched. IF you want to prohibit the axis switching,
        you can pass the axis_order_correction flag.

        :param axis_order_correction: boolean flag to prohibit axis switching by epsg api.

        :return: in case of point geometry it return a Point from the geos library. ELIF it is a polygon geometry it
        return a Polygon from the geos library.
        :rtype: :class:`django.contrib.gis.geos.polygon.Point` or :class:`django.contrib.gis.geos.polygon.Polygon`
        """
        geometry = self.to_gml()
        if self.srs_name:
            authority, srid = get_epsg_srid(self.srs_name)
        else:
            srid = 4326
        geometry = GEOSGeometry(geo_input=geometry.wkt, srid=srid)
        if axis_order_correction:
            geometry = adjust_axis_order(geometry)
        return geometry
