from axis_order_cache.utils import get_epsg_srid
from django.contrib.gis.geos import GEOSGeometry
from eulxml import xmlmap


class Gml(xmlmap.XmlObject):
    srs_name = xmlmap.StringField(xpath="./@srsName")

    @property
    def geos(self) -> GEOSGeometry:
        geometry = GEOSGeometry.from_gml(self.serialize())
        if self.srs_name:
            authority, srid = get_epsg_srid(self.srs_name)
        else:
            srid = 4326
        return GEOSGeometry(geo_input=geometry.wkt, srid=srid)
