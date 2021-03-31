"""
Author: Jonas Kiefer
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: jonas.kiefer@vermkv.rlp.de
Created on: 23.03.2020

"""
from django.test import TestCase
from structure.forms import RegistrationForm
from tests.test_data import get_password_data, get_contact_data


class RegistrationFormTest(TestCase):
    """
        We setup custom regex username validators.
        This testcase will proof if something are bad configured in our RegistrationForm.
        Current requirement for a valid username is:
        < 1 special characters
        < 1 printable
        < 256 characters
        > 4 characters
        Current requirements for a strong password are:
        > 8 characters
        > 1 upper character
        > 1 lower character
        > 1 digit
        < 256 characters
    """

    def setUp(self):
        self.contact_data = get_contact_data()
        self.password_data = get_password_data()

    def test_valid_data(self):
        form = RegistrationForm(data=self.contact_data)

        is_valid = form.is_valid()

        if not is_valid:
            self.logger.error(form.errors.as_data())

        self.assertTrue(is_valid, msg="Valid contact data should be accepted.")

    def test_invalid_password_without_upper(self):
        """ Tests our password policy

          Checks if the password policy is correctly configured on the form field

        """
        # case: Error behaviour for password without upper character, user will not be created
        self.contact_data.update({
            'password': self.password_data.get('invalid_without_upper'),
            'password_check': self.password_data.get('invalid_without_upper'),
        })
        form = RegistrationForm(data=self.contact_data)
        self.assertFalse(form.is_valid(), msg="Password without upper character are accepted.")

    def test_invalid_password_without_lower(self):
        # case: Error behaviour for password without lower character, user will not be created
        self.contact_data.update({
            'password': self.password_data.get('invalid_without_lower'),
            'password_check': self.password_data.get('invalid_without_lower'),
        })
        form = RegistrationForm(data=self.contact_data)
        self.assertFalse(form.is_valid(), msg="Password without lower character are accepted.")

    def test_invalid_password_without_digit(self):
        # case: Error behaviour for password without digit character, user will not be created
        self.contact_data.update({
            'password': self.password_data.get('invalid_without_digit'),
            'password_check': self.password_data.get('invalid_without_digit'),
        })
        form = RegistrationForm(data=self.contact_data)
        self.assertFalse(form.is_valid(), msg="Password without digit character are accepted.")

    def test_invalid_password_at_most_8(self):
        # case: Error behaviour for password with less as 9 character, user will not be created
        self.contact_data.update({
            'password': self.password_data.get('invalid_at_most_8'),
            'password_check': self.password_data.get('invalid_at_most_8'),
        })
        form = RegistrationForm(data=self.contact_data)
        self.assertFalse(form.is_valid(), msg="Password with less as 9 character are accepted.")

    def test_invalid_password_more_than_255(self):
        # case: Error behaviour for password with more than 255 character, user will not be created
        self.contact_data.update({
            'password': self.password_data.get('invalid_more_than_255'),
            'password_again': self.password_data.get('invalid_more_than_255'),
        })
        form = RegistrationForm(data=self.contact_data)
        self.assertFalse(form.is_valid(), msg="Password with more than 255 character are accepted.")

    def test_invalid_username_with_special(self):
        self.contact_data.update({
            'username': self.password_data.get('invalid_has_special'),
        })
        form = RegistrationForm(data=self.contact_data)
        self.assertFalse(form.is_valid(), msg="Username with special character are accepted.")

    def test_invalid_username_with_non_printable(self):
        self.contact_data.update({
            'username': self.password_data.get('invalid_has_non_printable'),
        })
        form = RegistrationForm(data=self.contact_data)
        self.assertFalse(form.is_valid(), msg="Username with non printable character are accepted.")

    def test_invalid_username_with_more_than_255(self):
        self.contact_data.update({
            'username': self.password_data.get('invalid_more_than_255'),
        })
        form = RegistrationForm(data=self.contact_data)
        self.assertFalse(form.is_valid(), msg="Username with more than 255 character are accepted.")

    def test_required_field_username_is_empty(self):
        # username
        self.contact_data.pop('username')
        form = RegistrationForm(data=self.contact_data)
        self.assertFalse(form.is_valid(), msg="Username field was empty but the form is valid.")

    def test_required_field_email_is_empty(self):
        # email
        self.contact_data.pop('email')
        form = RegistrationForm(data=self.contact_data)
        self.assertFalse(form.is_valid(), msg="Email field was empty but the form is valid.")

    def test_required_field_password_is_empty(self):
        # password
        self.contact_data.pop('password')
        form = RegistrationForm(data=self.contact_data)
        self.assertFalse(form.is_valid(), msg="Password field was empty but the form is valid.")

    def test_required_field_password_check_is_empty(self):
        # password_check
        self.contact_data.pop('password_check')
        form = RegistrationForm(data=self.contact_data)
        self.assertFalse(form.is_valid(), msg="Password check field was empty but the form is valid.")

    def test_required_field_dsgvo_is_empty(self):
        # dsgvo
        self.contact_data.pop('dsgvo')
        form = RegistrationForm(data=self.contact_data)
        self.assertFalse(form.is_valid(), msg="DSGVO field was set to false but the form is valid.")

    def test_required_field_captcha_is_empty(self):
        # captcha
        self.contact_data.pop('captcha_0')
        self.contact_data.pop('captcha_1')
        form = RegistrationForm(data=self.contact_data)
        self.assertFalse(form.is_valid(), msg="captcha field was empty but the form is valid.")
