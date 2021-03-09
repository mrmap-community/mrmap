from django.core.exceptions import FieldError
from django.test import TestCase, RequestFactory
from django.urls import reverse
from django_tables2 import RequestConfig

from MrMap.consts import SERVICE_INDEX_LOG
from service.models import Metadata, ProxyLog
from service.tables import ChildLayerTable, FeatureTypeTable, CoupledMetadataTable, ProxyLogTable, OgcServiceTable, \
    PendingTaskTable
from tests.baker_recipes.db_setup import create_guest_groups, create_superadminuser, create_proxy_logs, create_testuser
from tests.utils import check_table_sorting

TEST_URI = "http://test.com?request=GetTest"


class ServiceTestCase(TestCase):

    def setUp(self):
        self.default_user = create_testuser()
        self.factory = RequestFactory()
        self.request = self.factory.get(
            TEST_URI,
        )
        self.request.user = self.default_user

    def test_wms_service_table_sorting(self):
        # we just need an empty queryset
        md_list = Metadata.objects.all()

        wms_table = OgcServiceTable(data=md_list,
                                    order_by_field='swms',  # swms = sort wms
                                    request=self.request, )

        for column in wms_table.columns.columns:
            request = self.factory.get(reverse("resource:wms-index") + '?{}={}'.format("swms", column))
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

        wms_table = OgcServiceTable(data=md_list,
                                    order_by_field='swms',  # swms = sort wms
                                    request=self.request, )

        for column in wms_table.columns.columns:
            request = self.factory.get(reverse("resource:wms-index") + '?{}={}'.format("swms", column))
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

        wfs_table = OgcServiceTable(data=md_list,
                                    order_by_field='swfs',  # swms = sort wms
                                    request=self.request, )

        for column in wfs_table.columns.columns:
            request = self.factory.get(reverse("resource:wfs-index") + '?{}={}'.format("swfs", column))
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

        table = PendingTaskTable(data=md_list,
                                 order_by_field='sort',  # swms = sort wms
                                 request=self.request, )

        for column in table.columns.columns:
            request = self.factory.get(reverse("resource:pending-tasks") + '?{}={}'.format("sort", column))
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

        table = ChildLayerTable(queryset=md_list,
                                order_by_field='sort',  # swms = sort wms
                                request=self.request, )

        for column in table.columns.columns:
            # to match the reverse we use dummy id 1. It's ok, cause no request on views will be done
            request = self.factory.get(reverse("resource:get-metadata-html", args=(1,)) + '?{}={}'.format("sort", column))
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

        table = FeatureTypeTable(queryset=md_list,
                                 order_by_field='sort',  # swms = sort wms
                                 request=self.request, )

        for column in table.columns.columns:
            # to match the reverse we use dummy id 1. It's ok, cause no request on views will be done
            request = self.factory.get(reverse("resource:get-metadata-html", args=(1,)) + '?{}={}'.format("sort", column))
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

        table = CoupledMetadataTable(queryset=md_list,
                                     order_by_field='sort',  # swms = sort wms
                                     request=self.request, )

        for column in table.columns.columns:
            # to match the reverse we use dummy id 1. It's ok, cause no request on views will be done
            request = self.factory.get(reverse("resource:get-metadata-html", args=(1,)) + '?{}={}'.format("sort", column))
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

    def test_proxy_log_table_sorting(self):
        """ Run test to check the sorting functionality of the ProxyLogTable

        Return:

        """
        groups = create_guest_groups(how_much_groups=9)
        user = create_superadminuser(groups=groups)
        request_factory = RequestFactory()
        # Create an instance of a GET request.
        request = request_factory.get('/')
        # Recall that middleware are not supported. You can simulate a
        # logged-in user by setting request.user manually.
        request.user = user
        create_proxy_logs(user, 10)

        # Get all logs, make sure the initial set is ordered by random
        logs = ProxyLog.objects.all().order_by("?")
        sorting_param = "sort"
        table = ProxyLogTable(
            data=logs,
            order_by_field=sorting_param,
            request=request
        )
        # Check table sorting
        sorting_implementation_failed, sorting_results = check_table_sorting(
            table=table,
            url_path_name=SERVICE_INDEX_LOG,
        )

        for key, val in sorting_results.items():
            self.assertTrue(val, msg="ProxyLog table sorting not correct for column '{}'".format(key))
        for key, val in sorting_implementation_failed.items():
            self.assertFalse(val, msg="ProxyLog table sorting leads to error for column '{}'".format(key))
