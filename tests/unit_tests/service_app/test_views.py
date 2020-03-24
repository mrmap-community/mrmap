import logging
from django.test import TestCase, Client
from django.urls import reverse
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
        self.logger.debug(response.__dict__)
        self.assertEqual(response.status_code, 200, )
        self.assertTemplateUsed(response=response, template_name="views/index.html")

        # ToDo: proof if the new service form is in the context
        # ToDo: proof if the wms_table is in the context
        # ToDo: proof if the wfs_table is in the context
        # ToDo: proof if the PendingTasksTable is in the context

    def test_post_new_service_wizard_page1_valid_input(self):
        # ToDo:
        pass

    def test_post_new_service_wizard_page1_invalid_input(self):
        # ToDo:
        pass

    def test_post_new_service_wizard_page2(self):
        # ToDo:
        pass
