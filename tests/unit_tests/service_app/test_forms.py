from django.test import TestCase

from service.forms import RegisterNewServiceWizardPage1
from tests.test_data import get_capabilitites_url


class RegisterNewServiceWizardPage1TestCase(TestCase):
    """
        This testcase will proof if something are bad configured in our RegisterNewServiceWizardPage1.
        Current requirements are:

            valid getCapabilities URL is inserted

    """
    def setUp(self):
        self.params = {
                        'page': '1',
                      }
        self.get_capabilities_urls = get_capabilitites_url()

    def test_invalid_get_capabilitites_url_valid_wms_version_130(self):
        self.params.update({
            'get_request_uri': self.get_capabilities_urls.get('valid_wms_version_130'),
        })
        form = RegisterNewServiceWizardPage1(data=self.params)
        self.assertTrue(form.is_valid(), msg="get request uri with wms version 1.3.0 should be valid.")

    def test_invalid_get_capabilitites_url_valid_wms_version_111(self):
        self.params.update({
            'get_request_uri': self.get_capabilities_urls.get('valid_wms_version_111'),
        })
        form = RegisterNewServiceWizardPage1(data=self.params)
        self.assertTrue(form.is_valid(), msg="get request uri with wms version 1.1.1 should be valid.")

    def test_invalid_get_capabilitites_url_valid_wms_version_110(self):
        self.params.update({
            'get_request_uri': self.get_capabilities_urls.get('valid_wms_version_110'),
        })
        form = RegisterNewServiceWizardPage1(data=self.params)
        self.assertTrue(form.is_valid(), msg="get request uri with wms version 1.1.0 should be valid.")

    def test_invalid_get_capabilitites_url_valid_wms_version_100(self):
        self.params.update({
            'get_request_uri': self.get_capabilities_urls.get('valid_wms_version_100'),
        })
        form = RegisterNewServiceWizardPage1(data=self.params)
        self.assertTrue(form.is_valid(), msg="get request uri with wms version 1.0.0 should be valid.")

    def test_invalid_get_capabilitites_url_valid_wfs_version_202(self):
        self.params.update({
            'get_request_uri': self.get_capabilities_urls.get('valid_wfs_version_202'),
        })
        form = RegisterNewServiceWizardPage1(data=self.params)
        self.assertTrue(form.is_valid(), msg="get request uri with wfs version 2.0.2 should be valid.")

    def test_invalid_get_capabilitites_url_valid_wfs_version_200(self):
        self.params.update({
            'get_request_uri': self.get_capabilities_urls.get('valid_wfs_version_200'),
        })
        form = RegisterNewServiceWizardPage1(data=self.params)
        self.assertTrue(form.is_valid(), msg="get request uri with wfs version 2.0.0 should be valid.")

    def test_invalid_get_capabilitites_url_valid_wfs_version_110(self):
        self.params.update({
            'get_request_uri': self.get_capabilities_urls.get('valid_wfs_version_110'),
        })
        form = RegisterNewServiceWizardPage1(data=self.params)
        self.assertTrue(form.is_valid(), msg="get request uri with wfs version 1.1.0 should be valid.")

    def test_invalid_get_capabilitites_url_valid_wfs_version_100(self):
        self.params.update({
            'get_request_uri': self.get_capabilities_urls.get('valid_wfs_version_100'),
        })
        form = RegisterNewServiceWizardPage1(data=self.params)
        self.assertTrue(form.is_valid(), msg="get request uri with wfs version 1.0.0 should be valid.")

    def test_invalid_get_capabilitites_url_without_request_param(self):
        self.params.update({
            'get_request_uri': self.get_capabilities_urls.get('invalid_no_request'),
        })
        form = RegisterNewServiceWizardPage1(data=self.params)
        self.assertFalse(form.is_valid(), msg="get request uri was accepted, but was invalid without request param.")

    def test_invalid_get_capabilitites_url_without_version_param(self):
        self.params.update({
            'get_request_uri': self.get_capabilities_urls.get('invalid_no_version'),
        })
        form = RegisterNewServiceWizardPage1(data=self.params)
        self.assertFalse(form.is_valid(), msg="get request uri was accepted, but was invalid without version param.")

    def test_invalid_get_capabilitites_url_without_service_param(self):
        self.params.update({
            'get_request_uri': self.get_capabilities_urls.get('invalid_no_service'),
        })
        form = RegisterNewServiceWizardPage1(data=self.params)
        self.assertFalse(form.is_valid(), msg="get request uri was accepted, but was invalid without service param.")

    def test_invalid_get_capabilitites_url_without_valid_version(self):
        self.params.update({
            'get_request_uri': self.get_capabilities_urls.get('invalid_version'),
        })
        form = RegisterNewServiceWizardPage1(data=self.params)
        self.assertFalse(form.is_valid(), msg="get request uri was accepted, but was invalid with not supported version.")


