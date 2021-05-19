from django.test import TestCase
import os
from eulxml import xmlmap

from service.serializer.ogc.parser.new import Service as XmlService
from service.models import Service as DbService


class ServiceXmlManagerTestCase(TestCase):

    def test_create(self):
        """

        """
        current_dir = os.path.dirname(os.path.abspath(__file__))
        parsed_service = xmlmap.load_xmlobject_from_file(filename=current_dir + '/test_data/dwd_wms_1.3.0.xml', xmlclass=XmlService)

        DbService.objects.create(parsed_service=parsed_service)
