import logging
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase, Client
from django.urls import reverse

from MapSkinner.messages import PASSWORD_SENT, EMAIL_IS_UNKNOWN
from MapSkinner.settings import ROOT_URL
from structure.models import User, UserActivation
from tests.baker_recipes import create_active_user
from tests.helper import _login
from tests.test_data import get_contact_data, get_password_data, get_username_data, get_email_data
from django.utils import timezone
from django.contrib.messages import get_messages

REDIRECT_WRONG = "Redirect wrong"


class PasswordResetTestCase(TestCase):
    def setUp(self):
        self.user_password = 'testpassword'
        self.active_user = create_active_user('testuser', self.user_password, 'test@example.com')
        self.logger = logging.getLogger('PasswordResetTestCase')

    def test_success_password_reset(self):
        client = _login(self.active_user.username, self.user_password, Client())
        response = client.post(reverse('password-reset', ), data={"email": 'test@example.com'})
        self.logger.debug(response.__dict__)

        self.assertEqual(response.status_code, 302, msg="No Http-302 was returned.")
        self.assertEqual(response.url, reverse('login', ), msg=REDIRECT_WRONG)

        messages = list(get_messages(response.wsgi_request))
        self.logger.debug(messages)
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), PASSWORD_SENT)

    def test_failed_password_reset(self):
        client = _login(self.active_user.username, self.user_password, Client())
        response = client.post(reverse('password-reset', ), data={"email": 'test1@example.com'})
        self.assertEqual(response.status_code, 200, msg="We don't stay on page to see the error messages.")
        self.assertFormError(response, 'form', 'email', EMAIL_IS_UNKNOWN)

    def test_get_password_reset_view(self):
        client = _login(self.active_user.username, self.user_password, Client())
        response = client.get(reverse('password-reset', ))
        self.assertEqual(response.status_code, 200, msg="We should get the view.")


class RegisterNewUserTestCase(TestCase):
    def setUp(self):
        self.logger = logging.getLogger('RegisterNewUserTestCase')
        self.contact_data = get_contact_data()
        # creates user object in db
        self.user_password = get_password_data().get('valid')
        self.user = create_active_user("Testuser", self.user_password, "test@example.com")

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
        self.assertEqual(user.username, self.contact_data.get('username'), msg="Name is incorrect")
        self.assertEqual(user.person_name, self.contact_data.get('person_name'), msg="Person name is incorrect")
        self.assertEqual(user.password, make_password(self.contact_data.get('password'), user.salt), msg="Password is incorrect")
        self.assertEqual(user.facsimile, self.contact_data.get('facsimile'), msg="Facsimile is incorrect")
        self.assertEqual(user.phone, self.contact_data.get('phone'), msg="Phone is incorrect")
        self.assertEqual(user.email, self.contact_data.get('email'), msg="E-mail is incorrect")
        self.assertEqual(user.city, self.contact_data.get('city'), msg="City is incorrect")
        self.assertEqual(user.address, self.contact_data.get('address'), msg="Address is incorrect")
        self.assertEqual(user.postal_code, self.contact_data.get('postal_code'), msg="Postal code is incorrect")
        self.assertEqual(user.confirmed_newsletter, self.contact_data.get('newsletter'), msg="Newsletter is incorrect")
        self.assertEqual(user.confirmed_survey, self.contact_data.get('survey'), msg="Survey is incorrect")

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

    def test_failed_user_register(self):
        client = Client()
        # case: Error behaviour, user will not be created
        self.contact_data.update({'username': '!qwertzui123'})
        response = client.post(reverse('register'), data=self.contact_data)

        self.assertEqual(response.status_code, 200, msg="We doesn't get the rendered view.")
        self.assertFormError(response, 'form', 'username', 'Special or non printable characters are not allowed')
        user = None
        try:
            user = User.objects.get(
                username=self.contact_data.get('!qwertzui123'),
            )
        except ObjectDoesNotExist as e:
            pass

        self.assertIsNone(user, msg="User is created.")

    def test_get_user_register_view(self):
        client = Client()
        # case: Error behaviour, user will not be created
        response = client.get(reverse('register'))

        self.assertEqual(response.status_code, 200, msg="We doesn't get the rendered view.")
        self.assertTemplateUsed(response, template_name='views/register.html')


