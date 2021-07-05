import os
from pathlib import Path

from resourceNew.parsers.ogc.feature_collection import FeatureCollection

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "MrMap.settings_docker")

import django
django.setup()

from resourceNew.models.service import Service as DbService
from resourceNew.models import RemoteMetadata
from resourceNew.tasks.service import schedule_collect_linked_metadata
from eulxml import xmlmap
from resourceNew.parsers.iso.iso_metadata import WrappedIsoMetadata




if __name__ == '__main__':
    current_dir = os.path.dirname(os.path.abspath(__file__))

    fc = xmlmap.load_xmlobject_from_file(
        filename=current_dir + '/../test_data/feature_collection/dwd_2m.xml',
        xmlclass=FeatureCollection)
    poly = fc.bounded_by.get_geometry()

    poly2 = fc.members[0].geom.get_geometry()

    i=0
