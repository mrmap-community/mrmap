import os
from pathlib import Path


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "MrMap.settings_docker")

import django
django.setup()

from resourceNew.models.service import Service as DbService
from resourceNew.models import RemoteMetadata
from resourceNew.tasks import get_linked_metadata


def create_from_file():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    print(current_dir)
    import time

    start = time.time()
    path = Path(current_dir + '/../test_data/iso_md/RBSN_FF.xml')
    #parsed_service = get_parsed_iso_metadata(xml=path)

    print("parsing took: " + str(time.time() - start))
    return
    start = time.time()
    db_service = DbService.xml_objects.create_from_parsed_service(parsed_service=parsed_service)
    print("persisting: " + str(time.time() - start))
    return db_service


def db_process():
    remote_metadata = RemoteMetadata.objects.get(pk=7)
    #remote_metadata.fetch_remote_content()

    #db_metadata = remote_metadata.create_metadata_instance()
    task_id = get_linked_metadata("3e3538b9-1550-4c5c-a8c5-6efa86df4bce")

    #db_metadata.delete()


if __name__ == '__main__':
    db_process()
