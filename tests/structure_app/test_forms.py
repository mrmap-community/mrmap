from django.test import TestCase

from structure.forms import RegistrationForm


class StructureFormsTestCase(TestCase):

    def setUp(self):
        # default user data to perform tests with it. Values are all valid
        self.username = "NewUser"
        self.password = "MyStrongPassword1!"
        self.person_name = "New User"
        self.firstname = "New"
        self.lastname = "User"
        self.email = "newuser@example.com"
        self.address = "Teststreet 2"
        self.postal_code = "442211"
        self.city = "Testcity"
        self.phone = "02463341"
        self.facsimile = "01234566"
        self.newsletter = True
        self.survey = True
        self.dsgvo = True

        self.params = {
            "username": self.username,
            "password": self.password,
            "password_check": self.password,
            "first_name": self.firstname,
            "last_name": self.lastname,
            "facsimile": self.facsimile,
            "phone": self.phone,
            "email": self.email,
            "city": self.city,
            "address": self.address,
            "postal_code": self.postal_code,
            "newsletter": self.newsletter,
            "survey": self.survey,
            "dsgvo": self.dsgvo,
            "captcha_0": "dummy",
            "captcha_1": "PASSED",
        }

    def test_password_validation_of_registration_form(self):
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
            'password_check': password_without_upper
        })
        form = RegistrationForm(data=self.params)
        self.assertFalse(form.is_valid(), msg="Password without upper character are accepted.")

        # case: Error behaviour for password without lower character, user will not be created
        self.params.update({
            'password': password_without_lower,
            'password_check': password_without_lower
        })
        form = RegistrationForm(data=self.params)
        self.assertFalse(form.is_valid(), msg="Password without lower character are accepted.")

        # case: Error behaviour for password without digit character, user will not be created
        self.params.update({
            'password': password_without_digit,
            'password_check': password_without_digit
        })
        form = RegistrationForm(data=self.params)
        self.assertFalse(form.is_valid(), msg="Password without digit character are accepted.")

        # case: Error behaviour for password with less as 9 character, user will not be created
        self.params.update({
            'password': password_at_most_8,
            'password_check': password_at_most_8
        })
        form = RegistrationForm(data=self.params)
        self.assertFalse(form.is_valid(), msg="Password with less as 9 character are accepted.")
