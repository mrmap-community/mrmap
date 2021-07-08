from django.contrib.gis.gdal import SpatialReference
from django.contrib.gis.geos import Polygon, GEOSGeometry, Point
from eulxml import xmlmap

from epsg_registry_offline.registry import Registry
from epsg_registry_offline.utils import get_epsg_srid
from resourceNew.parsers.consts import NS_WC


class Gml(xmlmap.XmlObject):
    srs_name = xmlmap.StringField(xpath="./@srsName")

    def to_gml(self) -> GEOSGeometry:
        return GEOSGeometry.from_gml(self.serialize())

    def get_geometry(self):
        """
        **GML 3.1.1 (see 12.4.1.3 page 113 of the OGC 03-105r1 document)**:
        Bearing in mind that the order of the coordinates in a coordinate tuple shall be the same as the defined order
        of the coordinate axes, the ‘i-th’ coordinate axis of a coordinate system is defined as the locus of points for
        which all coordinates with sequence number not equal to ‘i’, have a constant value locally (whereby i = 1 ...n,
        and n is the dimension of the coordinate space).
        """
        geometry = self.to_gml()
        if self.srs_name:
            authority, srid = get_epsg_srid(self.srs_name)
        else:
            srid = 4326

        # FIXME: unclear which axis order in different versions of gml shall be used.
        sr = SpatialReference(srs_input=srid)
        registry = Registry()
        epsg_sr = registry.get(srid=sr.srid)

        if isinstance(geometry, Polygon):
            if epsg_sr.is_xy_order:
                return Polygon(geometry.coords, srid=int(srid))
            else:
                for geom in geometry.coords:
                    coords = []
                    for coord in geom:
                        coords.append((coord[1], coord[0]))
                    return Polygon(tuple(coords), srid=srid)
        elif isinstance(geometry, Point):
            if epsg_sr.is_xy_order:
                return Point(geometry.coords, srid=int(srid))
            else:
                return Point((geometry.coords[1], geometry.coords[0]), srid=srid)


class Member(xmlmap.XmlObject):
    bounded_by = xmlmap.NodeField(xpath=f"//{NS_WC}boundedBy']/gml:*", node_class=Gml)
    geom = xmlmap.NodeField(xpath=f"//{NS_WC}THE_GEOM']/gml:*", node_class=Gml)


class FeatureCollection(xmlmap.XmlObject):
    number_matched = xmlmap.IntegerField(xpath=f"@numberMatched")
    number_returned = xmlmap.IntegerField(xpath=f"@numberReturned")
    bounded_by = xmlmap.NodeField(xpath=f"{NS_WC}boundedBy']/gml:*", node_class=Gml)
    members = xmlmap.NodeListField(xpath=f"{NS_WC}member']", node_class=Member)

