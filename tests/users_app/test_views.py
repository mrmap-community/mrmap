import os
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase, Client
from django.urls import reverse

from MapSkinner.settings import ROOT_URL
from structure.models import User, UserActivation, Theme
from tests.test_data import get_contact_data, get_password_data, get_username_data
from django.utils import timezone


class RegisterNewUserTestCase(TestCase):

    def setUp(self):
        self.contact_data = get_contact_data()

        # creates theme object
        theme = Theme.objects.create(
            name='LIGHT'
        )

        # creates user object in db
        self.username = "Testuser"
        self.pw = "test"
        salt = str(os.urandom(25).hex())
        pw = self.pw
        user = User.objects.create(
            username=self.username,
            salt=salt,
            password=make_password(pw, salt=salt),
            confirmed_dsgvo=timezone.now(),
            is_active=True,
            theme=theme
        )
        self.user_id = user.id

    def test_success_user_register(self):
        """ Tests the register functionality

        Checks if a user can be registered using the route.
        Checks if the user activation object is created automatically afterwards.

        """
        client = Client()

        # case: Normal behaviour, user will be created
        response = client.post(reverse('register'), data=self.contact_data)

        # we should redirected to the root path /
        self.assertEqual(response.status_code, 302, msg="No redirect after posting user registration form.")

        # test all user attributes are correctly inserted
        user = User.objects.get(
            username=self.contact_data.get('username'),
            email=self.contact_data.get('email'),
        )
        self.assertEqual(user.username, self.contact_data.get('username'), msg="Name is'nt incorrect")
        self.assertEqual(user.person_name, self.contact_data.get('person_name'), msg="Person name is'nt incorrect")
        self.assertEqual(user.password, make_password(self.contact_data.get('password'), user.salt), msg="Password is'nt incorrect")
        self.assertEqual(user.facsimile, self.contact_data.get('facsimile'), msg="Facsimile is'nt incorrect")
        self.assertEqual(user.phone, self.contact_data.get('phone'), msg="Phone is'nt incorrect")
        self.assertEqual(user.email, self.contact_data.get('email'), msg="E-mail is'nt incorrect")
        self.assertEqual(user.city, self.contact_data.get('city'), msg="City is'nt incorrect")
        self.assertEqual(user.address, self.contact_data.get('address'), msg="Address is'nt incorrect")
        self.assertEqual(user.postal_code, self.contact_data.get('postal_code'), msg="Postal code is'nt incorrect")
        self.assertEqual(user.confirmed_newsletter, self.contact_data.get('newsletter'), msg="Newsletter is'nt incorrect")
        self.assertEqual(user.confirmed_survey, self.contact_data.get('survey'), msg="Survey is'nt incorrect")

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

    def test_user_activation(self):
        """ Tests the user activation process

        Checks if the UserActivation object was created and is still valid.
        Checks if the user is activated after simulating the activation.
        Checks if the UserActivation object was deleted after successfull activation.

        Returns:
             nothing
        """

        client = Client()
        user = User.objects.get(
            id=self.user_id
        )

        # simulate the situation, when the user is not activated, yet!
        user.is_active = False
        user.create_activation()

        user_activation = UserActivation.objects.get(
            user=user
        )

        # assert activation is still valid
        self.assertLessEqual(timezone.now(), user_activation.activation_until, msg="User activation time window is wrong")

        # activate user
        # assert 200 status code, assert user is active, assert UserActivation object does not exist anymore
        client.get(reverse('activate-user', args=(user_activation.activation_hash,)))
        user.refresh_from_db()
        self.assertEqual(user.is_active, True, msg="User could not be activated")
        obj_found = True
        try:
            UserActivation.objects.get(
                user=user
            )
        except ObjectDoesNotExist:
            obj_found = False
        self.assertEqual(obj_found, False, msg="User activation object could not be removed")

    def test_user_login_logout(self):
        """ Tests the login functionality

        Checks if the user is not able to login while the account is deactivated.
        Checks if the user is able to login when the account is activated.

        Returns:

        """
        REDIRECT_WRONG = "Redirect wrong"
        client = Client()
        user = User.objects.get(
            id=self.user_id
        )

        ## case 1: user activated -> user will be logged in
        self.assertEqual(user.logged_in, False, msg="User already logged in")
        response = client.post(reverse('login',), data={"username": user.username, "password": self.pw})
        user.refresh_from_db()
        self.assertEqual(response.status_code, 302, msg="No redirect was processed.")
        self.assertEqual(response.url, ROOT_URL + reverse('home', ), msg=REDIRECT_WRONG)
        self.assertEqual(user.logged_in, True, msg="User not logged in")

        ## case 1.1: user logged in -> logout successful
        response = client.get(reverse('logout',), data={"user": user})
        user.refresh_from_db()
        self.assertEqual(response.status_code, 302, msg="No redirect was processed.")
        self.assertEqual(response.url, reverse('login',), msg=REDIRECT_WRONG)
        self.assertEqual(user.logged_in, False, msg="User already logged in")

        ## case 2: user not activated -> user will not be logged in
        # make sure the user is not activated
        user.is_active = False
        user.save()
        self.assertEqual(user.logged_in, False, msg="User already logged in")
        response = client.post(reverse('login',), data={"username": user.username, "password": self.pw})
        user.refresh_from_db()
        self.assertEqual(response.status_code, 302, msg="No redirect was processed.")
        self.assertEqual(response.url, reverse('login',), msg=REDIRECT_WRONG)
        self.assertEqual(user.logged_in, False, msg="User not logged in")

    def test_user_password_change(self):
        """ Tests the password change functionality

        Checks if the password can be changed as expected by providing the new password two times.
        Checks if the password change will fail if the provided passwords do not match.

        Args;
        Returns:
        """
        PASSWORD_WRONG = "Password wrong"
        user = User.objects.get(
            id=self.user_id
        )
        self.assertEqual(user.password, make_password(self.pw, user.salt), msg=PASSWORD_WRONG)
        new_pw = get_password_data().get('valid')

        client = Client()

        ## case 0: User is not logged in -> action has no effect
        # assert action has no effect
        self.assertEqual(user.logged_in, False, msg="User already logged in")
        client.post(
            reverse('password-change', ),
            data={"password": new_pw, "password_again": new_pw, "user": user}
        )
        user.refresh_from_db()
        self.assertNotEqual(user.password, make_password(new_pw, user.salt), msg=PASSWORD_WRONG)

        # login user to pass session checking
        client.post(reverse('login', ), data={"username": user.username, "password": self.pw})
        user.refresh_from_db()

        # case 1: Input passwords match
        # assert action has effect as expected
        client.post(
            reverse('password-change', ),
            data={"password": new_pw, "password_again": new_pw, "user": user}
        )
        user.refresh_from_db()
        self.assertEqual(user.password, make_password(new_pw, user.salt), msg=PASSWORD_WRONG)

        # case 2: Input passwords do not match
        # assert action has no effect
        client.post(
            reverse('password-change', ),
            data={"password": new_pw, "password_again": new_pw[::-1], "user": user}
        )
        user.refresh_from_db()
        self.assertEqual(user.password, make_password(new_pw, user.salt), msg=PASSWORD_WRONG)

    def test_user_profile_edit(self):
        """ Tests the profile edit functionality

        Due to multiple possible changes in the profile, this test simply checks whether the user can change it's
        username if the user is logged in.

        Args:
        Returns:

        """
        user = User.objects.get(
            id=self.user_id
        )
        client = Client()
        new_name = get_username_data().get('valid')
        params = {
            "user": user,
            "username": new_name,
        }

        ## case 0: User not logged in -> no effect!
        # assert as expected
        self.assertEqual(user.logged_in, False, msg="User already logged in")
        client.post(
            reverse('password-change', ),
            data=params
        )
        user.refresh_from_db()
        self.assertNotEqual(user.username, new_name, msg="Username has been changed")

        # login user
        client.post(
            reverse('login', ),
            data={"username": user.username, "password": self.pw},
        )
        user.refresh_from_db()
        self.assertEqual(user.logged_in, True, msg="User not logged in")

        ## case 1: User logged in -> effect!
        # assert as expected
        client.post(
            reverse('account-edit', ),
            data=params
        )
        user.refresh_from_db()
        self.assertEqual(user.username, new_name, msg="Username could not be changed")

    def test_error_messages_of_password_field(self):
        """ Tests if the validator fires the right error messages on all cases.
        """

        password_data = get_password_data()

        client = Client()

        # case:
        self.contact_data.update({
            'password': password_data.get('invalid_without_upper'),
            'password_check': password_data.get('invalid_without_upper')
        })
        response = client.post(reverse('register'), data=self.contact_data)
        self.assertEqual(response.status_code, 200, msg="We don't stay on page to see the error messages.")
        self.assertFormError(response, 'form', 'password', 'Password must have at least one Uppercase letter')

        # case:
        self.contact_data.update({
            'password': password_data.get('invalid_without_lower'),
            'password_check': password_data.get('invalid_without_lower')
        })
        response = client.post(reverse('register'), data=self.contact_data)
        self.assertEqual(response.status_code, 200, msg="We don't stay on page to see the error messages.")
        self.assertFormError(response, 'form', 'password', 'Password must have at least one lowercase letter')

        # case:
        self.contact_data.update({
            'password': password_data.get('invalid_without_digit'),
            'password_check': password_data.get('invalid_without_digit')
        })
        response = client.post(reverse('register'), data=self.contact_data)
        self.assertEqual(response.status_code, 200, msg="We don't stay on page to see the error messages.")
        self.assertFormError(response, 'form', 'password', 'Password must have at least one digit')

        # case:
        self.contact_data.update({
            'password': password_data.get('invalid_at_most_8'),
            'password_check': password_data.get('invalid_at_most_8')
        })
        response = client.post(reverse('register'), data=self.contact_data)
        self.assertEqual(response.status_code, 200, msg="We don't stay on page to see the error messages.")
        self.assertFormError(response, 'form', 'password', 'Ensure this value has at least 9 characters (it has 8).')

        # case:
        self.contact_data.update({
            'password': password_data.get('invalid_more_than_255'),
            'password_check': password_data.get('invalid_more_than_255')
        })
        response = client.post(reverse('register'), data=self.contact_data)
        self.assertEqual(response.status_code, 200, msg="We don't stay on page to see the error messages.")
        self.assertFormError(response, 'form', 'password', 'Ensure this value has at most 255 characters (it has 300).')
