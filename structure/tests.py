import os
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase, Client
from django.utils import timezone

from MapSkinner.settings import HTTP_OR_SSL, HOST_NAME
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
        self.group_id = group.id

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

    def _get_group(self):
        """ Returns the group, which is created in the setUp()

        Returns:
             group (Group): The group
        """
        return Group.objects.get(id=self.group_id)

    def _create_new_group(self, client: Client, name: str, parent: Group = None):
        """ Helping function

        Calls the create-new-group route

        Args:
            client (Client): The logged in client
            name (str): The new group's name
        Returns:

        """
        g_name = name
        params = {
            "name": g_name,
            "description": "Testdescription",
            "role": self.role_id,
            "user": self._get_user(),
        }
        if parent is not None:
            params["parent"] = parent.id
        client.post("/structure/groups/new/register-form/", data=params)

    def _remove_group(self, client: Client, group: Group, user: User):
        """ Helping function

        Calls the delete-group route

        Args;
            client (Client): The logged in client
            group (Group): The group which shall be deleted
            user (User): The performing user
        Returns:

        """
        params = {
            "id": group.id,
            "confirmed": True,
            "user": user,
        }

        # Use the HTTP_REFERER here! This is needed to cover the redirect, forced by the permission check decorator
        client.get("/structure/groups/remove/", data=params, HTTP_REFERER=HTTP_OR_SSL + HOST_NAME)

    def test_group_creation(self):
        """ Tests the group creation functionality

        Returns:

        """
        client = self._get_logged_in_client()
        g_name = "New Testgroup"
        self._create_new_group(client, g_name)
        exists = True
        try:
            group = Group.objects.get(
                name=g_name
            )
        except ObjectDoesNotExist:
            exists = False
        self.assertEqual(exists, True, msg="Group could not be created")
        if exists:
            self.assertEqual(group.role, self._get_role())
            self.assertEqual(group.name, g_name)

    def test_group_deletion(self):
        """ Tests the group deletion functionality

        Returns:

        """
        user = self._get_user()

        ## case 0: User not logged in, delete single group
        client = Client()
        g_name = "ToBeDeletedGroup"
        g_descr = "KillMeWithFire"
        # create group directly to get around the client-not-logged-in-for-creation-thing
        group = Group.objects.create(
            name=g_name,
            created_by=user,
            description=g_descr,
        )
        self.assertEqual(group.name, g_name)
        self.assertEqual(group.description, g_descr)

        self._remove_group(client, group, user)

        exists = True
        try:
            group.refresh_from_db()
        except ObjectDoesNotExist:
            exists = False

        self.assertEqual(exists, True, msg="Group could be deleted without user being logged in!")
        # remove group directly
        group.delete()

        ## case 1: User logged in, delete single group without subgroups
        g_name = "TestGroup"
        client = self._get_logged_in_client()
        self._create_new_group(client, g_name)
        group = Group.objects.get(
            name=g_name
        )
        self.assertNotEqual(group.id, None, msg="Group does not exist")
        self._remove_group(client, group, user)
        exists = True
        try:
            group.refresh_from_db()
        except ObjectDoesNotExist:
            exists = False
        self.assertEqual(exists, False, msg="Group still exists")

        ## case 2.1: Delete group, keep subgroups
        self._create_new_group(client, g_name)
        group = Group.objects.get(name=g_name)
        g_sub_a_name = "TestGroup_Sub_A"
        self._create_new_group(client, g_sub_a_name, group)
        g_sub_b_name = "TestGroup_Sub_B"
        self._create_new_group(client, g_sub_b_name, group)
        group_sub_a = Group.objects.get(name=g_sub_a_name)
        group_sub_b = Group.objects.get(name=g_sub_b_name)

        self.assertNotEqual(group_sub_a.id, None, msg="Sub group A does not exist")
        self.assertNotEqual(group_sub_b.id, None, msg="Sub group B does not exist")
        self.assertNotEqual(group.id, None, msg="Group does not exist")

        # delete parent group
        self._remove_group(client, group, user)
        sub_a_exists = True
        sub_b_exists = True
        try:
            group_sub_a.refresh_from_db()
        except ObjectDoesNotExist:
            sub_a_exists = False
        try:
            group_sub_b.refresh_from_db()
        except ObjectDoesNotExist:
            sub_b_exists = False

        self.assertEqual(sub_a_exists, True, msg="Sub group A does not exist anymore")
        self.assertEqual(sub_b_exists, True, msg="Sub group B does not exist anymore")
        del sub_a_exists
        del sub_b_exists

        ## case 2.2: Delete group without permission -> expect, that it won't work
        # manipulate user permission
        role = self._get_role()
        role.permission.can_delete_group = False
        role.permission.save()
        role.save()

        # try to remove sub group A
        self._remove_group(client, group_sub_a, user)
        exists = True
        try:
            group_sub_a.refresh_from_db()
        except ObjectDoesNotExist:
            exists = False
        self.assertEqual(exists, True, msg="Sub group A was removed without permission")

    def test_group_editing(self):
        """ Tests for editing functionality

        Checks if a not logged in user can edit a group
        Checks if a logged in user can edit a group
        Checks if a logged in user can not edit a group using wrong/forbidden input

        Returns:

        """
        user = self._get_user()
        group = self._get_group()
        group_id = group.id
        new_g_name = "New Groupname"
        new_descr = "Test Tralala"

        ## case 0: User is not logged in
        # the editing here should not work
        client = Client()
        error = "The user is not logged in, but could edit the group!"

        params = {
            "user": user,
            "name": new_g_name,
            "description": new_descr,
        }

        client.post("/structure/groups/edit/{}".format(self.group_id), data=params)
        group.refresh_from_db()

        self.assertNotEqual(group.name, new_g_name, msg=error)
        self.assertNotEqual(group.description, new_descr, msg=error)

        ## case 1: User is logged in, normal editing case
        client = self._get_logged_in_client()
        self._create_new_group(client, "New Parent")
        new_parent = Group.objects.get(name="New Parent")
        error = "Created group has unexpected values!"

        params = {
            "user": user,
            "name": new_g_name,
            "description": new_descr,
            "parent": new_parent.id,
        }

        self.assertEqual(group.parent, None, msg=error)
        self.assertNotEqual(group.name, new_g_name, msg=error)
        self.assertNotEqual(group.description, new_descr, msg=error)

        client.post("/structure/groups/edit/{}".format(self.group_id), data=params)

        group.refresh_from_db()
        error = "Group is not correctly editable!"

        self.assertEqual(group.id, group_id, msg=error)
        self.assertEqual(group.parent, new_parent, msg=error)
        self.assertEqual(group.name, new_g_name, msg=error)
        self.assertEqual(group.description, new_descr, msg=error)


        ## case 1.1: User is logged in, editing form is missing data or contains wrong data
        params["name"] = None  # name should not be null
        params["parent"] = group_id  # group can not be it's own parent

        client.post("/structure/groups/edit/{}".format(self.group_id), data=params)

        group.refresh_from_db()

        # we expect that nothing has changed, so we can assert the same constraints as before
        self.assertEqual(group.id, group_id, msg=error)
        self.assertEqual(group.parent, new_parent, msg=error)
        self.assertEqual(group.name, new_g_name, msg=error)
        self.assertEqual(group.description, new_descr, msg=error)








