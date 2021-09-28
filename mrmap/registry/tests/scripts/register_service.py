import os
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "MrMap.settings_docker")

import django
django.setup()

from registry.enums.service import AuthTypeEnum
from registry.tasks.service import register_service
from registry.models.service import Service as DbService
from registry.parsers.ogc.capabilities import get_parsed_service
from registry.parsers.ogc.capabilities import ServiceType as XmlServiceType
from eulxml import xmlmap



def create_from_file():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    print(current_dir)
    import time

    start = time.time()
    path = Path(current_dir + '/../test_data/wms/dwd_wms_1.1.1.xml')
    parsed_service = get_parsed_service(xml=path)

    print("parsing took: " + str(time.time() - start))
    return
    start = time.time()
    db_service = DbService.xml_objects.create_from_parsed_service(parsed_service=parsed_service)
    print("persisting: " + str(time.time() - start))
    return db_service


def test_task_function():
    register_service(form={"auth_type": AuthTypeEnum.NONE.value,
                           #"registering_for_organization": "ff86445e-5eab-480e-95a7-b6a4cf7d6c24",
                           "test_url": "http://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&REQUEST=GetCapabilities&VERSION=1.1.1"})


if __name__ == '__main__':
    registered_service = create_from_file()
    #registered_service.delete()
