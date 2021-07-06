import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "MrMap.settings_docker")

import django
django.setup()

from resourceNew.models.service import Service as DbService
from resourceNew.models import RemoteMetadata
from resourceNew.tasks.service import schedule_collect_linked_metadata
from eulxml import xmlmap
from resourceNew.parsers.iso.iso_metadata import WrappedIsoMetadata
from resourceNew.parsers.ogc.wfs_filter import GetFeature


if __name__ == '__main__':
    current_dir = os.path.dirname(os.path.abspath(__file__))

    get_feature_xml = xmlmap.load_xmlobject_from_file(
        filename=current_dir + '/../test_data/wfs_filter/geo5_gemarkung_wfs.xml',
        xmlclass=GetFeature)
    get_feature_xml.secure_spatial("test", 4326, "1 2 2 1")

    i=0
