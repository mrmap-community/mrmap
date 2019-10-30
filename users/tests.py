import os

from django.contrib.auth.hashers import make_password
from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase, Client
from django.utils import timezone

from structure.models import User, UserActivation


class UserTestCase(TestCase):

    def setUp(self):
        """ Create test user for test purpose

        Args:
        Returns:

        """
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
        )
        self.user_id = user.id

    def test_user_register(self):
        """ Tests the register functionality

        Checks if a user can be registered using the route.
        Checks if the user activation object is created automatically afterwards.

        Returns:

        """
        client = Client()

        ## case 0: Normal behaviour, user will be created
        name = "NewUser"
        p_name = "New User"
        pw = "test"
        facsimile = "01234566"
        phone = "02463341"
        email = "test@test.de"
        city = "Testcity"
        address = "Teststreet 2"
        postal_code = "442211"

        params = {
            "username": name,
            "password": pw,
            "password_check": pw,
            "first_name": "New",
            "last_name": "User",
            "facsimile": facsimile,
            "phone": phone,
            "email": email,
            "city": city,
            "address": address,
            "postal_code": postal_code,
            "newsletter": True,
            "survey": True,
            "dsgvo": True,
            "captcha_0": "dummy",
            "captcha_1": "PASSED",
        }
        client.post("/register/", data=params)

        user = User.objects.get(
            username=name,
            email=email
        )
        self.assertEqual(user.username, name, msg="Name is incorrect")
        self.assertEqual(user.person_name, p_name, msg="Person name is incorrect")
        self.assertEqual(user.password, make_password(pw, user.salt), msg="Password is incorrect")
        self.assertEqual(user.facsimile, facsimile, msg="Facsimile is incorrect")
        self.assertEqual(user.phone, phone, msg="Phone is incorrect")
        self.assertEqual(user.email, email, msg="E-mail is incorrect")
        self.assertEqual(user.city, city, msg="City is incorrect")
        self.assertEqual(user.address, address, msg="Address is incorrect")
        self.assertEqual(user.postal_code, postal_code, msg="Postal code is incorrect")
        self.assertEqual(user.confirmed_newsletter, True, msg="Newsletter is incorrect")
        self.assertEqual(user.confirmed_survey, True, msg="Survey is incorrect")

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

        ## case 1: Missing form data -> user will not be created
        params["username"] = ""
        num_users_pre = User.objects.all().count()
        client.post("/register/", data=params)
        num_users_post = User.objects.all().count()
        self.assertEqual(num_users_pre, num_users_post, msg="Malicious should not have been created")


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
        response = client.get("/activate/{}".format(user_activation.activation_hash))
        user.refresh_from_db()
        self.assertEqual(user.is_active, True, msg="User could not be activated")
        obj_found = True
        try:
            user_activation = UserActivation.objects.get(
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
        response = client.post("/", data={"username": user.username, "password": self.pw})
        user.refresh_from_db()
        self.assertEqual(response.url, "/home", msg=REDIRECT_WRONG)
        self.assertEqual(user.logged_in, True, msg="User not logged in")

        ## case 1.1: user logged in -> logout successful
        response = client.get("/logout/", data={"user": user})
        user.refresh_from_db()
        self.assertEqual(response.url, "/", msg=REDIRECT_WRONG)
        self.assertEqual(user.logged_in, False, msg="User already logged in")

        ## case 2: user not activated -> user will not be logged in
        # make sure the user is not activated
        user.is_active = False
        user.save()
        self.assertEqual(user.logged_in, False, msg="User already logged in")
        response = client.post("/", data={"username": user.username, "password": self.pw})
        user.refresh_from_db()
        self.assertEqual(response.url, "/", msg=REDIRECT_WRONG)
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
        new_pw = "12345"

        client = Client()

        ## case 0: User is not logged in -> action has no effect
        # assert action has no effect
        self.assertEqual(user.logged_in, False, msg="User already logged in")
        client.post(
            "/users/password/edit/",
            data={"password": new_pw, "password_again": new_pw, "user": user}
        )
        user.refresh_from_db()
        self.assertNotEqual(user.password, make_password(new_pw, user.salt), msg=PASSWORD_WRONG)

        # login user to pass session checking
        client.post("/", data={"username": user.username, "password": self.pw})
        user.refresh_from_db()

        ## case 1: Input passwords match
        # assert action has effect as expected
        client.post(
            "/users/password/edit/",
            data={"password": new_pw, "password_again": new_pw, "user": user}
        )
        user.refresh_from_db()
        self.assertEqual(user.password, make_password(new_pw, user.salt), msg=PASSWORD_WRONG)

        ## case 2: Input passwords do not match
        # assert action has no effect
        client.post(
            "/users/password/edit/",
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
        new_name = self.username[::-1]
        params = {
            "user": user,
            "username": new_name,
        }

        ## case 0: User not logged in -> no effect!
        # assert as expected
        self.assertEqual(user.logged_in, False, msg="User already logged in")
        client.post(
            "/users/edit/",
            data=params
        )
        user.refresh_from_db()
        self.assertNotEqual(user.username, new_name, msg="Username has been changed")

        # login user
        client.post(
            "/",
            data={"username": user.username, "password": self.pw},
        )
        user.refresh_from_db()
        self.assertEqual(user.logged_in, True, msg="User not logged in")

        ## case 1: User logged in -> effect!
        # assert as expected
        client.post(
            "/users/edit/",
            data=params
        )
        user.refresh_from_db()
        self.assertEqual(user.username, new_name, msg="Username could not be changed")


