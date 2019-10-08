import os
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase, Client
from django.utils import timezone

from structure.models import Group, User, Role, Permission


class StructureTestCase(TestCase):

    def setUp(self):
        # create user who performs the actions in these tests
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

        # create default role with super rights
        role = Role()
        role.name = "_default_"
        permission = Permission()
        for key, val in permission.__dict__.items():
            if not isinstance(val, bool) and 'can_' not in key:
                continue
            setattr(permission, key, True)
        permission.save()
        role.permission = permission
        role.save()
        self.role_id = role.id

        # create default group for super rights and user
        group = Group.objects.create(
            role=role,
            name="Testgroup",
            created_by=user
        )
        user.groups.add(group)

    def _get_logged_in_client(self):
        """ Helping function to encapsulate the login process

        Returns:
             client (Client): The client object, which holds an active session for the user
        """
        client = Client()
        user = User.objects.get(
            id=self.user_id
        )
        self.assertEqual(user.logged_in, False, msg="User already logged in")
        response = client.post("/", data={"username": user.username, "password": self.pw})
        user.refresh_from_db()
        self.assertEqual(response.url, "/home", msg="Redirect wrong")
        self.assertEqual(user.logged_in, True, msg="User not logged in")
        return client

    def _get_role(self):
        """ Returns the role, which is used in these tests

        Returns:
             role (Role): The role
        """
        return Role.objects.get(id=self.role_id)

    def _get_user(self):
        """ Returns the user, which is used in these tests

        Returns:
             user (User): The user
        """
        return User.objects.get(id=self.user_id)

    def test_group_creation(self):
        client = self._get_logged_in_client()
        g_name = "New Testgroup"
        params = {
            "name": g_name,
            "description": "Testdescription",
            "role": self.role_id,
            "user": self._get_user(),
        }
        client.post("/structure/groups/new/register-form/", data=params)
        exists = True
        try:
            group = Group.objects.get(
                name=g_name
            )
        except ObjectDoesNotExist:
            exists = False
        self.assertEqual(exists, True, msg="Group could not be created")
