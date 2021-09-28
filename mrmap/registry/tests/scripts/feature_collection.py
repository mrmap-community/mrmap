import os
from pathlib import Path

from registry.parsers.ogc.feature_collection import FeatureCollection

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "MrMap.settings_docker")

import django
django.setup()

from registry.models.service import Service as DbService
from registry.models import RemoteMetadata
from registry.tasks.service import schedule_collect_linked_metadata
from eulxml import xmlmap
from registry.parsers.iso.iso_metadata import WrappedIsoMetadata




if __name__ == '__main__':
    current_dir = os.path.dirname(os.path.abspath(__file__))

    import time
    start = time.time()
    fc = xmlmap.load_xmlobject_from_file(
        filename=current_dir + '/../test_data/feature_collection/operation2.xml',
        xmlclass=FeatureCollection)
    print(time.time() - start)
    poly = fc.bounded_by.get_geometry()

    poly2 = fc.members[0].geom.get_geometry()

    i=0
