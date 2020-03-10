from django.contrib.auth.hashers import make_password
from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase, Client
from django.urls import reverse
from structure.models import User, UserActivation


class RegisterNewUserTestCase(TestCase):

    def setUp(self):
        # create default user object to perform tests with it
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

    def test_success_user_register(self):
        """ Tests the register functionality

        Checks if a user can be registered using the route.
        Checks if the user activation object is created automatically afterwards.

        """
        client = Client()

        # case: Normal behaviour, user will be created
        response = client.post(reverse('register'), data=self.params)

        # we should redirected to the root path /
        self.assertEqual(response.status_code, 302, msg="No redirect after posting user registration form.")

        # test all user attributes are correctly inserted
        user = User.objects.get(
            username=self.username,
            email=self.email
        )
        self.assertEqual(user.username, self.username, msg="Name is incorrect")
        self.assertEqual(user.person_name, self.person_name, msg="Person name is incorrect")
        self.assertEqual(user.password, make_password(self.password, user.salt), msg="Password is incorrect")
        self.assertEqual(user.facsimile, self.facsimile, msg="Facsimile is incorrect")
        self.assertEqual(user.phone, self.phone, msg="Phone is incorrect")
        self.assertEqual(user.email, self.email, msg="E-mail is incorrect")
        self.assertEqual(user.city, self.city, msg="City is incorrect")
        self.assertEqual(user.address, self.address, msg="Address is incorrect")
        self.assertEqual(user.postal_code, self.postal_code, msg="Postal code is incorrect")
        self.assertEqual(user.confirmed_newsletter, self.newsletter, msg="Newsletter is incorrect")
        self.assertEqual(user.confirmed_survey, self.survey, msg="Survey is incorrect")

        # test user activation object
        exists = True
        try:
            user_activation = UserActivation.objects.get(
                user=user
            )
        except ObjectDoesNotExist:
            exists = False
        self.assertEqual(exists, True, msg="No user activation created")
        self.assertNotEqual(user_activation.activation_hash, None, msg="User activation hash does not exist")

    def test_password_policy_user_register(self):
        """ Tests our password policy

          Checks if the password policy is correctly configured on the form fields

        """
        # TODO: refactors this test. We should only check if the error messages are present in our return form.
        """
        example:
        class MyTests(TestCase):
            def test_forms(self):
            response = self.client.post("/my/form/", {'something':'something'})
            self.assertFormError(response, 'form', 'something', 'This field is required.')
            
        we can use empty password to get all error messages
        
        """
        pass
        # Password must have at least one lowercase letter
        # Password must have at least one Uppercase letter
        # Password must have at least one digit
        # Password must have at least nine characters
        # contains in following mismatching passwords:
        password_without_upper = "mystrongpassword1"
        password_without_lower = "MYSTRONGPASSWORD1"
        password_without_digit = "MyStrongP"
        password_at_most_8 = "MyStron1"

        client = Client()

        # case: Error behaviour for password without upper character, user will not be created
        self.params.update({
            'password': password_without_upper,
            'password_check': password_without_upper
        })
        response = client.post(reverse('register'), data=self.params)
        # we should stay on same page with errors
        self.assertEqual(response.status_code, 200,
                         msg="Password without upper character are accepted. "
                             "We should stay on the same page and see the error at password field")

        # case: Error behaviour for password without lower character, user will not be created
        self.params.update({
            'password': password_without_lower,
            'password_check': password_without_lower
        })
        response = client.post(reverse('register'), data=self.params)
        # we should stay on same page with errors
        self.assertEqual(response.status_code, 200,
                         msg="Password without lower character are accepted."
                             "We should stay on the same page and see the error at password field")

        # case: Error behaviour for password without digit character, user will not be created
        self.params.update({
            'password': password_without_digit,
            'password_check': password_without_digit
        })
        response = client.post(reverse('register'), data=self.params)
        # we should stay on same page with errors
        self.assertEqual(response.status_code, 200,
                         msg="Password without digit character are accepted."
                             "We should stay on the same page and see the error at password field")

        # case: Error behaviour for password with less as 9 character, user will not be created
        self.params.update({
            'password': password_at_most_8,
            'password_check': password_at_most_8
        })
        response = client.post(reverse('register'), data=self.params)
        # we should stay on same page with errors
        self.assertEqual(response.status_code, 200,
                         msg="Password with less as 9 character are accepted."
                             "We should stay on the same page and see the error at password field")