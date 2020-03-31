import logging

from django.contrib.messages import get_messages
from django.test import TestCase, Client
from django.urls import reverse
from MapSkinner.consts import SERVICE_ADD
from MapSkinner.settings import ROOT_URL
from service.forms import RegisterNewServiceWizardPage1, RegisterNewServiceWizardPage2
from service.helper.enums import OGCServiceEnum
from service.tables import WmsServiceTable, WfsServiceTable, PendingTasksTable
from structure.models import PendingTask
from tests.baker_recipes.db_setup import *
from tests.baker_recipes.structure_app.baker_recipes import PASSWORD
from tests.test_data import get_capabilitites_url


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

    def setUp(self):
        self.logger = logging.getLogger('ServiceViewTestCase')
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)

    def test_redirect_if_http_get(self):
        response = self.client.get(reverse('service:add'))
        self.assertEqual(response.status_code, 302, msg="No redirect was done")
        self.assertEqual(response.url, reverse('service:index'), msg="Redirect wrong")

    def test_permission_denied_page1(self):
        post_params = {
            'page': '1',
            'get_request_uri': get_capabilitites_url().get('valid')
        }

        # remove permission to add new services
        perm = self.user.get_groups()[0].role.permission
        perm.can_register_service = False
        perm.save()

        response = self.client.post(reverse('service:add'), HTTP_REFERER=reverse('service:add'), data=post_params,)
        self.assertEqual(response.status_code, 302)
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn('You do not have permissions for this!', messages)

    def test_post_new_service_wizard_page1_valid_input(self):
        post_params={
            'page': '1',
            'get_request_uri': get_capabilitites_url().get('valid')
        }

        response = self.client.post(reverse('service:add'), data=post_params)

        self.assertEqual(response.status_code, 200,)
        self.assertIsInstance(response.context['new_service_form'], RegisterNewServiceWizardPage2)

    def test_post_new_service_wizard_page1_invalid_version(self):
        post_params = {
            'page': '1',
            'get_request_uri': get_capabilitites_url().get('invalid_version')
        }

        response = self.client.post(reverse('service:add'), data=post_params)

        self.assertEqual(response.status_code, 200, )
        self.assertIsInstance(response.context['new_service_form'], RegisterNewServiceWizardPage1)
        self.assertFormError(response, 'new_service_form', 'get_request_uri', 'The given {} version {} is not supported from Mr. Map.'.format(OGCServiceEnum.WMS.value, '9.4.0'))

    def test_post_new_service_wizard_page1_invalid_no_service(self):
        post_params = {
            'page': '1',
            'get_request_uri': get_capabilitites_url().get('invalid_no_service')
        }

        response = self.client.post(reverse('service:add'), data=post_params)

        self.assertEqual(response.status_code, 200, )
        self.assertIsInstance(response.context['new_service_form'], RegisterNewServiceWizardPage1)
        self.assertFormError(response, 'new_service_form', 'get_request_uri', 'The given uri is not valid cause there is no service parameter.')

    def test_post_new_service_wizard_page1_invalid_no_version(self):
        post_params = {
            'page': '1',
            'get_request_uri': get_capabilitites_url().get('invalid_no_version')
        }

        response = self.client.post(reverse('service:add'), data=post_params)

        self.assertEqual(response.status_code, 200, )
        self.assertIsInstance(response.context['new_service_form'], RegisterNewServiceWizardPage1)
        self.assertFormError(response, 'new_service_form', 'get_request_uri', 'The given uri is not valid cause there is no version parameter.')

    def test_post_new_service_wizard_page1_invalid_no_request(self):
        post_params = {
            'page': '1',
            'get_request_uri': get_capabilitites_url().get('invalid_no_request')
        }

        response = self.client.post(reverse('service:add'), data=post_params)

        self.assertEqual(response.status_code, 200, )
        self.assertIsInstance(response.context['new_service_form'], RegisterNewServiceWizardPage1)
        self.assertFormError(response, 'new_service_form', 'get_request_uri', 'The given uri is not valid cause there is no request parameter.')

    def test_post_new_service_wizard_page1_invalid_servicetype(self):
        post_params = {
            'page': '1',
            'get_request_uri': get_capabilitites_url().get('invalid_servicetype')
        }

        response = self.client.post(reverse('service:add'), data=post_params)

        self.assertEqual(response.status_code, 200, )
        self.assertIsInstance(response.context['new_service_form'], RegisterNewServiceWizardPage1)
        self.assertFormError(response, 'new_service_form', 'get_request_uri', 'The given service typ is not supported from Mr. Map.')

    def test_post_new_service_wizard_page2(self):

        post_params = {
            'page': '2',
            'is_form_update': 'False',
            'ogc_request': 'GetCapabilities',
            'ogc_service': 'wms',
            'ogc_version': '1.3.0',
            'uri': 'http://geo5.service24.rlp.de/wms/karte_rp.fcgi?',
            'registering_with_group': '1',
        }

        response = self.client.post(reverse('service:add'), data=post_params)
        self.assertEqual(response.status_code, 302, )
        self.assertEqual(response.url, reverse('service:index'), msg="Redirect wrong")
        self.assertEqual(PendingTask.objects.all().count(), 1)
