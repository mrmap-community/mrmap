"""
Author: Jonas Kiefer
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: jonas.kiefer@vermkv.rlp.de
Created on: 23.03.2020

"""
import logging
from django.test import TestCase, RequestFactory

from tests.baker_recipes.db_setup import create_superadminuser
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
        create_superadminuser()

        self.params.update({
            'email': 'test@example.com'
        })
        form = PasswordResetForm(data=self.params)
        self.assertTrue(form.is_valid(), msg="E-Mail should be accepted.")

    def test_valid_email_but_not_registered(self):
        self.params.update({
            'email': self.email.get('valid')
        })
        form = PasswordResetForm(data=self.params)
        self.assertFalse(form.is_valid(), msg="E-Mail which is not known by the system is accepted.")

    def test_invalid_email_to_long(self):
        self.params.update({
            'email': self.email.get('invalid_to_long')
        })
        form = PasswordResetForm(data=self.params)
        self.assertFalse(form.is_valid(), msg="E-Mail shouldn't be accepted.")

    def test_empty_email(self):
        form = PasswordResetForm(data=self.params)
        self.assertFalse(form.is_valid(), msg="E-Mail was empty but was accepted.")


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
        self.params = {'old_password': 'qwertzuiop'}
        self.password_data = get_password_data()

        user = create_superadminuser()
        request_factory = RequestFactory()
        # Create an instance of a GET request.
        self.request = request_factory.get('/')
        # Recall that middleware are not supported. You can simulate a
        # logged-in user by setting request.user manually.
        self.request.user = user
        self.request.LANGUAGE_CODE = 'en'

    def test_valid_password(self):
        # case: Password with upper, lower, digit and more than 8 characters should be accepted.

        self.params.update({
            'old_password': get_password_data().get('valid'),
            'new_password': self.password_data.get('valid'),
            'new_password_again': self.password_data.get('valid')
        })
        form = PasswordChangeForm(data=self.params, request=self.request)
        self.assertTrue(form.is_valid(), msg="Password should be accepted.")

    def test_invalid_password_without_upper(self):
        # case: Error behaviour for password without upper character, user will not be created
        self.params.update({
            'old_password': get_password_data().get('valid'),
            'new_password': self.password_data.get('invalid_without_upper'),
            'new_password_again': self.password_data.get('invalid_without_upper')
        })
        form = PasswordChangeForm(data=self.params, request=self.request)
        self.assertFalse(form.is_valid(), msg="Password without upper character are accepted.")

    def test_invalid_password_without_lower(self):
        # case: Error behaviour for password without lower character, user will not be created
        self.params.update({
            'old_password': get_password_data().get('valid'),
            'new_password': self.password_data.get('invalid_without_lower'),
            'new_password_again': self.password_data.get('invalid_without_lower')
        })
        form = PasswordChangeForm(data=self.params, request=self.request)
        self.assertFalse(form.is_valid(), msg="Password without lower character are accepted.")

    def test_invalid_password_without_digit(self):
        # case: Error behaviour for password without digit character, user will not be created
        self.params.update({
            'old_password': get_password_data().get('valid'),
            'new_password': self.password_data.get('invalid_without_digit'),
            'new_password_again': self.password_data.get('invalid_without_digit')
        })
        form = PasswordChangeForm(data=self.params, request=self.request)
        self.assertFalse(form.is_valid(), msg="Password without digit character are accepted.")

    def test_invalid_password_with_less_as_9(self):
        # case: Error behaviour for password with less as 9 character, user will not be created
        self.params.update({
            'old_password': get_password_data().get('valid'),
            'new_password': self.password_data.get('invalid_at_most_8'),
            'new_password_again': self.password_data.get('invalid_at_most_8')
        })
        form = PasswordChangeForm(data=self.params, request=self.request)
        self.assertFalse(form.is_valid(), msg="Password with less as 9 character are accepted.")

    def test_invalid_password_with_more_than_255(self):
        # case: Error behaviour for password with more than 255 character, user will not be created
        self.params.update({
            'old_password': get_password_data().get('valid'),
            'new_password': self.password_data.get('invalid_more_than_255'),
            'new_password_again': self.password_data.get('invalid_more_than_255')
        })
        form = PasswordChangeForm(data=self.params, request=self.request)
        self.assertFalse(form.is_valid(), msg="Password with more than 255 character are accepted.")

    def test_valid_password_again(self):
        # case: Error behaviour for password without upper character, user will not be created
        self.params.update({
            'old_password': get_password_data().get('valid'),
            'new_password': self.password_data.get('valid'),
            'new_password_again': self.password_data.get('valid')
        })
        form = PasswordChangeForm(data=self.params, request=self.request)
        self.assertTrue(form.is_valid(), msg="Repeat password and password Field wasn't accepted.")

    def test_invalid_password_again(self):
        # case: Error behaviour for password without upper character, user will not be created
        self.params.update({
            'old_password': get_password_data().get('valid'),
            'new_password': self.password_data.get('valid'),
            'new_password_again': self.password_data.get('valid_2')
        })
        form = PasswordChangeForm(data=self.params, request=self.request)
        self.assertFalse(form.is_valid(), msg="Repeat password and password Field was accepted, but two different passwords where given.")

    def test_empty_password(self):
        self.params.update({
            'new_password_again': self.password_data.get('valid_2')
        })
        form = PasswordChangeForm(data=self.params, request=self.request)
        self.assertFalse(form.is_valid(),
                         msg="Password was empty but form was accepted.")

    def test_empty_password_again(self):
        self.params.update({
            'new_password': self.password_data.get('valid'),
        })
        form = PasswordChangeForm(data=self.params, request=self.request)
        self.assertFalse(form.is_valid(),
                         msg="Password was empty but form was accepted.")


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
        self.user = create_superadminuser()
        self.request_factory = RequestFactory()

        self.account_data = get_account_data()
        self.username_data = get_username_data()
        self.logger = logging.getLogger('UserFormTestCase')
        self.request = self.request_factory.get(
            "/",
        )
        self.request.user = self.user
        self.request.LANGUAGE_CODE = 'en'


    def test_valid_username(self):
        form = UserForm(data=self.account_data,
                        request=self.request,
                        )
        is_valid = form.is_valid()

        if not is_valid:
            self.logger.error(form.errors.as_data())

        self.assertTrue(is_valid, msg="Valid account data should be accepted.")
