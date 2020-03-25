import logging
from django.test import TestCase, Client
from django.urls import reverse

from MapSkinner.consts import SERVICE_ADD
from service.forms import RegisterNewServiceWizardPage1
from service.tables import WmsServiceTable, WfsServiceTable, PendingTasksTable
from tests.db_setup import create_active_user
from tests.helper import _login
from tests.test_data import get_password_data


class ServiceIndexViewTestCase(TestCase):
    def setUp(self):
        self.logger = logging.getLogger('ServiceViewTestCase')
        self.user_password = get_password_data().get('valid')
        self.user = create_active_user("Testuser", self.user_password, "test@example.com")

    def test_get_index_view(self):
        client = _login(self.user.username, self.user_password, Client())

        response = client.get(
            reverse('service:index', ),
        )
        self.assertEqual(response.status_code, 200, )
        self.assertTemplateUsed(response=response, template_name="views/index.html")
        self.assertIsInstance(response.context["wms_table"], WmsServiceTable)
        self.assertIsInstance(response.context["wfs_table"], WfsServiceTable)
        self.assertIsInstance(response.context["pt_table"], PendingTasksTable)
        self.assertIsInstance(response.context["new_service_form"], RegisterNewServiceWizardPage1)
        self.assertEqual(reverse(SERVICE_ADD,), response.context["new_service_form"].action_url)

    def test_post_new_service_wizard_page1_valid_input(self):
        # ToDo:
        pass

    def test_post_new_service_wizard_page1_invalid_input(self):
        # ToDo:
        pass

    def test_post_new_service_wizard_page2(self):
        # ToDo:
        pass
