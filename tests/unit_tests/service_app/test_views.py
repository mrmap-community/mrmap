import logging
from django.test import TestCase, Client
from django.urls import reverse
from MapSkinner.consts import SERVICE_ADD
from service.forms import RegisterNewServiceWizardPage1
from service.tables import WmsServiceTable, WfsServiceTable, PendingTasksTable
from tests.baker_recipes.db_setup import *
from tests.baker_recipes.structure_app.baker_recipes import PASSWORD


class ServiceIndexViewTestCase(TestCase):
    def setUp(self):
        self.logger = logging.getLogger('ServiceViewTestCase')
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        create_wms_service(self.user.get_groups().first(), 10)
        create_wfs_service(self.user.get_groups().first(), 10)

    def test_get_index_view(self):
        response = self.client.get(
            reverse('service:index', ),
        )
        self.assertEqual(response.status_code, 200, )
        self.assertTemplateUsed(response=response, template_name="views/index.html")
        self.assertIsInstance(response.context["wms_table"], WmsServiceTable)
        self.assertEqual(len(response.context["wms_table"].rows), 10)
        # see if paging is working... only 5 elements by default should be listed
        self.assertEqual(len(response.context["wms_table"].page.object_list), 5)

        self.assertIsInstance(response.context["wfs_table"], WfsServiceTable)
        self.assertEqual(len(response.context["wfs_table"].rows), 10)
        # see if paging is working... only 5 elements by default should be listed
        self.assertEqual(len(response.context["wfs_table"].page.object_list), 5)

        self.assertIsInstance(response.context["pt_table"], PendingTasksTable)
        self.assertIsInstance(response.context["new_service_form"], RegisterNewServiceWizardPage1)
        self.assertEqual(reverse(SERVICE_ADD,), response.context["new_service_form"].action_url)


class ServiceAddViewTestCase(TestCase):

    def test_post_new_service_wizard_page1_valid_input(self):
        # ToDo:
        pass

    def test_post_new_service_wizard_page1_invalid_input(self):
        # ToDo:
        pass

    def test_post_new_service_wizard_page2(self):
        # ToDo:
        pass
