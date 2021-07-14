import os
from pathlib import Path

from django.contrib.gis.geos import GEOSGeometry

from epsg_registry_offline.registry import Registry
from resourceNew.ows_client.request_builder import WebService
from resourceNew.parsers.ogc.feature_collection import FeatureCollection

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "MrMap.settings_docker")

import django
django.setup()

from resourceNew.models.service import Service as DbService
from resourceNew.models import RemoteMetadata
from resourceNew.tasks.service import schedule_collect_linked_metadata
from resourceNew.parsers.iso.iso_metadata import WrappedIsoMetadata, Polygon

if __name__ == '__main__':

    polygon = GEOSGeometry.from_gml('<gml:Polygon><gml:outerBoundaryIs><gml:LinearRing><gml:coordinates decimal="." cs="," ts=" ">7.294921874999999,50.32091555536218 7.28668212890625,50.24720490139267 7.393798828125,50.198001033269506 7.327880859374999,49.983020075472226 7.75360107421875,50.13994558740855 7.8662109375,50.327929664466275 7.599792480468749,50.51167994970682 7.294921874999999,50.32091555536218</gml:coordinates></gml:LinearRing></gml:outerBoundaryIs></gml:Polygon>')
    service = WebService.manufacture_service(url="http://example.com/geoserver/wfs?service=wfs&version=2.0.0&request=GetFeature&typeNames=namespace:featuretype&srsName=EPSG:4326&bbox=6.92962646484375,49.908787000867136,8.470458984375,50.62855775525792")

    xml = service.construct_filter_xml(polygon=polygon.ogr)
    i=0
