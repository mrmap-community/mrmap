import json
import os

from django.contrib.auth.hashers import make_password
from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase, Client
from django.utils import timezone

from structure.forms import LoginForm
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
        self.assertLessEqual(timezone.now(), user_activation.activation_until)

        # activate user
        # assert 200 status code, assert user is active, assert UserActivation object does not exist anymore
        response = client.get("/activate/{}".format(user_activation.activation_hash))
        user.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(user.is_active, True)
        obj_found = True
        try:
            user_activation = UserActivation.objects.get(
                user=user
            )
        except ObjectDoesNotExist:
            obj_found = False
        self.assertEqual(obj_found, False)

    def test_user_login_logout(self):
        """ Tests the login functionality

        Checks if the user is not able to login while the account is deactivated.
        Checks if the user is able to login when the account is activated.

        Returns:

        """
        client = Client()
        user = User.objects.get(
            id=self.user_id
        )

        ## case 1: user activated -> user will be logged in
        self.assertEqual(user.logged_in, False)
        response = client.post("/", data={"username": user.username, "password": self.pw})
        user.refresh_from_db()
        self.assertEqual(response.url, "/home")
        self.assertEqual(user.logged_in, True)

        ## case 1.1: user logged in -> logout successful
        response = client.get("/logout/", data={"user": user})
        user.refresh_from_db()
        self.assertEqual(response.url, "/")
        self.assertEqual(user.logged_in, False)

        ## case 2: user not activated -> user will not be logged in
        # make sure the user is not activated
        user.is_active = False
        user.save()
        self.assertEqual(user.logged_in, False)
        response = client.post("/", data={"username": user.username, "password": self.pw})
        user.refresh_from_db()
        self.assertEqual(response.url, "/")
        self.assertEqual(user.logged_in, False)


