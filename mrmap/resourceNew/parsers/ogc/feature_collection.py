from django.contrib.gis.geos import Polygon
from eulxml import xmlmap


class BoundingBox(xmlmap.XmlObject):
    srs_name = xmlmap.StringField(xpath="./@srsName")
    coordinates = xmlmap.StringField(xpath="./gml:coordinates")

    def get_polygon(self):
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

        srid = self.srs_name.split("/")[-1]
        if "#" in srid:
            srid = srid.split("#")[-1]
        # FIXME: dynamic axis order possible; we need to use the epsg api
        #  gml 3.1.1 <= traditional without epsg api
        #  gml > 3.1.1 epsg api request
        return Polygon(((min_x, min_y), (min_x, max_y), (max_x, max_y), (max_x, min_y), (min_x, min_y)), srid=int(srid))


class FeatureCollection(xmlmap.XmlObject):
    bounded_by = xmlmap.NodeField(xpath="//gml:boundedBy/gml:Box", node_class=BoundingBox)
