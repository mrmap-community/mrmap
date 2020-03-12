from pprint import pprint

from django.core.exceptions import FieldError
from django.test import TestCase, RequestFactory
from django.urls import reverse
from django_tables2 import RequestConfig

from MapSkinner.consts import DJANGO_TABLES2_BOOTSTRAP4_CUSTOM_TEMPLATE
from MapSkinner.utils import prepare_table_pagination_settings
from service.helper.enums import OGCServiceEnum
from service.models import Metadata
from service.tables import WmsLayerTable
from tests.db_setup import *


class ServiceTestCase(TestCase):

    def setUp(self):
        self.factory = RequestFactory()

    def test_wms_layer_table_sorting(self):
        # we just need an empty queryset
        md_list_wms = Metadata.objects.all()

        pprint('metadata len: ' + str(len(md_list_wms)))

        wms_table = WmsLayerTable(md_list_wms,
                                  template_name=DJANGO_TABLES2_BOOTSTRAP4_CUSTOM_TEMPLATE,
                                  order_by_field='swms',  # swms = sort wms
                                  user=None, )


        request = self.factory.get(reverse("service:wms-index") + '?{}'.format("swms=wms_parent_service"))
        RequestConfig(request).configure(wms_table)
        # TODO: check sorting of all fields dynamic with loop
        exception = None
        try:
            # this line will raise a filederror exception if
            # custom renderd field without accessor has no custom order function
            list(wms_table.rows)
        except FieldError as e:
            exception = e
        self.assertEqual(exception, None, msg="Field Error for field {} raised. Check your custom order function of table {}".format("wms_parent_service", "WmsLayerTable"))