class ActivateUserTestCase(TestCase):
    def setUp(self):
        self.logger = logging.getLogger('ActivateUserTestCase')
        # creates user object in db
        self.user_password = get_password_data().get('valid')
        self.user = create_active_user("Testuser", self.user_password, "test@example.com")

    def test_user_activation(self):
        """ Tests the user activation process

        Checks if the UserActivation object was created and is still valid.
        Checks if the user is activated after simulating the activation.
        Checks if the UserActivation object was deleted after successfull activation.

        Returns:
             nothing
        """

        client = Client()

        # simulate the situation, when the user is not activated, yet!
        self.user.is_active = False
        self.user.create_activation()

        user_activation = UserActivation.objects.get(
            user=self.user
        )

        # assert activation is still valid
        self.assertLessEqual(timezone.now(), user_activation.activation_until, msg="User activation time window is wrong")

        # activate user
        # assert 200 status code, assert user is active, assert UserActivation object does not exist anymore
        client.get(reverse('activate-user', args=(user_activation.activation_hash,)))
        self.user.refresh_from_db()
        self.assertEqual(self.user.is_active, True, msg="User could not be activated")
        obj_found = True
        try:
            UserActivation.objects.get(
                user=self.user
            )
        except ObjectDoesNotExist:
            obj_found = False
        self.assertEqual(obj_found, False, msg="User activation object could not be removed")


class LoginLogoutTestCase(TestCase):
    def setUp(self):
        self.logger = logging.getLogger('LoginLogoutTestCase')
        # creates user object in db
        self.user_password = get_password_data().get('valid')
        self.user = create_active_user("Testuser", self.user_password, "test@example.com")

    def test_user_login_logout(self):
        """ Tests the login functionality

        Checks if the user is not able to login while the account is deactivated.
        Checks if the user is able to login when the account is activated.

        Returns:

        """
        client = Client()

        # case 1: user activated -> user will be logged in
        self.assertEqual(self.user.logged_in, False, msg="User already logged in")
        response = client.post(reverse('login',), data={"username": self.user.username, "password": self.user_password})
        self.user.refresh_from_db()
        self.assertEqual(response.status_code, 302, msg="No redirect was processed.")
        self.assertEqual(response.url, ROOT_URL + reverse('home', ), msg=REDIRECT_WRONG)
        self.assertEqual(self.user.logged_in, True, msg="User not logged in")

        # case 1.1: user logged in -> logout successful
        response = client.get(reverse('logout',), data={"user": self.user})
        self.user.refresh_from_db()
        self.assertEqual(response.status_code, 302, msg="No redirect was processed.")
        self.assertEqual(response.url, reverse('login',), msg=REDIRECT_WRONG)
        self.assertEqual(self.user.logged_in, False, msg="User already logged in")

        # case 2: user not activated -> user will not be logged in
        # make sure the user is not activated
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.user.logged_in, False, msg="User already logged in")
        response = client.post(reverse('login',), data={"username": self.user.username, "password": self.user_password})
        self.user.refresh_from_db()
        self.assertEqual(response.status_code, 302, msg="No redirect was processed.")
        self.assertEqual(response.url, reverse('login',), msg=REDIRECT_WRONG)
        self.assertEqual(self.user.logged_in, False, msg="User not logged in")


class PasswordChangeTestCase(TestCase):
    def setUp(self):
        self.logger = logging.getLogger('PasswordChangeTestCase')
        # creates user object in db
        self.user_password = get_password_data().get('valid')
        self.user = create_active_user("Testuser", self.user_password, "test@example.com")

    def test_user_password_change_with_logged_out_user(self):
        """ Tests the password change functionality

        Checks if the password can be changed as expected by providing the new password two times.
        Checks if the password change will fail if the provided passwords do not match.

        Args;
        Returns:
        """
        PASSWORD_WRONG = "Password wrong"
        self.assertEqual(self.user.password, make_password(self.user_password, self.user.salt), msg=PASSWORD_WRONG)
        new_pw = 'qwertzuiop!123M'

        ## case 0: User is not logged in -> action has no effect
        # assert action has no effect
        self.assertEqual(self.user.logged_in, False, msg="User already logged in")
        Client().post(
            reverse('password-change', ),
            data={"password": new_pw, "password_again": new_pw, "user": self.user}
        )
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.password, make_password(new_pw, self.user.salt), msg=PASSWORD_WRONG)

    def test_user_password_change_with_logged_in_user(self):
        PASSWORD_WRONG = "Password wrong"
        new_pw = get_password_data().get('valid')

        client = _login(self.user.username, self.user_password, Client())

        # case 1: Input passwords match
        # assert action has effect as expected
        client.post(
            reverse('password-change', ),
            data={"password": new_pw, "password_again": new_pw, "user": self.user}
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.password, make_password(new_pw, self.user.salt), msg=PASSWORD_WRONG)

        # case 2: Input passwords do not match
        # assert action has no effect
        client.post(
            reverse('password-change', ),
            data={"password": new_pw, "password_again": new_pw[::-1], "user": self.user}
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.password, make_password(new_pw, self.user.salt), msg=PASSWORD_WRONG)


