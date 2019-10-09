import os
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase, Client
from django.utils import timezone

from MapSkinner.settings import HTTP_OR_SSL, HOST_NAME
from structure.models import Group, User, Role, Permission, Organization


class StructureTestCase(TestCase):

    def setUp(self):
        # create user who performs the actions in these tests
        self.username_A = "Testuser_A"
        self.username_B = "Testuser_B"
        self.pw = "test"
        salt = str(os.urandom(25).hex())
        pw = self.pw

        # create two different users, to check property rights during tests
        user_A = User.objects.create(
            username=self.username_A,
            salt=salt,
            password=make_password(pw, salt=salt),
            confirmed_dsgvo=timezone.now(),
            is_active=True,
        )
        self.user_A_id = user_A.id
        user_B = User.objects.create(
            username=self.username_B,
            salt=salt,
            password=make_password(pw, salt=salt),
            confirmed_dsgvo=timezone.now(),
            is_active=True,
        )
        self.user_B_id = user_B.id

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
            created_by=user_A
        )
        user_A.groups.add(group)
        user_B.groups.add(group)
        self.group_id = group.id

        # create default organization
        org = Organization.objects.create(
            organization_name="Testorganization",
            is_auto_generated=False,
            created_by=user_A,
        )
        self.org_id = org.id

    def _get_logged_in_client(self, user_id: int):
        """ Helping function to encapsulate the login process

        Returns:
             client (Client): The client object, which holds an active session for the user
             user_id (int): The user (id) who shall be logged in
        """
        client = Client()
        user = User.objects.get(
            id=user_id
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

    def _get_user_A(self):
        """ Returns the user, which is used in these tests

        Returns:
             user (User): The user
        """
        return User.objects.get(id=self.user_A_id)

    def _get_user_B(self):
        """ Returns the user, which is used in these tests

        Returns:
             user (User): The user
        """
        return User.objects.get(id=self.user_B_id)

    def _get_group(self):
        """ Returns the group, which is created in the setUp()

        Returns:
             group (Group): The group
        """
        return Group.objects.get(id=self.group_id)

    def _create_new_group(self, client: Client, user: User, name: str, parent: Group = None):
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
            "user": user,
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
        user_A = self._get_user_A()
        g_name = "New Testgroup"

        ## case 0: User not logged in -> creation fails
        client = Client()
        self._create_new_group(client, user_A, g_name)
        exists = True
        try:
            group = Group.objects.get(
                name=g_name
            )
        except ObjectDoesNotExist:
            exists = False
        self.assertEqual(exists, False, msg="Group was created by not logged in user!")

        ## case 1: User logged in -> creation as expected
        client = self._get_logged_in_client(user_A.id)
        self._create_new_group(client, user_A, g_name)
        exists = True
        try:
            group = Group.objects.get(
                name=g_name
            )
        except ObjectDoesNotExist:
            exists = False
        self.assertEqual(exists, True, msg="Group could not be created!")
        if exists:
            self.assertEqual(group.role, self._get_role())
            self.assertEqual(group.name, g_name)

        ## case 2: User logged in, uses empty group name -> creation fails
        self._create_new_group(client, user_A, "")
        exists = True
        try:
            group = Group.objects.get(
                name=""
            )
        except ObjectDoesNotExist:
            exists = False
        self.assertEqual(exists, False, msg="Group with empty name was created!")

    def test_group_deletion(self):
        """ Tests the group deletion functionality

        Returns:

        """
        user_A = self._get_user_A()
        user_B = self._get_user_B()

        ## case 0.1: User not logged in, delete own group -> fails
        client = Client()
        g_name = "ToBeDeletedGroup"
        g_descr = "KillMeWithFire"

        # create group directly to get around the client-not-logged-in-for-creation-thing
        group_of_B = Group.objects.create(
            name=g_name,
            created_by=user_B,
            description=g_descr,
            role=self._get_role()
        )

        self._remove_group(client, group_of_B, user_B)

        exists = True
        try:
            group_of_B.refresh_from_db()
        except ObjectDoesNotExist:
            exists = False

        self.assertEqual(exists, True, msg="Group of user B could be deleted without user B being logged in!")

        ## case 0.2: User not logged in, delete group of other user -> fails
        self._remove_group(client, group_of_B, user_A)

        exists = True
        try:
            group_of_B.refresh_from_db()
        except ObjectDoesNotExist:
            exists = False

        self.assertEqual(exists, True, msg="Group of user A could be deleted by user B, not logged in!")

        ## case 1.1: User logged in, delete another user's group -> fail!
        client = self._get_logged_in_client(user_A.id)
        self._remove_group(client, group_of_B, user_A)

        exists = True
        try:
            group_of_B.refresh_from_db()
        except ObjectDoesNotExist:
            exists = False

        self.assertEqual(exists, True, msg="Group of user A could be deleted by user B!")

        ## case 1.2: User logged in, delete own group, no subgroups exists
        client = self._get_logged_in_client(user_B.id)
        self._remove_group(client, group_of_B, user_B)
        exists = True
        try:
            group_of_B.refresh_from_db()
        except ObjectDoesNotExist:
            exists = False
        self.assertEqual(exists, False, msg="Group still exists!")

        ## case 2.1: User logged in, delete group, keep existing subgroups
        g_name = "TestGroup"
        self._create_new_group(client, user_B, g_name)
        group_of_B = Group.objects.get(name=g_name)
        g_sub_a_name = "TestGroup_Sub_A"
        self._create_new_group(client, user_A, g_sub_a_name, group_of_B)
        g_sub_b_name = "TestGroup_Sub_B"
        self._create_new_group(client, user_B, g_sub_b_name, group_of_B)
        group_sub_a = Group.objects.get(name=g_sub_a_name)
        group_sub_b = Group.objects.get(name=g_sub_b_name)

        self.assertNotEqual(group_sub_a.id, None, msg="Sub group A does not exist!")
        self.assertNotEqual(group_sub_b.id, None, msg="Sub group B does not exist!")
        self.assertNotEqual(group_of_B.id, None, msg="Group does not exist!")

        # delete parent group
        self._remove_group(client, group_of_B, user_B)
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

        self.assertEqual(sub_a_exists, True, msg="Sub group A does not exist anymore!")
        self.assertEqual(sub_b_exists, True, msg="Sub group B does not exist anymore!")
        del sub_a_exists
        del sub_b_exists

        ## case 2.2: Delete own group without having permissions -> fail!
        # manipulate users permission
        role = self._get_role()
        role.permission.can_delete_group = False
        role.permission.save()
        role.save()

        # try to remove sub group A
        self._remove_group(client, group_sub_a, user_A)
        exists = True
        try:
            group_sub_a.refresh_from_db()
        except ObjectDoesNotExist:
            exists = False
        self.assertEqual(exists, True, msg="Sub group A was removed without permission!")

    def test_group_editing(self):
        """ Tests for editing functionality

        Checks if a not logged in user can edit a group
        Checks if a logged in user can edit a group
        Checks if a logged in user can not edit a group using wrong/forbidden input

        Returns:

        """
        user_A = self._get_user_A()
        user_B = self._get_user_B()
        group_of_A = self._get_group()
        group_of_A_id = group_of_A.id

        new_g_name = "New Groupname"
        new_descr = "Test Tralala"
        old_g_name = group_of_A.name
        old_descr = group_of_A.description

        ## case 0.1: User is not logged in, edit another user's group -> fails
        client = Client()
        error = "The user is not logged in, but could edit another one's group!"
        params = {
            "user": user_B,
            "name": new_g_name,
            "description": new_descr,
        }

        client.post("/structure/groups/edit/{}".format(group_of_A_id), data=params)
        group_of_A.refresh_from_db()

        self.assertNotEqual(group_of_A.name, new_g_name, msg=error)
        self.assertNotEqual(group_of_A.description, new_descr, msg=error)

        ## case 0.2: User is not logged in, edit own group -> fails
        error = "The user is not logged in, but could edit the group!"

        params = {
            "user": user_A,
            "name": new_g_name,
            "description": new_descr,
        }

        client.post("/structure/groups/edit/{}".format(group_of_A_id), data=params)
        group_of_A.refresh_from_db()

        self.assertNotEqual(group_of_A.name, new_g_name, msg=error)
        self.assertNotEqual(group_of_A.description, new_descr, msg=error)

        ## case 1: User is logged in, normal editing case
        client = self._get_logged_in_client(user_A.id)
        self._create_new_group(client, user_A, "New Parent")
        new_parent = Group.objects.get(name="New Parent")

        params = {
            "user": user_A,
            "name": new_g_name,
            "description": new_descr,
            "parent": new_parent.id,
        }

        client.post("/structure/groups/edit/{}".format(group_of_A_id), data=params)

        group_of_A.refresh_from_db()
        error = "Group is not correctly editable!"

        self.assertEqual(group_of_A.id, group_of_A_id, msg=error)
        self.assertEqual(group_of_A.parent, new_parent, msg=error)
        self.assertEqual(group_of_A.name, new_g_name, msg=error)
        self.assertEqual(group_of_A.description, new_descr, msg=error)

        ## case 2.1: User is logged in, tries to edit another one's group -> fail!
        error = "Group was edited by another user!"
        client = self._get_logged_in_client(user_B.id)
        params["user"] = user_B
        params["parent"] = ""
        params["name"] = old_g_name
        params["description"] = old_descr

        client.post("/structure/groups/edit/{}".format(group_of_A_id), data=params)

        group_of_A.refresh_from_db()

        # as we expect that nothing changes, we can still check the same assertions as before
        self.assertEqual(group_of_A.id, group_of_A_id, msg=error)
        self.assertEqual(group_of_A.parent, new_parent, msg=error)
        self.assertEqual(group_of_A.name, new_g_name, msg=error)
        self.assertEqual(group_of_A.description, new_descr, msg=error)

        ## case 2.2.1: User is logged in, edits own group, name is empty -> fail
        error = "Group was edited with empty name!"
        params["name"] = ""

        client.post("/structure/groups/edit/{}".format(self.group_id), data=params)

        group_of_A.refresh_from_db()

        # we expect that nothing has changed, so we can assert the same constraints as before
        self.assertEqual(group_of_A.id, group_of_A_id, msg=error)
        self.assertEqual(group_of_A.parent, new_parent, msg=error)
        self.assertEqual(group_of_A.name, new_g_name, msg=error)
        self.assertEqual(group_of_A.description, new_descr, msg=error)

        params["name"] = new_g_name

        ## case 2.2.2: User is logged in, edits own group, shall become it's own parent -> fail
        error = "Group can be it's own parent!"
        params["parent"] = group_of_A_id  # group can not be it's own parent

        client.post("/structure/groups/edit/{}".format(self.group_id), data=params)

        group_of_A.refresh_from_db()

        # we expect that nothing has changed, so we can assert the same constraints as before
        self.assertEqual(group_of_A.id, group_of_A_id, msg=error)
        self.assertEqual(group_of_A.parent, new_parent, msg=error)
        self.assertEqual(group_of_A.name, new_g_name, msg=error)
        self.assertEqual(group_of_A.description, new_descr, msg=error)

    def _get_organization(self):
        """ Returns the organization, which is created in the setUp()

        Returns:
             organization (Organization): The organization
        """
        return Organization.objects.get(id=self.org_id)

    def _create_new_organization(self, client: Client, user: User, org_name: str, person_name: str, parent: Organization = None):
        """ Helping function

        Calls the create-new-organization route

        Args:
            client (Client): The logged in client
            user (User): The performing user
            org_name (str): The new organization's name
            person_name (str): The new organization's contact person name

        Returns:

        """
        params = {
            "user": user,
            "organization_name": org_name,
            "person_name": person_name,
        }
        if parent is not None:
            params["parent"] = parent
        client.post("/structure/organizations/new/register-form/", data=params)

    def test_organization_creation(self):
        """ Tests the organization creation functionality

        Checks if a not logged in user can create an organization
        Checks if a logged in user can create an organization
        Checks if a logged in user can create an organization using malicious data

        Returns:

        """
        user = self._get_user_A()
        ## case 0: User not logged in -> no creation possible
        client = Client()
        o_name = "NewTestorganization"
        p_name = "Testperson"
        self._create_new_organization(client, user, o_name, p_name)
        exists = True
        try:
            org = Organization.objects.get(
                organization_name=o_name
            )
        except ObjectDoesNotExist:
            exists = False
        self.assertEqual(exists, False, msg="Organization was created even though user is not logged in!")

        ## case 1: User logged in -> creation as expected
        client = self._get_logged_in_client(user.id)
        self._create_new_organization(client, user, o_name, p_name)
        exists = True
        try:
            org = Organization.objects.get(
                organization_name=o_name
            )
        except ObjectDoesNotExist:
            exists = False
        self.assertEqual(exists, True, msg="Organization could not be created!")
        self.assertEqual(org.organization_name, o_name)
        self.assertEqual(org.person_name, p_name)

        # remove organization object, so we can try to recreate it in the next test cases
        org.delete()

        ## case 2.1: User logged in, but organization name is empty -> creation fails
        self._create_new_organization(client, user, "", p_name)  # create with empty organization name
        exists = True
        try:
            org = Organization.objects.get(
                organization_name=""
            )
        except ObjectDoesNotExist:
            exists = False
        self.assertEqual(exists, False, msg="Organization with empty name was created!")

        ## case 2.2: User logged in, but person name is empty -> creation fails
        self._create_new_organization(client, user, o_name, "")  # create with empty person name
        exists = True
        try:
            org = Organization.objects.get(
                organization_name=o_name
            )
        except ObjectDoesNotExist:
            exists = False
        self.assertEqual(exists, False, msg="Organization with empty person name was created!")

    def test_organization_editing(self):
        """ Tests the organization editing functionality

        Checks if a not logged in user can edit an organization
        Checks if a logged in user can edit an organization
        Checks if a logged in user can edit an organization using malicious data

        Returns:

        """
        user_A = self._get_user_A()
        user_B = self._get_user_B()
        org_of_A = self._get_organization()

        new_o_name = "EditedOrganizationName"
        new_p_name = "Lorem Ipsum"
        new_descr = "Solo dolo washimashi"

        old_o_name = org_of_A.organization_name
        old_p_name = org_of_A.person_name
        old_descr = org_of_A.description

        ## case 0.1: User not logged in -> no editing of own organization possible
        client = Client()

        params = {
            "user": user_A,
            "organization_name": new_o_name,
            "person_name": new_p_name,
            "description": new_descr,
        }

        client.post("/structure/organizations/edit/{}".format(org_of_A.id), data=params)
        org_of_A.refresh_from_db()

        self.assertNotEqual(org_of_A.organization_name, new_o_name, msg="Organization name was edited, but user is logged out!")
        self.assertNotEqual(org_of_A.description, new_descr, msg="Organization description was edited, but user is logged out!")
        self.assertNotEqual(org_of_A.person_name, new_p_name, msg="Person name could was edited, but user is logged out!")

        ## case 0.2: User not logged in -> no editing of another user's organization possible
        params = {
            "user": user_B,
            "organization_name": new_o_name,
            "person_name": new_p_name,
            "description": new_descr,
        }

        client.post("/structure/organizations/edit/{}".format(org_of_A.id), data=params)
        org_of_A.refresh_from_db()

        self.assertNotEqual(org_of_A.organization_name, new_o_name, msg="Organization name was edited, but user is logged out!")
        self.assertNotEqual(org_of_A.description, new_descr, msg="Organization description was edited, but user is logged out!")
        self.assertNotEqual(org_of_A.person_name, new_p_name, msg="Person name could was edited, but user is logged out!")

        ## case 1: User logged in -> normal editing of own group
        client = self._get_logged_in_client(user_A.id)

        client.post("/structure/organizations/edit/{}".format(org_of_A.id), data=params)
        org_of_A.refresh_from_db()

        self.assertEqual(org_of_A.organization_name, new_o_name, msg="Organization name could not be edited!")
        self.assertEqual(org_of_A.description, new_descr, msg="Organization description could not be edited!")
        self.assertEqual(org_of_A.person_name, new_p_name, msg="Person name could not be edited!")

        ## case 2.1.1: User logged in but uses organization as it's own parent -> fail!
        params["parent"] = org_of_A.id

        client.post("/structure/organizations/edit/{}".format(org_of_A.id), data=params)
        org_of_A.refresh_from_db()

        self.assertEqual(org_of_A.parent, None, msg="Organization can be it's own parent!")
        del params["parent"]

        ## case 2.1.2: User logged in but uses empty organization name -> fail!
        params["organization_name"] = ""
        client.post("/structure/organizations/edit/{}".format(org_of_A.id), data=params)
        org_of_A.refresh_from_db()

        self.assertEqual(org_of_A.organization_name, new_o_name, msg="Empty organization name was accepted for editing!")
        params["organization_name"] = new_o_name

        ## case 2.1.3: User logged in but uses empty person name -> fail!
        params["person_name"] = ""
        client.post("/structure/organizations/edit/{}".format(org_of_A.id), data=params)
        org_of_A.refresh_from_db()

        self.assertEqual(org_of_A.person_name, new_p_name, msg="Empty person name was accepted for editing!")
        params["person_name"] = new_p_name

        ## case 2.2: User logged in but tries to edit another users organization -> fail!
        params["user"] = user_B
        params["person_name"] = old_p_name
        params["organization_name"] = old_o_name
        client.post("/structure/organizations/edit/{}".format(org_of_A.id), data=params)
        org_of_A.refresh_from_db()

        self.assertNotEqual(org_of_A.organization_name, old_o_name, msg="Organization could be edited by another user!")
        self.assertNotEqual(org_of_A.person_name, old_p_name, msg="Organization could be edited by another user!")
        self.assertNotEqual(org_of_A.description, old_descr, msg="Organization could be edited by another user!")

    def test_organization_deleting(self):
        # first create an organization that can be
        pass

    def test_organization_publish_request_creating(self):
        pass

    def test_organization_publish_request_creating_toggling(self):
        pass

    def test_organization_publish_request_(self):
        pass








