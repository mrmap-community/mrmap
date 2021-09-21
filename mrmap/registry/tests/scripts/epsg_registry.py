import os
from pathlib import Path

from epsg_registry_offline.registry import Registry
from registry.parsers.ogc.feature_collection import FeatureCollection

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "MrMap.settings_docker")

import django
django.setup()

from registry.models.service import Service as DbService
from registry.models import RemoteMetadata
from registry.tasks.service import schedule_collect_linked_metadata
from registry.parsers.iso.iso_metadata import WrappedIsoMetadata




if __name__ == '__main__':

    registry = Registry()
    crs = registry.coord_ref_system_export(srid=4326)
    i=0
