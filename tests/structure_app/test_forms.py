from django.test import TestCase

from structure.forms import RegistrationForm
from tests.test_data import get_password_data, get_contact_data, get_username_data


class RegistrationFormTestCase(TestCase):
    """
        TODO: document the test case
    """

    def setUp(self):
        self.contact_data = get_contact_data()

    def test_valid_data(self):
        form = RegistrationForm(data=self.contact_data)

        is_valid = form.is_valid()

        if not is_valid:
            self.logger.error(form.errors.as_data())

        self.assertTrue(is_valid, msg="Valid contact data should be accepted.")

    def test_invalid_password(self):
        """ Tests our password policy

          Checks if the password policy is correctly configured on the form field

        """
        password_data = get_password_data()

        # case: Error behaviour for password without upper character, user will not be created
        self.contact_data.update({
            'password': password_data.get('invalid_without_upper'),
            'password_check': password_data.get('invalid_without_upper'),
        })
        form = RegistrationForm(data=self.contact_data)
        self.assertFalse(form.is_valid(), msg="Password without upper character are accepted.")

        # case: Error behaviour for password without lower character, user will not be created
        self.contact_data.update({
            'password': password_data.get('invalid_without_lower'),
            'password_check': password_data.get('invalid_without_lower'),
        })
        form = RegistrationForm(data=self.contact_data)
        self.assertFalse(form.is_valid(), msg="Password without lower character are accepted.")

        # case: Error behaviour for password without digit character, user will not be created
        self.contact_data.update({
            'password': password_data.get('invalid_without_digit'),
            'password_check': password_data.get('invalid_without_digit'),
        })
        form = RegistrationForm(data=self.contact_data)
        self.assertFalse(form.is_valid(), msg="Password without digit character are accepted.")

        # case: Error behaviour for password with less as 9 character, user will not be created
        self.contact_data.update({
            'password': password_data.get('invalid_at_most_8'),
            'password_check': password_data.get('invalid_at_most_8'),
        })
        form = RegistrationForm(data=self.contact_data)
        self.assertFalse(form.is_valid(), msg="Password with less as 9 character are accepted.")

        # case: Error behaviour for password with more than 255 character, user will not be created
        self.contact_data.update({
            'password': password_data.get('invalid_more_than_255'),
            'password_again': password_data.get('invalid_more_than_255'),
        })
        form = RegistrationForm(data=self.contact_data)
        self.assertFalse(form.is_valid(), msg="Password with more than 255 character are accepted.")

    def test_invalid_username(self):
        username_data = get_username_data()

        self.contact_data.update({
            'username': username_data.get('invalid_has_special'),
        })
        form = RegistrationForm(data=self.contact_data)
        self.assertFalse(form.is_valid(), msg="Username with special character are accepted.")

        self.contact_data.update({
            'username': username_data.get('invalid_has_non_printable'),
        })
        form = RegistrationForm(data=self.contact_data)
        self.assertFalse(form.is_valid(), msg="Username with non printable character are accepted.")

        self.contact_data.update({
            'username': username_data.get('invalid_more_than_255'),
        })
        form = RegistrationForm(data=self.contact_data)
        self.assertFalse(form.is_valid(), msg="Username with more than 255 character are accepted.")

    def test_required_fields_are_not_empty(self):
        # username
        self.contact_data.pop('username')
        form = RegistrationForm(data=self.contact_data)
        self.assertFalse(form.is_valid(), msg="Username field was empty but the form is valid.")

        # email
        self.contact_data.pop('email')
        form = RegistrationForm(data=self.contact_data)
        self.assertFalse(form.is_valid(), msg="Email field was empty but the form is valid.")

        # first_name
        self.contact_data.pop('first_name')
        form = RegistrationForm(data=self.contact_data)
        self.assertFalse(form.is_valid(), msg="First name field was empty but the form is valid.")

        # last_name
        self.contact_data.pop('last_name')
        form = RegistrationForm(data=self.contact_data)
        self.assertFalse(form.is_valid(), msg="Last name field was empty but the form is valid.")

        # password
        self.contact_data.pop('password')
        form = RegistrationForm(data=self.contact_data)
        self.assertFalse(form.is_valid(), msg="Password field was empty but the form is valid.")

        # password_check
        self.contact_data.pop('password_check')
        form = RegistrationForm(data=self.contact_data)
        self.assertFalse(form.is_valid(), msg="Password check field was empty but the form is valid.")

        # dsgvo
        self.contact_data.pop('dsgvo')
        form = RegistrationForm(data=self.contact_data)
        self.assertFalse(form.is_valid(), msg="DSGVO field was set to false but the form is valid.")

        # captcha
        self.contact_data.pop('captcha_0')
        self.contact_data.pop('captcha_1')
        form = RegistrationForm(data=self.contact_data)
        self.assertFalse(form.is_valid(), msg="captcha field was empty but the form is valid.")

    def test_max_lengths(self):
        # TODO
        pass
