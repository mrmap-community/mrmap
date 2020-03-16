import logging
from django.test import TestCase
from tests.test_data import get_password_data, get_username_data, get_account_data, get_email_data
from users.forms import PasswordChangeForm, UserForm, PasswordResetForm


class PasswordResetFormTestCase(TestCase):
    """
        This testcase will proof if something are bad configured in our PasswordResetForm.
        Current requirements are:
        < 256 characters
    """
    def setUp(self):
        self.params = {}
        self.email = get_email_data()

    def test_valid_email(self):
        self.params.update({
            'email': self.email.get('valid')
        })
        form = PasswordResetForm(data=self.params)
        self.assertTrue(form.is_valid(), msg="E-Mail should be accepted.")

    def test_invalid_email_to_long(self):
        self.params.update({
            'email': self.email.get('invalid_to_long')
        })
        form = PasswordResetForm(data=self.params)
        self.assertFalse(form.is_valid(), msg="E-Mail shouldn't be accepted.")


class PasswordChangeFormTestCase(TestCase):
    """
        We setup custom regex password validators.
        This testcase will proof if something are bad configured in our PasswordChangeForm.
        Current requirements for a strong password are:
        > 8 characters
        > 1 upper character
        > 1 lower character
        > 1 digit
        < 256 characters
    """

    def setUp(self):
        self.params = {}
        self.password_data = get_password_data()

    def test_valid_password(self):
        # case: Password wirth upper, lower, digit and more than 8 characters should be accepted.
        self.params.update({
            'password': self.password_data.get('valid'),
            'password_again': self.password_data.get('valid')
        })
        form = PasswordChangeForm(data=self.params)
        self.assertTrue(form.is_valid(), msg="Password should be accepted.")

    def test_invalid_password_without_upper(self):
        # case: Error behaviour for password without upper character, user will not be created
        self.params.update({
            'password': self.password_data.get('invalid_without_upper'),
            'password_again': self.password_data.get('invalid_without_upper')
        })
        form = PasswordChangeForm(data=self.params)
        self.assertFalse(form.is_valid(), msg="Password without upper character are accepted.")

    def test_invalid_password_without_lower(self):
        # case: Error behaviour for password without lower character, user will not be created
        self.params.update({
            'password': self.password_data.get('invalid_without_lower'),
            'password_again': self.password_data.get('invalid_without_lower')
        })
        form = PasswordChangeForm(data=self.params)
        self.assertFalse(form.is_valid(), msg="Password without lower character are accepted.")

    def test_invalid_password_without_digit(self):
        # case: Error behaviour for password without digit character, user will not be created
        self.params.update({
            'password': self.password_data.get('invalid_without_digit'),
            'password_again': self.password_data.get('invalid_without_digit')
        })
        form = PasswordChangeForm(data=self.params)
        self.assertFalse(form.is_valid(), msg="Password without digit character are accepted.")

    def test_invalid_password_with_less_as_9(self):
        # case: Error behaviour for password with less as 9 character, user will not be created
        self.params.update({
            'password': self.password_data.get('invalid_at_most_8'),
            'password_again': self.password_data.get('invalid_at_most_8')
        })
        form = PasswordChangeForm(data=self.params)
        self.assertFalse(form.is_valid(), msg="Password with less as 9 character are accepted.")

    def test_invalid_password_with_more_than_255(self):
        # case: Error behaviour for password with more than 255 character, user will not be created
        self.params.update({
            'password': self.password_data.get('invalid_more_than_255'),
            'password_again': self.password_data.get('invalid_more_than_255')
        })
        form = PasswordChangeForm(data=self.params)
        self.assertFalse(form.is_valid(), msg="Password with more than 255 character are accepted.")

    def test_valid_password_again(self):
        # case: Error behaviour for password without upper character, user will not be created
        self.params.update({
            'password': self.password_data.get('valid'),
            'password_again': self.password_data.get('valid')
        })
        form = PasswordChangeForm(data=self.params)
        self.assertTrue(form.is_valid(), msg="Repeat password and password Field wasn't accepted.")

    def test_invalid_password_again(self):
        # case: Error behaviour for password without upper character, user will not be created
        self.params.update({
            'password': self.password_data.get('valid'),
            'password_again': self.password_data.get('valid_2')
        })
        form = PasswordChangeForm(data=self.params)
        self.assertFalse(form.is_valid(), msg="Repeat password and password Field was accepted, but two different passwords where given.")


class UserFormTestCase(TestCase):
    """
        We setup custom regex username validators.
        This testcase will proof if something are bad configured in our UserForm.
        Current requirement for a valid username is:
        < 1 special characters
        < 1 printable
        < 256 characters
        > 4 characters
    """

    def setUp(self):
        self.account_data = get_account_data()
        self.username_data = get_username_data()
        self.logger = logging.getLogger('UserFormTestCase')

    def test_valid_username(self):
        form = UserForm(data=self.account_data)
        is_valid = form.is_valid()

        if not is_valid:
            self.logger.error(form.errors.as_data())

        self.assertTrue(is_valid, msg="Valid account data should be accepted.")

    def test_invalid_username_with_special(self):
        self.account_data.update({
            'username': self.username_data.get('invalid_has_special'),
        })
        form = UserForm(data=self.account_data)
        self.assertFalse(form.is_valid(), msg="Username with special character are accepted.")

    def test_invalid_username_with_printable(self):
        self.account_data.update({
            'username': self.username_data.get('invalid_has_non_printable'),
        })
        form = UserForm(data=self.account_data)
        self.assertFalse(form.is_valid(), msg="Username with non printable character are accepted.")

