import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "MrMap.settings_docker")

import django
django.setup()

from resourceNew.enums.service import AuthTypeEnum
from resourceNew.tasks import async_create_from_parsed_service
from resourceNew.models.service import Service as DbService
from resourceNew.parsers.capabilities import Service as XmlService
from eulxml import xmlmap


def create_from_file():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    print(current_dir)
    import time

    start = time.time()
    parsed_service = xmlmap.load_xmlobject_from_file(filename=current_dir + '/../test_data/wasserschutz_1.3.0.xml',
                                                     xmlclass=XmlService)
    print("parsing took: " + str(time.time() - start))

    start = time.time()
    db_service = DbService.xml_objects.create_from_parsed_service(parsed_service=parsed_service)
    print("persisting: " + str(time.time() - start))
    return db_service


def test_task_function():
    async_create_from_parsed_service(form={"auth_type": AuthTypeEnum.NONE.value,
                                           #"registering_for_organization": "ff86445e-5eab-480e-95a7-b6a4cf7d6c24",
                                           "test_url": "http://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&REQUEST=GetCapabilities&VERSION=1.1.1"})


if __name__ == '__main__':
    registered_service = create_from_file()
    registered_service.delete()
