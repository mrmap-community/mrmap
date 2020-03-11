from django.test import TestCase
import logging
from tests.test_data import get_password_data, get_username_data, get_account_data
from users.forms import PasswordChangeForm, UserForm


class PasswordChangeFormTestCase(TestCase):
    """
        We setup custom regex password validators.
        This testcase will proof if something are bad configured in our PasswordChangeForm.
        Current requirement for a strong password is:
        > 8 characters
        > 1 upper character
        > 1 lower character
        > 1 digit
        < 256 characters
    """

    def setUp(self):
        self.params = {}

    def test_valid_password(self):
        password_data = get_password_data()

        # case: Password wirth upper, lower, digit and more than 8 characters should be accepted.
        self.params.update({
            'password': password_data.get('valid'),
            'password_again': password_data.get('valid')
        })
        form = PasswordChangeForm(data=self.params)
        self.assertTrue(form.is_valid(), msg="Password should be accepted.")

    def test_invalid_password(self):
        """ Tests our password policy

          Checks if the password policy is correctly configured on the password change form field

        """
        password_data = get_password_data()

        # case: Error behaviour for password without upper character, user will not be created
        self.params.update({
            'password': password_data.get('invalid_without_upper'),
            'password_again': password_data.get('invalid_without_upper')
        })
        form = PasswordChangeForm(data=self.params)
        self.assertFalse(form.is_valid(), msg="Password without upper character are accepted.")

        # case: Error behaviour for password without lower character, user will not be created
        self.params.update({
            'password': password_data.get('invalid_without_lower'),
            'password_again': password_data.get('invalid_without_lower')
        })
        form = PasswordChangeForm(data=self.params)
        self.assertFalse(form.is_valid(), msg="Password without lower character are accepted.")

        # case: Error behaviour for password without digit character, user will not be created
        self.params.update({
            'password': password_data.get('invalid_without_digit'),
            'password_again': password_data.get('invalid_without_digit')
        })
        form = PasswordChangeForm(data=self.params)
        self.assertFalse(form.is_valid(), msg="Password without digit character are accepted.")

        # case: Error behaviour for password with less as 9 character, user will not be created
        self.params.update({
            'password': password_data.get('invalid_at_most_8'),
            'password_again': password_data.get('invalid_at_most_8')
        })
        form = PasswordChangeForm(data=self.params)
        self.assertFalse(form.is_valid(), msg="Password with less as 9 character are accepted.")

        # case: Error behaviour for password with more than 255 character, user will not be created
        self.params.update({
            'password': password_data.get('invalid_more_than_255'),
            'password_again': password_data.get('invalid_more_than_255')
        })
        form = PasswordChangeForm(data=self.params)
        self.assertFalse(form.is_valid(), msg="Password with more than 255 character are accepted.")


class UserFormTestCase(TestCase):
    """
        TODO: document the test case
    """

    def setUp(self):
        self.account_data = get_account_data()
        self.logger = logging.getLogger('UserFormTestCase')

    def test_valid_username(self):
        form = UserForm(data=self.account_data)
        is_valid = form.is_valid()

        if not is_valid:
            self.logger.error(form.errors.as_data())

        self.assertTrue(is_valid, msg="Valid account data should be accepted.")

    def test_invalid_username(self):
        username_data = get_username_data()

        self.account_data.update({
            'username': username_data.get('invalid_has_special'),
        })
        form = UserForm(data=self.account_data)
        self.assertFalse(form.is_valid(), msg="Username with special character are accepted.")

        self.account_data.update({
            'username': username_data.get('invalid_has_non_printable'),
        })
        form = UserForm(data=self.account_data)
        self.assertFalse(form.is_valid(), msg="Username with non printable character are accepted.")

        self.account_data.update({
            'username': username_data.get('invalid_more_than_255'),
        })
        form = UserForm(data=self.account_data)
        self.assertFalse(form.is_valid(), msg="Username with more than 255 character are accepted.")