class AccountEditTestCase(TestCase):
    def setUp(self):
        self.logger = logging.getLogger('AccountEditTestCase')
        # creates user object in db
        self.user_password = get_password_data().get('valid')
        self.user = create_active_user("Testuser", self.user_password, "test@example.com")
        self.contact_data = get_contact_data()

    def test_get_account_edit_view(self):
        client = _login(self.user.username, self.user_password, Client())

        # case 1: User logged in -> effect!
        # assert as expected
        response = client.get(
            reverse('account-edit', ),
        )
        self.logger.debug(response.__dict__)
        self.assertEqual(response.status_code, 200, msg="We dosn't get the account edit view")
        self.assertTemplateUsed("views/account.html")

        #self.assertEqual(response.url, ROOT_URL + reverse('account-edit'))

    def test_user_profile_edit_with_logged_out_user(self):
        """ Tests the profile edit functionality

        Due to multiple possible changes in the profile, this test simply checks whether the user can change it's
        username if the user is logged in.

        Args:
        Returns:

        """

        new_name = get_username_data().get('valid')
        params = {
            "user": self.user,
            "username": new_name,
        }

        # case 0: User not logged in -> no effect!
        # assert as expected
        self.assertEqual(self.user.logged_in, False, msg="User already logged in")
        Client().post(
            reverse('password-change', ),
            data=params
        )
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.username, new_name, msg="Username has been changed")

    def test_user_profile_edit_with_logged_in_user(self):
        client = _login(self.user.username, self.user_password, Client())

        new_name = get_username_data().get('valid')
        params = {
            "user": self.user,
            "username": new_name,
            "email": get_email_data().get('valid'),
            "theme": "LIGHT",
        }

        # case 1: User logged in -> effect!
        # assert as expected
        response = client.post(
            reverse('account-edit', ),
            data=params
        )
        self.logger.debug(response.__dict__)

        self.user.refresh_from_db()
        self.assertEqual(self.user.username, new_name, msg="Username could not be changed")

    def test_error_messages_of_password_without_upper(self):
        """
            Tests if the validator fires the right error messages on all cases.
        """

        # case:
        self.contact_data.update({
            'password': get_password_data().get('invalid_without_upper'),
            'password_check': get_password_data().get('invalid_without_upper')
        })
        response = Client().post(reverse('register'), data=self.contact_data)
        self.assertEqual(response.status_code, 200, msg="We don't stay on page to see the error messages.")
        self.assertFormError(response, 'form', 'password', 'Password must have at least one Uppercase letter')

    def test_error_messages_of_password_without_lower(self):

        # case:
        self.contact_data.update({
            'password': get_password_data().get('invalid_without_lower'),
            'password_check': get_password_data().get('invalid_without_lower')
        })
        response = Client().post(reverse('register'), data=self.contact_data)
        self.assertEqual(response.status_code, 200, msg="We don't stay on page to see the error messages.")
        self.assertFormError(response, 'form', 'password', 'Password must have at least one lowercase letter')

    def test_error_messages_of_password_without_digit(self):

        # case:
        self.contact_data.update({
            'password': get_password_data().get('invalid_without_digit'),
            'password_check': get_password_data().get('invalid_without_digit')
        })
        response = Client().post(reverse('register'), data=self.contact_data)
        self.assertEqual(response.status_code, 200, msg="We don't stay on page to see the error messages.")
        self.assertFormError(response, 'form', 'password', 'Password must have at least one digit')

    def test_error_messages_of_password_at_most_8(self):
        # case:
        self.contact_data.update({
            'password': get_password_data().get('invalid_at_most_8'),
            'password_check': get_password_data().get('invalid_at_most_8')
        })
        response = Client().post(reverse('register'), data=self.contact_data)
        self.assertEqual(response.status_code, 200, msg="We don't stay on page to see the error messages.")
        self.assertFormError(response, 'form', 'password', 'Ensure this value has at least 9 characters (it has 8).')

    def test_error_messages_of_password_more_than_255(self):
        # case:
        self.contact_data.update({
            'password': get_password_data().get('invalid_more_than_255'),
            'password_check': get_password_data().get('invalid_more_than_255')
        })
        response = Client().post(reverse('register'), data=self.contact_data)
        self.assertEqual(response.status_code, 200, msg="We don't stay on page to see the error messages.")
        self.assertFormError(response, 'form', 'password', 'Ensure this value has at most 255 characters (it has 300).')


class HomeViewTestCase(TestCase):

    def setUp(self):
        self.logger = logging.getLogger('HomeViewTestCase')
        # creates user object in db
        self.user_password = get_password_data().get('valid')
        self.user = create_active_user("Testuser", self.user_password, "test@example.com")

    def test_home_view(self):
        client = _login(self.user.username, self.user_password, Client())

        response = client.get(
            reverse('home', ),
        )
        self.logger.debug(response.__dict__)
        self.assertEqual(response.status_code, 200,)
        self.assertTemplateUsed(response=response, template_name="views/dashboard.html")
