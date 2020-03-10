from django.test import TestCase

from structure.forms import RegistrationForm
from users.forms import PasswordChangeForm


class UsersFormsTestCase(TestCase):

    def setUp(self):
        self.params = {}

    def test_password_validation_of_password_change_form(self):
        """ Tests our password policy

          Checks if the password policy is correctly configured on the form field

        """
        # Password must have at least one lowercase letter
        # Password must have at least one Uppercase letter
        # Password must have at least one digit
        # Password must have at least nine characters
        # contains in following mismatching passwords:
        password_without_upper = "mystrongpassword1"
        password_without_lower = "MYSTRONGPASSWORD1"
        password_without_digit = "MyStrongP"
        password_at_most_8 = "MyStron1"

        # case: Error behaviour for password without upper character, user will not be created
        self.params.update({
            'password': password_without_upper,
            'password_again': password_without_upper
        })
        form = PasswordChangeForm(data=self.params)
        self.assertFalse(form.is_valid(), msg="Password without upper character are accepted.")

        # case: Error behaviour for password without lower character, user will not be created
        self.params.update({
            'password': password_without_lower,
            'password_again': password_without_lower
        })
        form = PasswordChangeForm(data=self.params)
        self.assertFalse(form.is_valid(), msg="Password without lower character are accepted.")

        # case: Error behaviour for password without digit character, user will not be created
        self.params.update({
            'password': password_without_digit,
            'password_again': password_without_digit
        })
        form = PasswordChangeForm(data=self.params)
        self.assertFalse(form.is_valid(), msg="Password without digit character are accepted.")

        # case: Error behaviour for password with less as 9 character, user will not be created
        self.params.update({
            'password': password_at_most_8,
            'password_again': password_at_most_8
        })
        form = PasswordChangeForm(data=self.params)
        self.assertFalse(form.is_valid(), msg="Password with less as 9 character are accepted.")
