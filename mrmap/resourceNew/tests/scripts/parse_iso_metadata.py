import os
from pathlib import Path


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "MrMap.settings_docker")

import django
django.setup()

from resourceNew.models.service import Service as DbService
from resourceNew.parsers.iso_metadata import get_parsed_iso_metadata


def create_from_file():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    print(current_dir)
    import time

    start = time.time()
    path = Path(current_dir + '/../test_data/iso_md/RBSN_FF.xml')
    parsed_service = get_parsed_iso_metadata(xml=path)

    print("parsing took: " + str(time.time() - start))
    return
    start = time.time()
    db_service = DbService.xml_objects.create_from_parsed_service(parsed_service=parsed_service)
    print("persisting: " + str(time.time() - start))
    return db_service


if __name__ == '__main__':
    db_metadata = create_from_file()
    #registered_service.delete()
