import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "MrMap.settings_docker")

import django
django.setup()

from resourceNew.models.service import Service as DbService
from resourceNew.models import RemoteMetadata
from resourceNew.tasks.service import schedule_collect_linked_metadata
from eulxml import xmlmap
from resourceNew.parsers.iso.iso_metadata import WrappedIsoMetadata
from resourceNew.parsers.ogc.wfs_get_feature import GetFeature
from django.contrib.gis.geos import Polygon


if __name__ == '__main__':
    current_dir = os.path.dirname(os.path.abspath(__file__))

    get_feature_xml = xmlmap.load_xmlobject_from_file(
        filename=current_dir + '/../test_data/wfs_filter/geo5_gemarkung_wfs.xml',
        xmlclass=GetFeature)
    poly = Polygon(((1, 2), (2, 2), (2, 1), (2, 2), (1, 2)), srid=4326)
    get_feature_xml.filter.secure_spatial("test", poly)

    i=0
