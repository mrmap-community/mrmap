"""
Author: Jonas Kiefer
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: jonas.kiefer@vermkv.rlp.de
Created on: 23.03.2020

"""
from django.test import TestCase
from service.forms import RegisterNewServiceWizardPage1, RegisterNewServiceWizardPage2
from tests.baker_recipes.db_setup import create_superadminuser
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


class RegisterNewServiceWizardPage2TestCase(TestCase):
    """
        This testcase will proof the custom constructor of the RegisterNewServiceWizardPage2
    """

    def setUp(self):
        self.user = create_superadminuser()

    def test_construction_if_no_parameter_are_transfered(self):
        try:
            RegisterNewServiceWizardPage2()
        except Exception:
            self.fail(msg="Excaption raised while constructing RegisterNewServiceWizardPage2.")

    def test_construction_if_service_needs_authentication_is_false(self):
        """
            Tests if the service_needs_authentication depending fields are deactivated.

            following fields shouldn't be required:
            service_needs_authentication
            username
            password
            authentication_type

            following fields should be disabled:
            username
            password
            authentication_type

            following fields shouldn't be disabled:
            service_needs_authentication
        """
        form = RegisterNewServiceWizardPage2(service_needs_authentication=False)

        self.assertFalse(form.fields["service_needs_authentication"].required)
        self.assertFalse(form.fields["username"].required)
        self.assertFalse(form.fields["password"].required)
        self.assertFalse(form.fields["authentication_type"].required)

        self.assertTrue(form.fields["username"].disabled)
        self.assertTrue(form.fields["password"].disabled)
        self.assertTrue(form.fields["authentication_type"].disabled)

        self.assertFalse(form.fields["service_needs_authentication"].disabled)

    def test_construction_if_service_needs_authentication_is_true(self):
        """
            Tests if the service_needs_authentication depending fields are activated.

            following fields should be required:
            service_needs_authentication
            username
            password
            authentication_type

            following fields shouldn't be disabled:
            service_needs_authentication
            username
            password
            authentication_type
        """
        form = RegisterNewServiceWizardPage2(service_needs_authentication=True)

        self.assertTrue(form.fields["service_needs_authentication"].required)
        self.assertTrue(form.fields["username"].required)
        self.assertTrue(form.fields["password"].required)
        self.assertTrue(form.fields["authentication_type"].required)

        self.assertFalse(form.fields["service_needs_authentication"].disabled)
        self.assertFalse(form.fields["username"].disabled)
        self.assertFalse(form.fields["password"].disabled)
        self.assertFalse(form.fields["authentication_type"].disabled)

    def test_construction_with_given_user(self):
        """
            Tests if the correct queryset and initial value of the specific registering_with_group field
        """
        # Exclude public groups from the registration form check - registration is not allowed for public groups
        user_groups = self.user.get_groups({"is_public_group": False})
        form = RegisterNewServiceWizardPage2(user=self.user)
        self.assertEqual(list(form.fields["registering_with_group"].queryset), list(user_groups))
        self.assertQuerysetEqual(form.fields["registering_for_other_organization"].queryset, user_groups.first().publish_for_organizations.all())
        self.assertEqual(form.fields["registering_with_group"].initial, user_groups.first())

    def test_construction_with_given_selected_group(self):
        """
            Tests if the correct queryset of the specific registering_for_other_organization field
        """
        user_groups = self.user.get_groups()
        form = RegisterNewServiceWizardPage2(selected_group=user_groups.first())
        self.assertQuerysetEqual(form.fields["registering_for_other_organization"].queryset, user_groups.first().publish_for_organizations.all())

