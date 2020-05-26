from django.core.exceptions import FieldError
from django.test import TestCase, RequestFactory
from django.urls import reverse
from django_tables2 import RequestConfig
from MrMap.consts import DJANGO_TABLES2_BOOTSTRAP4_CUSTOM_TEMPLATE
from service.models import Metadata
from service.tables import WmsLayerTable, WfsServiceTable, WmsServiceTable, PendingTasksTable, ChildLayerTable, \
    FeatureTypeTable, CoupledMetadataTable


class ServiceTestCase(TestCase):

    def setUp(self):
        self.factory = RequestFactory()

    def test_wms_service_table_sorting(self):
        # we just need an empty queryset
        md_list = Metadata.objects.all()

        wms_table = WmsServiceTable(md_list,
                                    order_by_field='swms',  # swms = sort wms
                                    user=None, )

        for column in wms_table.columns.columns:
            request = self.factory.get(reverse("service:wms-index") + '?{}={}'.format("swms", column))
            RequestConfig(request).configure(wms_table)

            exception = None
            try:
                # this line will raise a filederror exception if (i dont know why but it does)
                # custom rendered field without accessor has no custom order function
                list(wms_table.rows)
            except FieldError as e:
                exception = e
            self.assertEqual(exception, None,
                             msg="Field Error for field {} raised. Check your custom order function of table {}".format(
                                 column, "WmsServiceTable"))

    def test_wms_layer_table_sorting(self):
        # we just need an empty queryset
        md_list = Metadata.objects.all()

        wms_table = WmsLayerTable(md_list,
                                  order_by_field='swms',  # swms = sort wms
                                  user=None, )

        for column in wms_table.columns.columns:
            request = self.factory.get(reverse("service:wms-index") + '?{}={}'.format("swms", column))
            RequestConfig(request).configure(wms_table)

            exception = None
            try:
                # this line will raise a filederror exception if (i dont know why but it does)
                # custom rendered field without accessor has no custom order function
                list(wms_table.rows)
            except FieldError as e:
                exception = e
            self.assertEqual(exception, None,
                             msg="Field Error for field {} raised. Check your custom order function of table {}".format(
                                 column, "WmsLayerTable"))

    def test_wfs_layer_table_sorting(self):
        # we just need an empty queryset
        md_list = Metadata.objects.all()

        wfs_table = WfsServiceTable(md_list,
                                    order_by_field='swfs',  # swms = sort wms
                                    user=None, )

        for column in wfs_table.columns.columns:
            request = self.factory.get(reverse("service:wfs-index") + '?{}={}'.format("swfs", column))
            RequestConfig(request).configure(wfs_table)

            exception = None
            try:
                # this line will raise a filederror exception if (i dont know why but it does)
                # custom rendered field without accessor has no custom order function
                list(wfs_table.rows)
            except FieldError as e:
                exception = e
            self.assertEqual(exception, None,
                             msg="Field Error for field {} raised. Check your custom order function of table {}".format(
                                 column, "WfsServiceTable"))

    def test_pending_tasks_table_sorting(self):
        # we just need an empty queryset
        md_list = Metadata.objects.all()

        table = PendingTasksTable(md_list,
                                  order_by_field='sort',  # swms = sort wms
                                  user=None, )

        for column in table.columns.columns:
            request = self.factory.get(reverse("service:pending-tasks") + '?{}={}'.format("sort", column))
            RequestConfig(request).configure(table)

            exception = None
            try:
                # this line will raise a filederror exception if (i dont know why but it does)
                # custom rendered field without accessor has no custom order function
                list(table.rows)
            except FieldError as e:
                exception = e
            self.assertEqual(exception, None,
                             msg="Field Error for field {} raised. Check your custom order function of table {}".format(
                                 column, "PendingTasksTable"))

    def test_child_layer_table_sorting(self):
        # we just need an empty queryset
        md_list = Metadata.objects.all()

        table = ChildLayerTable(md_list,
                                order_by_field='sort',  # swms = sort wms
                                user=None, )

        for column in table.columns.columns:
            # to match the reverse we use dummy id 1. It's ok, cause no request on views will be done
            request = self.factory.get(reverse("service:get-metadata-html", args=(1,)) + '?{}={}'.format("sort", column))
            RequestConfig(request).configure(table)

            exception = None
            try:
                # this line will raise a filederror exception if (i dont know why but it does)
                # custom rendered field without accessor has no custom order function
                list(table.rows)
            except FieldError as e:
                exception = e
            self.assertEqual(exception, None,
                             msg="Field Error for field {} raised. Check your custom order function of table {}".format(
                                 column, "ChildLayerTable"))

    def test_featuretype_table_sorting(self):
        # we just need an empty queryset
        md_list = Metadata.objects.all()

        table = FeatureTypeTable(md_list,
                                 order_by_field='sort',  # swms = sort wms
                                 user=None, )

        for column in table.columns.columns:
            # to match the reverse we use dummy id 1. It's ok, cause no request on views will be done
            request = self.factory.get(reverse("service:get-metadata-html", args=(1,)) + '?{}={}'.format("sort", column))
            RequestConfig(request).configure(table)

            exception = None
            try:
                # this line will raise a filederror exception if (i dont know why but it does)
                # custom rendered field without accessor has no custom order function
                list(table.rows)
            except FieldError as e:
                exception = e
            self.assertEqual(exception, None,
                             msg="Field Error for field {} raised. Check your custom order function of table {}".format(
                                 column, "FeatureTypeTable"))

    def test_coupled_metadata_table_sorting(self):
        # we just need an empty queryset
        md_list = Metadata.objects.all()

        table = CoupledMetadataTable(md_list,
                                     order_by_field='sort',  # swms = sort wms
                                     user=None, )

        for column in table.columns.columns:
            # to match the reverse we use dummy id 1. It's ok, cause no request on views will be done
            request = self.factory.get(reverse("service:get-metadata-html", args=(1,)) + '?{}={}'.format("sort", column))
            RequestConfig(request).configure(table)

            exception = None
            try:
                # this line will raise a filederror exception if (i dont know why but it does)
                # custom rendered field without accessor has no custom order function
                list(table.rows)
            except FieldError as e:
                exception = e
            self.assertEqual(exception, None,
                             msg="Field Error for field {} raised. Check your custom order function of table {}".format(
                                 column, "CoupledMetadataTable"))
