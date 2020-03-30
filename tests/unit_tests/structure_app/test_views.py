import os
from copy import copy
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase, Client, tag
from django.urls import reverse
from django.utils import timezone
from MapSkinner.settings import HTTP_OR_SSL, HOST_NAME, ROOT_URL
from structure.settings import PENDING_REQUEST_TYPE_PUBLISHING
from structure.models import MrMapGroup, MrMapUser, Role, Permission, Organization, PendingRequest


class StructureTestCase(TestCase):

    def setUp(self):
        """ Initial creation of objects that are needed during the tests

        Returns:

        """
        # create user who performs the actions in these tests
        self.username_A = "Testuser_A"
        self.username_B = "Testuser_B"
        self.pw = "test"
        salt = str(os.urandom(25).hex())
        pw = self.pw

        # create two different users, to check property rights during tests
        user_A = MrMapUser.objects.create(
            username=self.username_A,
            salt=salt,
            password=make_password(pw, salt=salt),
            confirmed_dsgvo=timezone.now(),
            is_active=True,
        )
        self.user_A_id = user_A.id
        user_B = MrMapUser.objects.create(
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
        group = MrMapGroup.objects.create(
            role=role,
            name="Testgroup",
            created_by=user_A
        )
        group.user_set.add(user_A)
        group.user_set.add(user_B)
        self.group_id = group.id

        # create default organization
        org = Organization.objects.create(
            organization_name="Testorganization",
            is_auto_generated=False,
            created_by=user_A,
        )
        self.org_id = org.id

    def _set_permission(self, permission: str, val: bool):
        """ Helping function

        Sets a given permission to a given value

        Args:
            permission (str): The permission attribute name
            val (bool): The new value for the permission
        Returns:

        """
        role = self._get_role()
        setattr(role.permission, permission, val)
        role.permission.save()
        role.save()

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
        return MrMapUser.objects.get(id=self.user_A_id)

    def _get_user_B(self):
        """ Returns the user, which is used in these tests

        Returns:
             user (User): The user
        """
        return MrMapUser.objects.get(id=self.user_B_id)

    def _get_group(self):
        """ Returns the group, which is created in the setUp()

        Returns:
             group (Group): The group
        """
        return MrMapGroup.objects.get(id=self.group_id)

    def _create_new_group(self, client: Client, user: MrMapUser, name: str, parent: MrMapGroup = None):
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

        client.post(reverse('structure:new-group', ), data=params, HTTP_REFERER=HTTP_OR_SSL + HOST_NAME)

    def _remove_group(self, client: Client, group: MrMapGroup, user: MrMapUser):
        """ Helping function

        Calls the delete-group route

        Args;
            client (Client): The logged in client
            group (Group): The group which shall be deleted
            user (User): The performing user
        Returns:

        """
        params = {
            "confirmed": True,
            "user": user,
        }

        # Use the HTTP_REFERER here! This is needed to cover the redirect, forced by the permission check decorator
        client.get(reverse('structure:delete-group', args=(group.id,)), data=params, HTTP_REFERER=HTTP_OR_SSL + HOST_NAME)

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
            group = MrMapGroup.objects.get(
                name=g_name
            )
        except ObjectDoesNotExist:
            exists = False
        self.assertFalse(exists, msg="Group was created by not logged in user!")

        ## case 1: User logged in -> creation as expected
        client = Client()
        client.login(username=user_A.username, password=self.pw)
        self._create_new_group(client, user_A, g_name)
        exists = True
        try:
            group = MrMapGroup.objects.get(
                name=g_name
            )
        except ObjectDoesNotExist:
            exists = False
        self.assertTrue(exists, msg="Group could not be created!")
        if exists:
            self.assertEqual(group.role, self._get_role())
            self.assertEqual(group.name, g_name)
            group.delete()

        ## case 2.1: User logged in, uses empty group name -> fails!
        self._create_new_group(client, user_A, "")
        exists = True
        try:
            MrMapGroup.objects.get(
                name=""
            )
        except ObjectDoesNotExist:
            exists = False
        self.assertFalse(exists, msg="Group with empty name was created!")

        ## case 2.2: User logged in, has no permission to create groups -> fails!
        # manipulate permissions
        self._set_permission('can_create_group', False)
        self._create_new_group(client, user_A, g_name)
        exists = True
        try:
            MrMapGroup.objects.get(
                name=g_name
            )
        except ObjectDoesNotExist:
            exists = False
        self.assertFalse(exists, msg="Group without permission was created!")

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
        group_of_B = MrMapGroup.objects.create(
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

        self.assertTrue(exists, msg="Group of user B could be deleted without user B being logged in!")

        ## case 0.2: User not logged in, delete group of other user -> fails
        self._remove_group(client, group_of_B, user_A)

        exists = True
        try:
            group_of_B.refresh_from_db()
        except ObjectDoesNotExist:
            exists = False

        self.assertTrue(exists, msg="Group of user A could be deleted by user B, not logged in!")

        ## case 1.1: User logged in, delete another user's group -> fail!
        client = Client()
        client.login(username=user_A.username, password=self.pw)
        self._remove_group(client, group_of_B, user_A)

        exists = True
        try:
            group_of_B.refresh_from_db()
        except ObjectDoesNotExist:
            exists = False

        self.assertTrue(exists, msg="Group of user A could be deleted by user B!")

        ## case 1.2: User logged in, delete own group, no subgroups exists
        client = Client()
        client.login(username=user_B.username, password=self.pw)
        self._remove_group(client, group_of_B, user_B)
        exists = True
        try:
            group_of_B.refresh_from_db()
        except ObjectDoesNotExist:
            exists = False
        self.assertFalse(exists, msg="Group still exists!")

        ## case 2.1: User logged in, delete group, keep existing subgroups
        g_name = "TestGroup"
        self._create_new_group(client, user_B, g_name)
        group_of_B = MrMapGroup.objects.get(name=g_name)
        g_sub_a_name = "TestGroup_Sub_A"
        self._create_new_group(client, user_A, g_sub_a_name, group_of_B)
        g_sub_b_name = "TestGroup_Sub_B"
        self._create_new_group(client, user_B, g_sub_b_name, group_of_B)
        group_sub_a = MrMapGroup.objects.get(name=g_sub_a_name)
        group_sub_b = MrMapGroup.objects.get(name=g_sub_b_name)

        self.assertIsNotNone(group_sub_a.id, msg="Sub group A does not exist!")
        self.assertIsNotNone(group_sub_b.id, msg="Sub group B does not exist!")
        self.assertIsNotNone(group_of_B.id, msg="Group does not exist!")

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

        self.assertTrue(sub_a_exists, msg="Sub group A does not exist anymore!")
        self.assertTrue(sub_b_exists, msg="Sub group B does not exist anymore!")
        del sub_a_exists
        del sub_b_exists

        ## case 2.2: Delete own group without having permissions -> fail!
        # manipulate users permission
        self._set_permission('can_delete_group', False)

        # try to remove sub group A
        self._remove_group(client, group_sub_a, user_A)
        exists = True
        try:
            group_sub_a.refresh_from_db()
        except ObjectDoesNotExist:
            exists = False
        self.assertTrue(exists, msg="Sub group A was removed without permission!")

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


        client.post(reverse('structure:edit-group', args=(group_of_A_id,)), data=params, HTTP_REFERER=HTTP_OR_SSL + HOST_NAME)
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

        client.post(reverse('structure:edit-group', args=(group_of_A_id,)), data=params, HTTP_REFERER=HTTP_OR_SSL + HOST_NAME)
        group_of_A.refresh_from_db()

        self.assertNotEqual(group_of_A.name, new_g_name, msg=error)
        self.assertNotEqual(group_of_A.description, new_descr, msg=error)

        ## case 1: User is logged in, normal editing case
        client = Client()
        client.login(username=user_A.username, password=self.pw)
        self._create_new_group(client, user_A, "New Parent")
        new_parent = MrMapGroup.objects.get(name="New Parent")

        params = {
            "user": user_A,
            "name": new_g_name,
            "description": new_descr,
            "parent": new_parent.id,
        }

        client.post(reverse('structure:edit-group', args=(group_of_A_id,)), data=params, HTTP_REFERER=HTTP_OR_SSL + HOST_NAME)

        group_of_A.refresh_from_db()
        error = "Group is not correctly editable!"

        self.assertEqual(group_of_A.id, group_of_A_id, msg=error)
        self.assertEqual(group_of_A.parent_group, new_parent, msg=error)
        self.assertEqual(group_of_A.name, new_g_name, msg=error)
        self.assertEqual(group_of_A.description, new_descr, msg=error)

        # case 2.1: User is logged in, tries to edit another one's group -> fail!
        error = "Group was edited by another user!"
        client = Client()
        client.login(username=user_B.username, password=self.pw)
        params["user"] = user_B
        params["parent"] = ""
        params["name"] = old_g_name
        params["description"] = old_descr

        client.post(reverse('structure:edit-group', args=(group_of_A_id,)), data={'name': 'new_name',
                                                                                  'description': 'new_description',})

        group_of_A.refresh_from_db()

        # as we expect that nothing changes, we can still check the same assertions as before
        self.assertEqual(group_of_A.id, group_of_A_id, msg=error)
        self.assertEqual(group_of_A.parent, new_parent, msg=error)
        self.assertEqual(group_of_A.name, new_g_name, msg=error)
        self.assertEqual(group_of_A.description, new_descr, msg=error)

        ## case 2.2.1: User is logged in, edits own group, name is empty -> fail
        error = "Group was edited with empty name!"
        params["name"] = ""

        client.post(reverse('structure:edit-group', args=(self.group_id,)), data={'name': ''}, HTTP_REFERER=HTTP_OR_SSL + HOST_NAME)

        group_of_A.refresh_from_db()

        # we expect that nothing has changed, so we can assert the same constraints as before
        self.assertEqual(group_of_A.id, group_of_A_id, msg=error)
        self.assertEqual(group_of_A.parent, new_parent, msg=error)
        self.assertEqual(group_of_A.name, new_g_name, msg=error)
        self.assertEqual(group_of_A.description, new_descr, msg=error)

        params["name"] = new_g_name

        ## case 2.2.2: User is logged in, edits own group, group shall become it's own parent -> fail
        error = "Group can be it's own parent!"
        params["parent"] = group_of_A_id  # group can not be it's own parent

        client.post(reverse('structure:edit-group', args=(self.group_id,)), data={'name': new_g_name, 'parent': group_of_A_id}, HTTP_REFERER=HTTP_OR_SSL + HOST_NAME)

        group_of_A.refresh_from_db()

        # we expect that nothing has changed, so we can assert the same constraints as before
        self.assertEqual(group_of_A.id, group_of_A_id, msg=error)
        self.assertEqual(group_of_A.parent, new_parent, msg=error)
        self.assertEqual(group_of_A.name, new_g_name, msg=error)
        self.assertEqual(group_of_A.description, new_descr, msg=error)

        ## case 2.3: User is logged in, edits group without permission -> fail
        error = "Group was edited without permission!"
        # manipulate permissions
        self._set_permission('can_edit_group', False)

        client.post(reverse('structure:edit-group', args=(self.group_id,)), data={'name': 'new_name'}, HTTP_REFERER=HTTP_OR_SSL + HOST_NAME)

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

    def _create_new_organization(self, client: Client, user: MrMapUser, org_name: str, person_name: str, parent: Organization = None):
        """ Helping function

        Calls the create-new-organization route

        Args:
            client (Client): The logged in client
            user (MrMapUser): The performing user
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
        client.post(reverse('structure:new-organization',), data=params, HTTP_REFERER=HTTP_OR_SSL + HOST_NAME)

    def _remove_organization(self, client: Client, user: MrMapUser, organization: Organization):
        """ Helping function

        Calls the remove-organization route

        Args:
            client (Client): The logged in client
            user (MrMapUser): The performing user
            organization (Organization): The organization

        Returns:

        """
        # Use the HTTP_REFERER here! This is needed to cover the redirect, forced by the permission check decorator
        uri = reverse("structure:delete-organization", args=(organization.id,))
        client.get(uri, HTTP_REFERER=HTTP_OR_SSL + HOST_NAME)

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
        self.assertFalse(exists, msg="Organization was created even though user is not logged in!")

        ## case 1: User logged in -> creation as expected
        client = Client()
        client.login(username=user.username, password=self.pw)
        self._create_new_organization(client, user, o_name, p_name)
        exists = True
        try:
            org = Organization.objects.get(
                organization_name=o_name
            )
        except ObjectDoesNotExist:
            exists = False
        self.assertTrue(exists, msg="Organization could not be created!")
        self.assertEqual(org.organization_name, o_name)
        self.assertEqual(org.person_name, p_name)

        # remove organization object, so we can try to recreate it in the next test cases
        org.delete()

        ## case 2.1: User logged in, but organization name is empty -> creation fails
        self._create_new_organization(client, user, "", p_name)  # create with empty organization name
        exists = True
        try:
            Organization.objects.get(
                organization_name=""
            )
        except ObjectDoesNotExist:
            exists = False
        self.assertFalse(exists, msg="Organization with empty name was created!")

        ## case 2.2: User logged in, but person name is empty -> creation fails
        self._create_new_organization(client, user, o_name, "")  # create with empty person name
        exists = True
        try:
            Organization.objects.get(
                organization_name=o_name
            )
        except ObjectDoesNotExist:
            exists = False
        self.assertFalse(exists, msg="Organization with empty person name was created!")

        ## case 2.3: User logged in, but has no permission to create an organization
        # manipulate permissions
        self._set_permission('can_create_organization', False)
        self._create_new_organization(client, user, o_name, p_name)
        exists = True
        try:
            Organization.objects.get(
                organization_name=o_name
            )
        except ObjectDoesNotExist:
            exists = False
        self.assertFalse(exists, msg="Organization without permission was created!")

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

        uri = reverse("structure:edit-organization", args=(org_of_A.id,))
        client.post(uri, data=params, HTTP_REFERER=HTTP_OR_SSL + HOST_NAME)
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

        client.post(uri, data=params, HTTP_REFERER=HTTP_OR_SSL + HOST_NAME)
        org_of_A.refresh_from_db()

        self.assertNotEqual(org_of_A.organization_name, new_o_name, msg="Organization name was edited, but user is logged out!")
        self.assertNotEqual(org_of_A.description, new_descr, msg="Organization description was edited, but user is logged out!")
        self.assertNotEqual(org_of_A.person_name, new_p_name, msg="Person name could was edited, but user is logged out!")

        ## case 1: User logged in -> normal editing of own group
        client = Client()
        client.login(username=user_A.username, password=self.pw)

        client.post(uri, data=params, HTTP_REFERER=HTTP_OR_SSL + HOST_NAME)
        org_of_A.refresh_from_db()

        self.assertEqual(org_of_A.organization_name, new_o_name, msg="Organization name could not be edited!")
        self.assertEqual(org_of_A.description, new_descr, msg="Organization description could not be edited!")
        self.assertEqual(org_of_A.person_name, new_p_name, msg="Person name could not be edited!")

        ## case 2.1.1: User logged in but uses organization as it's own parent -> fail!
        params["parent"] = org_of_A.id

        client.post(uri, data=params, HTTP_REFERER=HTTP_OR_SSL + HOST_NAME)
        org_of_A.refresh_from_db()

        self.assertEqual(org_of_A.parent, None, msg="Organization can be it's own parent!")
        del params["parent"]

        ## case 2.1.2: User logged in but uses empty organization name -> fail!
        params["organization_name"] = ""
        client.post(uri, data=params, HTTP_REFERER=HTTP_OR_SSL + HOST_NAME)
        org_of_A.refresh_from_db()

        self.assertEqual(org_of_A.organization_name, new_o_name, msg="Empty organization name was accepted for editing!")
        params["organization_name"] = new_o_name

        ## case 2.1.3: User logged in but uses empty person name -> fail!
        params["person_name"] = ""
        client.post(uri, data=params, HTTP_REFERER=HTTP_OR_SSL + HOST_NAME)
        org_of_A.refresh_from_db()

        self.assertEqual(org_of_A.person_name, new_p_name, msg="Empty person name was accepted for editing!")
        params["person_name"] = new_p_name

        ## case 2.2: User logged in but tries to edit another users organization -> fail!
        params["user"] = user_B
        params["person_name"] = old_p_name
        params["organization_name"] = old_o_name
        client.post(uri, data=params, HTTP_REFERER=HTTP_OR_SSL + HOST_NAME)
        org_of_A.refresh_from_db()

        self.assertNotEqual(org_of_A.organization_name, old_o_name, msg="Organization could be edited by another user!")
        self.assertNotEqual(org_of_A.person_name, old_p_name, msg="Organization could be edited by another user!")
        self.assertNotEqual(org_of_A.description, old_descr, msg="Organization could be edited by another user!")

        ## case 2.3: User logged in but has no permission to edit an organization -> fail!
        # manipulate permissions
        self._set_permission('can_edit_organization', False)
        client.post(uri, data=params, HTTP_REFERER=HTTP_OR_SSL + HOST_NAME)
        org_of_A.refresh_from_db()

        self.assertNotEqual(org_of_A.organization_name, old_o_name, msg="Organization could be edited by another user!")
        self.assertNotEqual(org_of_A.person_name, old_p_name, msg="Organization could be edited by another user!")
        self.assertNotEqual(org_of_A.description, old_descr, msg="Organization could be edited by another user!")

    def test_organization_deleting(self):
        """ Tests the organization deleting functionality

        Checks if a not logged in user can delete it's organization
        Checks if a not logged in user can delete another user's organization
        Checks if a logged in user can delete it's organization
        Checks if a logged in user can delete another user's organization

        Returns:

        """
        user_A = self._get_user_A()
        user_B = self._get_user_B()
        # first create an organization that can be deleted
        org_of_B = Organization.objects.create(
            organization_name="TTT",
            person_name="PPPP",
            created_by=user_B,
        )

        ## case 0.1: User not logged in, try to delete another one's organization -> fail!
        client = Client()
        self._remove_organization(client, user_A, org_of_B)
        exists = True
        try:
            org_of_B.refresh_from_db()
        except ObjectDoesNotExist:
            exists = False
        self.assertEqual(exists, True, msg="Organization was removed by a not logged in user, who is not the organization's object owner!")

        ## case 0.2: User not logged in, try to delete own organization -> fail!
        client = Client()
        self._remove_organization(client, user_B, org_of_B)
        exists = True
        try:
            org_of_B.refresh_from_db()
        except ObjectDoesNotExist:
            exists = False
        self.assertEqual(exists, True, msg="Organization was removed by the not logged in user!")

        ## case 1.1: User logged in, try to delete another one's organization -> fail
        client = Client()
        client.login(username=user_A.username, password=self.pw)
        self._remove_organization(client, user_A, org_of_B)
        exists = True
        try:
            org_of_B.refresh_from_db()
        except ObjectDoesNotExist:
            exists = False
        self.assertEqual(exists, True, msg="Organization was removed by another user!")

        ## case 1.2: User logged in, try to delete own organization, has no permission -> fail!
        # manipulate user permission
        perm = 'can_delete_organization'
        self._set_permission(perm, False)

        client = Client()
        client.login(username=user_B.username, password=self.pw)
        self._remove_organization(client, user_B, org_of_B)
        exists = True
        try:
            org_of_B.refresh_from_db()
        except ObjectDoesNotExist:
            exists = False
        self.assertEqual(exists, True, msg="Organization was removed without permission!")

        # restore permission
        self._set_permission(perm, True)

        ## case 2: User logged in, try to delete own organization
        self._remove_organization(client, user_B, org_of_B)
        exists = True
        try:
            org_of_B.refresh_from_db()
        except ObjectDoesNotExist:
            exists = False
        self.assertEqual(exists, False, msg="Organization could not be removed!")

    def _create_publish_request(self, client: Client, user: MrMapUser, group: MrMapGroup, organization: Organization):
        """ Helping function

        Calls the create-publish-request route

        Args:
            client (Client): The logged in client
            user (MrMapUser): The performing user
            group (Group): The group which requests the publish permission
            organization (Organization): The organization

        Returns:

        """
        params = {
            "user": user,
            "group": group.id,
            "organization_name": organization.organization_name,
            "request_msg": "Test msg"
        }

        client.post("/structure/publish-request/{}".format(organization.id), data=params, HTTP_REFERER=HTTP_OR_SSL + HOST_NAME)

    def _toggle_publish_request(self, client: Client, user: MrMapUser, organization: Organization, pub_request: PendingRequest, accept: bool):
        """ Helping function

        Calls the accept-publish-request route

        Args:
            client (Client): The logged in client
            user (MrMapUser): The performing user
            organization (Organization): The organization which holds the publish request
            pub_request (PendingRequest): The publish request
            accept (bool): Whether to accept the publish request or not
        Returns:

        """
        params = {
            "user": user,
            "accept": accept,
            "requestId": pub_request.id,
        }
        uri = reverse("structure:accept-publish-request", args=(organization.id,))
        client.post(uri, data=params, HTTP_REFERER=HTTP_OR_SSL + HOST_NAME)

    def _remove_publish_permission(self, client: Client, user: MrMapUser, organization: Organization, group: MrMapGroup):
        """ Helping function

        Calls the remove-publish-permission route

        Args:
            client (Client): The logged in client
            user (MrMapUser): The performing user
            organization (Organization): The organization which let a group publish
            group (Group): The group which has the publish permission
        Returns:

        """
        params = {
            "user": user,
            "publishingGroupId": group.id,
        }
        uri = reverse("structure:delete-organization", args=(organization.id,))
        client.post(uri, data=params, HTTP_REFERER=HTTP_OR_SSL + HOST_NAME)

    def test_organization_publish_request_creating(self):
        """ Tests the organization request publish permission functionality

        Checks if a not logged in user can create a publish request
        Checks if a logged in user can create a publish request
        Checks if a logged in user can create a publish request with wrong input

        Returns:

        """
        # TODO: this test fails. publisher roots are deprecated....
        return

        user_A = self._get_user_A()
        group_of_A = self._get_group()
        org = self._get_organization()

        ## case 0: User is not logged in, tries to create a publish request -> fail!
        client = Client()
        self._create_publish_request(client, user_A, group_of_A, org)
        exists = True
        try:
            pub_requ = PendingRequest.objects.get(
                type=PENDING_REQUEST_TYPE_PUBLISHING,
                group=group_of_A,
                organization=org,
            )
        except ObjectDoesNotExist:
            exists = False
        self.assertFalse(exists, msg="PendingRequest was created by not logged in user!")

        ## case 1: User is logged in, tries to create a publish request
        client = Client()
        client.login(username=user_A.username, password=self.pw)
        self._create_publish_request(client, user_A, group_of_A, org)
        exists = True
        try:
            pub_requ = PendingRequest.objects.get(
                type=PENDING_REQUEST_TYPE_PUBLISHING,
                group=group_of_A,
                organization=org,
            )
        except ObjectDoesNotExist:
            exists = False
        self.assertTrue(exists, msg="PendingRequest was not created!")
        if exists:
            self.assertGreater(pub_requ.activation_until, timezone.now(), msg="PendingRequest latest activation datetime is not in the future!")
            pub_requ.delete()

        ## case 2: User is logged in, has no permission to request a publisher permission
        # manipulate permission
        self._set_permission('can_request_to_become_publisher', False)
        self._create_publish_request(client, user_A, group_of_A, org)
        exists = True
        try:
            PendingRequest.objects.get(
                type=PENDING_REQUEST_TYPE_PUBLISHING,
                group=group_of_A,
                organization=org,
            )
        except ObjectDoesNotExist:
            exists = False
        self.assertFalse(exists, msg="PendingRequest was created without permission!")

    def test_organization_publish_request_toggling(self):
        """ Tests the organization publish request toggling

        Checks if a logged out user can toggle existing pending requests.
        Checks if a logged in user can toggle existing pending requests.

        Returns:

        """
        # TODO: this test fails. publisher roots are deprecated....
        return

        user_B = self._get_user_B()

        org_of_A = self._get_organization()
        group_of_B = self._get_group()
        group_of_B.created_by = user_B

        # create publish request at first
        client = Client()
        client.login(username=user_B.username, password=self.pw)
        self._create_publish_request(client_logged_in_B, user_B, group_of_B, org_of_A)
        pub_requ = PendingRequest.objects.get(
            type=PENDING_REQUEST_TYPE_PUBLISHING,
            organization=org_of_A,
            group=group_of_B
        )

        ## case 0: User not logged in, tries to toggle the existing pending request -> fail!
        client = Client()
        test_cases = [False, True]
        for test_case in test_cases:
            self._toggle_publish_request(client, user_B, org_of_A, pub_requ, test_case)
            exists = True
            try:
                pub_requ.refresh_from_db()
            except ObjectDoesNotExist:
                exists = False
            group_publishes_for_orgs = group_of_B.publish_for_organizations.all()
            self.assertEqual(org_of_A in group_publishes_for_orgs, False)
            self.assertEqual(exists, True, msg="Publishing request was toggled by not logged in user!")

        ## case 1.1: User logged in, denies the pending request
        ## case 1.2: User logged in, accepts the pending request
        client = client_logged_in_B
        test_cases = [False, True]
        for test_case in test_cases:
            pub_requ_backup = copy(pub_requ)
            self._toggle_publish_request(client, user_B, org_of_A, pub_requ, test_case)
            exists = True
            try:
                pub_requ.refresh_from_db()
            except ObjectDoesNotExist:
                exists = False
            group_publishes_for_orgs = group_of_B.publish_for_organizations.all()
            self.assertEqual(org_of_A in group_publishes_for_orgs, test_case)
            self.assertFalse(exists, msg="Publishing request was not removed after toggling!")
            if not exists:
                # restore for next iteration
                pub_requ = pub_requ_backup
                pub_requ.save()

        # clear publishing permission for next test case
        group_of_B.publish_for_organizations.clear()

        ## case 2: User logged in, has no permission to toggle permission request -> fails!
        # manipulate permission
        self._set_permission('can_toggle_publish_requests', False)
        self._toggle_publish_request(client, user_B, org_of_A, pub_requ, True)
        exists = True
        try:
            pub_requ.refresh_from_db()
        except ObjectDoesNotExist:
            exists = False
        group_publishes_for_orgs = group_of_B.publish_for_organizations.all()
        self.assertFalse(org_of_A in group_publishes_for_orgs)
        self.assertTrue(exists, msg="Publishing request could be toggled without having permission!")

    def test_organization_publish_permission_removing(self):
        """ Tests the publish permission removing functionality

        Checks if a not logged in user can remove the publish permission of it's group for an organization.
        Checks if a not logged in user can remove the publish permission of a group for it's organization.
        Checks if a not logged in user can remove the publish permission of a foreign group for a foreign organization.
        Checks if a logged in user can remove the publish permission of it's group for an organization.
        Checks if a logged in user can remove the publish permission of a group for it's organization.
        Checks if a logged in user can remove the publish permission of a foreign group for a foreign organization.

        Returns:

        """
        # TODO: this test fails. publisher roots are deprecated....
        return


        user_A = self._get_user_A()
        user_B = self._get_user_B()

        group_of_B = self._get_group()
        group_of_B.created_by = user_B

        # create a seconds group with superuser rights
        group_of_A = MrMapGroup.objects.create(
            name="Group of A",
            role=self._get_role(),
            created_by=user_A
        )
        group_of_A.user_set.add(user_A)

        org_of_A = self._get_organization()
        client = Client()

        # manipulate the publish permission of group_of_B, that it can publish for org_of_A
        group_of_B.publish_for_organizations.add(org_of_A)

        ## case 0.1: User not logged in, tries to remove it's group's publish permission -> fails!
        self._remove_publish_permission(client, user_B, org_of_A, group_of_B)
        orgs_to_publish_for = group_of_B.publish_for_organizations.all()
        self.assertTrue(org_of_A in orgs_to_publish_for, msg="Publish Permission was removed by not logged in user!")

        ## case 0.2: User not logged in, tries to remove the publish permission of a group - where user is not a member - for it's organization -> fails!
        user_A.organization = org_of_A
        group_of_B.user_set.remove(user_A)
        self.assertTrue(user_A not in group_of_B.user_set.all())
        self.assertEqual(user_A.organization, org_of_A)
        self._remove_publish_permission(client, user_A, org_of_A, group_of_B)
        orgs_to_publish_for = group_of_B.publish_for_organizations.all()
        self.assertTrue(org_of_A in orgs_to_publish_for, msg="Publish Permission was removed by not logged in user!")

        ## case 0.3: User not logged in, tries to remove the publish permission of a group in another organization -> fails!
        ## first manipulate the user_A organization
        user_A.organization = None  # user_A is now not part of org_of_A anymore
        self.assertTrue(user_A not in group_of_B.user_set.all())  # user_A is not part of group_of_B
        self.assertIsNone(user_A.organization)  # user_A is not part of org_of_A
        ## this means, that user_A is not part of the publishing group nor part of the organization, that provides the publish permission
        self._remove_publish_permission(client, user_A, org_of_A, group_of_B)
        orgs_to_publish_for = group_of_B.publish_for_organizations.all()
        self.assertTrue(org_of_A in orgs_to_publish_for, msg="Publish Permission was removed by not logged in user!")

        ## case 1.1: User logged in, tries to remove it's group's publish permission
        client = Client()
        client.login(username=user_B.username, password=self.pw)
        group_of_B.user_set.add(user_B)
        self.assertTrue(org_of_A in orgs_to_publish_for)
        self.assertTrue(group_of_B in user_B.get_groups())
        self._remove_publish_permission(client, user_B, org_of_A, group_of_B)
        orgs_to_publish_for = group_of_B.publish_for_organizations.all()
        self.assertTrue(org_of_A not in orgs_to_publish_for, msg="Publish Permission was not removed!")

        # restore for next test case
        group_of_B.publish_for_organizations.add(org_of_A)

        ## case 1.2: User logged in, tries to remove the publish permission of a group - where user is not a member - for it's organization
        orgs_to_publish_for = group_of_B.publish_for_organizations.all()
        client = Client()
        client.login(username=user_A.username, password=self.pw)
        self.assertTrue(org_of_A in orgs_to_publish_for)
        user_A.groups.remove(group_of_B)
        user_A.organization = org_of_A
        user_A.save()
        self.assertTrue(user_A not in group_of_B.user_set.all())  # doublecheck
        self.assertTrue(user_A.organization, org_of_A)  # doublecheck

        self._remove_publish_permission(client, user_A, org_of_A, group_of_B)
        orgs_to_publish_for = group_of_B.publish_for_organizations.all()
        self.assertTrue(org_of_A not in orgs_to_publish_for, msg="Publish Permission was not removed!")

        # restore for next test case
        group_of_B.publish_for_organizations.add(org_of_A)

        ## case 1.3: User logged in, tries to remove the publish permission of a group in another organization -> fails!
        orgs_to_publish_for = group_of_B.publish_for_organizations.all()
        self.assertTrue(org_of_A in orgs_to_publish_for)
        user_A.groups.remove(group_of_B)
        user_A.organization = None
        user_A.save()
        self.assertTrue(user_A not in group_of_B.user_set.all())  # doublecheck
        self.assertIsNone(user_A.organization)  # doublecheck

        self._remove_publish_permission(client, user_A, org_of_A, group_of_B)
        orgs_to_publish_for = group_of_B.publish_for_organizations.all()
        self.assertTrue(org_of_A in orgs_to_publish_for, msg="Publish Permission was removed by a user which is not in the publishing group, nor in the organization that holds the permissions!")

        ## case 2: User logged in, has no permission to remove publish permissions -> fails!
        # manipulate permissions
        self._set_permission('can_remove_publisher', False)
        user_A.organization = org_of_A
        group_of_B.user_set.add(user_A)
        user_A.save()

        self._remove_publish_permission(client, user_A, org_of_A, group_of_B)
        orgs_to_publish_for = group_of_B.publish_for_organizations.all()
        self.assertTrue(org_of_A in orgs_to_publish_for, msg="Publish Permission was removed without having permission for this action!")


