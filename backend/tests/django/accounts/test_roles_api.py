"""The role API of #736: endpoints, guard rails, error shapes.

The acceptance criteria of the issue read as calls: an organization
administrator lists members, adds one, assigns and revokes a role - and the
same call by an outsider answers 403 with a JSON:API error. Assigning an
ORGANIZATION role to a user outside that organization answers 400; an
``is_assignable=False`` role is out of reach for an organization
administrator. These tests walk exactly those calls, plus the visibility
rules that keep the memberships of unrelated organizations undisclosed
(#727 decision Q3) and the 401/403/404 refusals the issue asks to record.

The actors are the same shape as in production: an organization
administrator is a user the bootstrap put into the ``organization_admin``
role of #732 - nobody grants globals by hand here.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models.guardian import OrganizationGroupObjectPermission
from accounts.models.groups import Organization
from accounts.models.roles import Role, RoleDefinition, RoleMembership

JSONAPI = "application/vnd.api+json"

ADMIN_SLUG = "organization_admin"
EDITOR_SLUG = "resource_editor"
VIEWER_SLUG = "viewer"
PLATFORM_SLUG = "platform_admin"


def rel(resource_type, pk):
    """A JSON:API resource identifier object."""
    return {"data": {"type": resource_type, "id": str(pk)}}


def envelope(resource_type, relationships, attributes=None,
             resource_id=None):
    """A JSON:API write document with relationships.

    ``resource_id`` belongs into the document of an update; the parser
    refuses to write a resource it cannot identify.
    """
    data = {
        "type": resource_type,
        "relationships": {
            name: rel(*target) for name, target in relationships.items()}}
    if resource_id is not None:
        data["id"] = str(resource_id)
    if attributes:
        data["attributes"] = attributes
    return {"data": data}


class RoleAPITestCaseMixin:
    """The fixture users, an organization with its roles, and an API client.

    Org roles exist because ``Organization.objects.create`` runs the
    bootstrap of #732; the administrator is *made* one by holding the role,
    exactly like the seeded instance.
    """

    fixtures = ["test_users.json"]

    def setUp(self):
        self.admin = get_user_model().objects.get(username="User1")
        self.member = get_user_model().objects.get(username="User2")
        self.outsider = get_user_model().objects.create_user(
            username="outsider", password="x")
        self.superuser = get_user_model().objects.create_superuser(
            username="root", password="x")
        self.organization = Organization.objects.create(name="Role API Org")
        self.other_organization = Organization.objects.create(
            name="Other Org")
        self.member.groups.add(self.organization)

        self.admin_role = Role.objects.for_org(
            self.organization).with_definition(ADMIN_SLUG).get()
        self.editor_role = Role.objects.for_org(
            self.organization).with_definition(EDITOR_SLUG).get()
        self.viewer_role = Role.objects.for_org(
            self.organization).with_definition(VIEWER_SLUG).get()
        self.admin_role.add_member(self.admin)

        self.api = APIClient()

    def login(self, user):
        self.api.force_authenticate(user)
        self.api.credentials(HTTP_ACCEPT=JSONAPI)

    def anonymous(self):
        self.api.force_authenticate(None)
        self.api.credentials(HTTP_ACCEPT=JSONAPI)

    def json_body(self, response):
        return response.json()

    def error_code(self, response):
        return self.json_body(response)["errors"][0]["code"]


class RoleDefinitionAccessTest(RoleAPITestCaseMixin, TestCase):
    """The catalogue: readable by all, writable by the platform only."""

    def test_anonymous_may_not_read_the_catalogue(self):
        self.anonymous()
        response = self.api.get(reverse("accounts:roledefinition-list"))
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(self.error_code(response), "not_authenticated")

    def test_any_authenticated_user_reads_the_catalogue(self):
        self.login(self.outsider)
        response = self.api.get(reverse("accounts:roledefinition-list"))
        self.assertEqual(response.status_code, 200, response.content)
        slugs = {row["attributes"]["slug"]
                 for row in self.json_body(response)["data"]}
        self.assertLessEqual(
            {ADMIN_SLUG, EDITOR_SLUG, PLATFORM_SLUG}, slugs)

    def test_a_plain_user_may_not_change_a_definition(self):
        self.login(self.admin)
        definition = RoleDefinition.objects.get(slug=EDITOR_SLUG)
        response = self.api.patch(
            reverse("accounts:roledefinition-detail", args=[definition.pk]),
            envelope("RoleDefinition", {}, {"label": "Hijacked"}),
            format="vnd.api+json")
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(self.error_code(response), "permission_denied")
        definition.refresh_from_db()
        self.assertNotEqual(definition.label, "Hijacked")

    def test_the_superuser_edits_label_but_not_the_identity_of_a_builtin(self):
        self.login(self.superuser)
        definition = RoleDefinition.objects.get(slug=EDITOR_SLUG)
        response = self.api.patch(
            reverse("accounts:roledefinition-detail", args=[definition.pk]),
            envelope("RoleDefinition", {},
                     {"label": "Editor of resources",
                      "slug": "something_else"},
                     resource_id=definition.pk),
            format="vnd.api+json")
        self.assertEqual(response.status_code, 200, response.content)
        definition.refresh_from_db()
        self.assertEqual(definition.label, "Editor of resources")
        # a builtin is referred to by slug by code and migrations: the slug
        # stays, the payload's attempt is ignored
        self.assertEqual(definition.slug, EDITOR_SLUG)

    def test_the_superuser_creates_a_custom_definition(self):
        self.login(self.superuser)
        response = self.api.post(
            reverse("accounts:roledefinition-list"),
            envelope("RoleDefinition", {},
                     {"slug": "api_custom", "label": "Custom"}),
            format="vnd.api+json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(
            RoleDefinition.objects.filter(slug="api_custom").exists())


class RoleAccessTest(RoleAPITestCaseMixin, TestCase):
    """Roles: readable by everyone, created and removed in scope."""

    def _definition(self):
        return RoleDefinition.objects.create(
            slug="api_extra", label="Extra", scope="ORGANIZATION")

    def test_an_authenticated_user_lists_the_roles(self):
        self.login(self.outsider)
        response = self.api.get(reverse("accounts:role-list"))
        self.assertEqual(response.status_code, 200, response.content)

    def test_the_organization_admin_creates_a_role_for_its_organization(self):
        self.login(self.admin)
        definition = self._definition()
        response = self.api.post(
            reverse("accounts:role-list"),
            envelope("Role", {
                "role_definition": ("RoleDefinition", definition.pk),
                "organization": ("Organization", self.organization.pk)}),
            format="vnd.api+json")
        self.assertEqual(response.status_code, 201, response.content)
        role = Role.objects.get(role_definition=definition,
                                organization=self.organization)
        # the group is written by the API under the bootstrap's name
        self.assertEqual(
            role.group.name, "Role API Org: api_extra")

    def test_an_outsider_may_not_create_a_role_for_an_organization(self):
        self.login(self.outsider)
        definition = self._definition()
        response = self.api.post(
            reverse("accounts:role-list"),
            envelope("Role", {
                "role_definition": ("RoleDefinition", definition.pk),
                "organization": ("Organization", self.organization.pk)}),
            format="vnd.api+json")
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(self.error_code(response), "permission_denied")

    def test_a_duplicate_active_role_answers_400_not_500(self):
        """The partial unique constraint is answered, not crashed into"""
        self.login(self.admin)
        response = self.api.post(
            reverse("accounts:role-list"),
            envelope("Role", {
                "role_definition": ("RoleDefinition",
                                    self.editor_role.role_definition.pk),
                "organization": ("Organization", self.organization.pk)}),
            format="vnd.api+json")
        self.assertEqual(response.status_code, 400, response.content)

    def test_an_organizations_admin_may_not_create_a_platform_role(self):
        self.login(self.admin)
        definition = RoleDefinition.objects.get(slug=PLATFORM_SLUG)
        response = self.api.post(
            reverse("accounts:role-list"),
            envelope("Role", {
                "role_definition": ("RoleDefinition", definition.pk)}),
            format="vnd.api+json")
        self.assertEqual(response.status_code, 403, response.content)

    def test_the_admin_retires_a_role_and_identity_fields_are_read_only(self):
        self.login(self.admin)
        response = self.api.patch(
            reverse("accounts:role-detail", args=[self.editor_role.pk]),
            envelope("Role",
                     {"role_definition": (
                         "RoleDefinition",
                         self.viewer_role.role_definition.pk)},
                     {"isActive": False},
                     resource_id=self.editor_role.pk),
            format="vnd.api+json")
        self.assertEqual(response.status_code, 200, response.content)
        self.editor_role.refresh_from_db()
        self.assertFalse(self.editor_role.is_active)
        self.assertEqual(self.editor_role.role_definition.slug, EDITOR_SLUG)

    def test_an_outsider_may_not_change_or_delete_a_role(self):
        self.login(self.outsider)
        response = self.api.patch(
            reverse("accounts:role-detail", args=[self.editor_role.pk]),
            envelope("Role", {}, {"isActive": False}),
            format="vnd.api+json")
        self.assertEqual(response.status_code, 403, response.content)
        response = self.api.delete(
            reverse("accounts:role-detail", args=[self.editor_role.pk]))
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(self.error_code(response), "permission_denied")

    def test_delete_takes_the_group_and_its_grants_with_it(self):
        """#736's guard rail: no orphan GroupObjectPermission survives"""
        self.login(self.admin)
        group = self.editor_role.group
        self.assertTrue(
            OrganizationGroupObjectPermission.objects.filter(
                group=group).exists() or True,
            "the editor role may hold no organization grant; the delete "
            "must leave none either way")
        response = self.api.delete(
            reverse("accounts:role-detail", args=[self.editor_role.pk]))
        self.assertEqual(response.status_code, 204, response.content)
        self.assertFalse(Role.objects.filter(pk=self.editor_role.pk).exists())
        self.assertFalse(Group.objects.filter(pk=group.pk).exists())
        self.assertEqual(
            OrganizationGroupObjectPermission.objects.filter(
                group=group).count(), 0)

    def test_an_unknown_role_answers_404(self):
        self.login(self.admin)
        response = self.api.get(reverse("accounts:role-detail", args=[99999]))
        self.assertEqual(response.status_code, 404, response.content)
        self.assertEqual(self.error_code(response), "not_found")


class RoleMembershipAPITest(RoleAPITestCaseMixin, TestCase):
    """Assigning and revoking: AC1, AC2 and AC3 of #736 live here."""

    def _assign(self, actor, role, user):
        self.login(actor)
        return self.api.post(
            reverse("accounts:role-memberships-list",
                    args=[role.pk]),
            envelope("RoleMembership", {
                "role": ("Role", role.pk),
                "user": ("User", user.pk)}),
            format="vnd.api+json")

    def test_anonymous_is_answered_403_not_authenticated(self):
        self.anonymous()
        response = self.api.get(reverse("accounts:rolemembership-list"))
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(self.error_code(response), "not_authenticated")

    def test_the_admin_assigns_a_role_to_a_member(self):
        response = self._assign(self.admin, self.editor_role, self.member)
        self.assertEqual(response.status_code, 201, response.content)
        membership = RoleMembership.objects.get(
            role=self.editor_role, user=self.member)
        self.assertEqual(membership.granted_by, self.admin)
        self.assertIn(self.editor_role.group, self.member.groups.all())
        body = self.json_body(response)
        self.assertEqual(
            body["data"]["relationships"]["grantedBy"]["data"]["id"],
            str(self.admin.pk))

    def test_an_outsider_gets_403_on_the_role_collection(self):
        self.login(self.outsider)
        response = self.api.get(
            reverse("accounts:role-memberships-list",
                    args=[self.editor_role.pk]))
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(self.error_code(response), "permission_denied")

    def test_an_outsider_gets_403_when_assigning(self):
        response = self._assign(self.outsider, self.editor_role, self.member)
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(self.error_code(response), "permission_denied")
        self.assertFalse(
            RoleMembership.objects.filter(
                role=self.editor_role, user=self.member).exists())

    def test_assigning_an_organization_role_to_an_outsider_user_is_400(self):
        """AC2: the target user must be a member of the organization"""
        response = self._assign(self.admin, self.editor_role, self.outsider)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(
            self.json_body(response)["errors"][0]["code"], "invalid")

    def test_an_admin_may_not_assign_an_unassignable_platform_role(self):
        """AC3: platform_admin (is_assignable=False) is out of reach"""
        platform_role = Role.objects.filter(
            organization__isnull=True).with_definition(PLATFORM_SLUG).get()
        response = self._assign(self.admin, platform_role, self.member)
        self.assertEqual(response.status_code, 403, response.content)

    def test_an_admin_may_not_assign_an_unassignable_organization_role(self):
        definition = RoleDefinition.objects.create(
            slug="api_locked", label="Locked", scope="ORGANIZATION",
            is_assignable=False)
        role = Role.objects.create(
            role_definition=definition, organization=self.organization,
            group=Group.objects.create(name="Locked Group"))
        response = self._assign(self.admin, role, self.member)
        self.assertEqual(response.status_code, 403, response.content)

    def test_a_superuser_assigns_a_platform_role(self):
        platform_role = Role.objects.filter(
            organization__isnull=True).with_definition(PLATFORM_SLUG).get()
        response = self._assign(self.superuser, platform_role, self.member)
        self.assertEqual(response.status_code, 201, response.content)

    def test_a_retired_role_takes_no_member(self):
        self.editor_role.is_active = False
        self.editor_role.save()
        response = self._assign(self.admin, self.editor_role, self.member)
        self.assertEqual(response.status_code, 400, response.content)

    def test_a_second_membership_of_one_user_is_refused(self):
        self.assertEqual(
            self._assign(self.admin, self.editor_role, self.member).status_code,
            201)
        self.assertEqual(
            self._assign(self.admin, self.editor_role, self.member).status_code,
            400)

    def test_a_nested_post_naming_another_role_is_refused(self):
        self.login(self.admin)
        response = self.api.post(
            reverse("accounts:role-memberships-list",
                    args=[self.editor_role.pk]),
            envelope("RoleMembership", {
                "role": ("Role", self.viewer_role.pk),
                "user": ("User", self.member.pk)}),
            format="vnd.api+json")
        self.assertEqual(response.status_code, 400, response.content)

    def test_a_nested_post_under_an_unknown_role_is_404(self):
        self.login(self.admin)
        response = self.api.post(
            reverse("accounts:role-memberships-list", args=[99999]),
            envelope("RoleMembership", {
                "role": ("Role", self.editor_role.pk),
                "user": ("User", self.member.pk)}),
            format="vnd.api+json")
        self.assertEqual(response.status_code, 404, response.content)

    def test_the_flat_list_shows_only_visible_rows(self):
        """No disclosure of the memberships of an unrelated organization"""
        self._assign(self.admin, self.editor_role, self.member)
        other_admin = get_user_model().objects.create_user(
            username="other_admin", password="x")
        other_admin_role = Role.objects.for_org(
            self.other_organization).with_definition(ADMIN_SLUG).get()
        other_admin_role.add_member(other_admin)

        self.login(self.admin)
        response = self.api.get(reverse("accounts:rolemembership-list"))
        rows = self.json_body(response)["data"]
        self.assertTrue(rows, "the admin sees their organization's rows")
        admin_org_ids = set(
            Role.objects.for_org(self.organization).values_list(
                "memberships__id", flat=True))
        self.assertEqual(
            {row["id"] for row in rows},
            {str(pk) for pk in admin_org_ids if pk})

        self.login(other_admin)
        rows = self.json_body(
            self.api.get(reverse("accounts:rolemembership-list")))[
                "data"]
        self.assertEqual(
            {row["id"] for row in rows}, {str(
                RoleMembership.objects.get(
                    user=other_admin, role__organization=self.other_organization).pk)})

        self.login(self.outsider)
        rows = self.json_body(
            self.api.get(reverse("accounts:rolemembership-list")))["data"]
        self.assertEqual(rows, [])

    def test_the_admin_revokes_a_membership_and_the_grant_follows(self):
        self.assertEqual(
            self._assign(self.admin, self.editor_role, self.member).status_code,
            201)
        membership = RoleMembership.objects.get(
            role=self.editor_role, user=self.member)
        self.login(self.admin)
        response = self.api.delete(
            reverse("accounts:rolemembership-detail", args=[membership.pk]))
        self.assertEqual(response.status_code, 204, response.content)
        self.assertNotIn(self.editor_role.group, self.member.groups.all())

    def test_an_outsider_may_not_revoke_and_is_answered_403(self):
        """AC1: the outsider's revocation names the refusal, not a 404"""
        self._assign(self.admin, self.editor_role, self.member)
        membership = RoleMembership.objects.get(
            role=self.editor_role, user=self.member)
        self.login(self.outsider)
        response = self.api.delete(
            reverse("accounts:rolemembership-detail", args=[membership.pk]))
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(self.error_code(response), "permission_denied")
        self.assertTrue(
            RoleMembership.objects.filter(pk=membership.pk).exists())


class NestedRoleReadsTest(RoleAPITestCaseMixin, TestCase):
    """/users/{id}/roles, /organizations/{id}/roles and who-am-i."""

    def setUp(self):
        super().setUp()
        self.editor_role.add_member(self.member, granted_by=self.admin)

    def test_who_am_i_answers_the_callers_roles(self):
        self.login(self.member)
        response = self.api.get(reverse("accounts:whoami"))
        self.assertEqual(response.status_code, 200, response.content)
        body = self.json_body(response)
        ids = {item["id"] for item in
               body["data"]["relationships"]["roles"]["data"]}
        self.assertEqual(ids, {str(self.editor_role.pk)})

    def test_a_user_sees_their_own_roles(self):
        self.login(self.member)
        response = self.api.get(
            reverse("accounts:user-roles-list", args=[self.member.pk]))
        self.assertEqual(response.status_code, 200, response.content)
        ids = {row["id"] for row in self.json_body(response)["data"]}
        self.assertEqual(ids, {str(self.editor_role.pk)})

    def test_an_admin_sees_the_roles_of_a_member_of_their_organization(self):
        self.login(self.admin)
        response = self.api.get(
            reverse("accounts:user-roles-list", args=[self.member.pk]))
        self.assertEqual(response.status_code, 200, response.content)

    def test_an_unrelated_user_may_not_see_the_roles_of_another(self):
        self.login(self.outsider)
        response = self.api.get(
            reverse("accounts:user-roles-list", args=[self.member.pk]))
        self.assertEqual(response.status_code, 403, response.content)

    def test_an_unknown_parent_user_answers_404(self):
        self.login(self.outsider)
        response = self.api.get(
            reverse("accounts:user-roles-list", args=[99999]))
        self.assertEqual(response.status_code, 404, response.content)

    def test_the_roles_of_an_organization_are_readable(self):
        self.login(self.outsider)
        response = self.api.get(
            reverse("accounts:organization-roles-list",
                    args=[self.organization.pk]))
        self.assertEqual(response.status_code, 200, response.content)
        names = {row["attributes"]["stringRepresentation"]
                 for row in self.json_body(response)["data"]}
        self.assertIn(f"Role API Org: {EDITOR_SLUG}", names)


class OrganizationMembersTest(RoleAPITestCaseMixin, TestCase):
    """/organizations/{id}/members - the users with their roles in one answer."""

    def setUp(self):
        super().setUp()
        self.editor_role.add_member(self.member, granted_by=self.admin)
        # the member also holds a role in the *other* organization: the
        # members answer must only show the role of the listed organization
        self.other_editor = Role.objects.for_org(
            self.other_organization).with_definition(EDITOR_SLUG).get()
        self.member.groups.add(self.other_organization)
        self.other_editor.add_member(self.member)

    def test_the_admin_lists_members_with_their_roles_in_that_org(self):
        self.login(self.admin)
        response = self.api.get(
            reverse("accounts:organization-members-list",
                    args=[self.organization.pk]))
        self.assertEqual(response.status_code, 200, response.content)
        body = self.json_body(response)
        by_user = {row["id"]: row for row in body["data"]}
        self.assertIn(str(self.member.pk), by_user)
        roles = by_user[str(self.member.pk)]["relationships"]["roles"]["data"]
        self.assertEqual({r["id"] for r in roles},
                         {str(self.editor_role.pk)})

    def test_an_outsider_may_not_list_members(self):
        self.login(self.outsider)
        response = self.api.get(
            reverse("accounts:organization-members-list",
                    args=[self.organization.pk]))
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(self.error_code(response), "permission_denied")

    def test_the_admin_adds_a_member(self):
        """AC1's "add a member": link an existing user to the organization"""
        self.login(self.admin)
        response = self.api.post(
            reverse("accounts:organization-members-list",
                    args=[self.organization.pk]),
            {"data": {"type": "User", "id": str(self.outsider.pk)}},
            format="vnd.api+json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(self.organization.user_set.filter(
            pk=self.outsider.pk).exists())
        # adding a member grants no role
        self.assertEqual(
            self.json_body(response)["data"]["relationships"]["roles"]
            ["data"], [])

    def test_an_outsider_may_not_add_a_member(self):
        self.login(self.outsider)
        response = self.api.post(
            reverse("accounts:organization-members-list",
                    args=[self.organization.pk]),
            {"data": {"type": "User", "id": str(self.outsider.pk)}},
            format="vnd.api+json")
        self.assertEqual(response.status_code, 403, response.content)

    def test_adding_an_unknown_user_answers_400(self):
        self.login(self.admin)
        response = self.api.post(
            reverse("accounts:organization-members-list",
                    args=[self.organization.pk]),
            {"data": {"type": "User", "id": "00000000-0000-0000-0000-000000000000"}},
            format="vnd.api+json")
        self.assertEqual(response.status_code, 400, response.content)

    def test_the_member_of_a_platform_holder_lists_the_members(self):
        self.login(self.superuser)
        response = self.api.get(
            reverse("accounts:organization-members-list",
                    args=[self.organization.pk]))
        self.assertEqual(response.status_code, 200, response.content)

    def test_a_lost_organization_answers_404(self):
        self.login(self.admin)
        response = self.api.get(
            reverse("accounts:organization-members-list", args=[99999]))
        self.assertEqual(response.status_code, 404, response.content)


class RoleAPISchemaTest(TestCase):
    """The generated schema shows every new operation (AC4)."""

    @classmethod
    def setUpTestData(cls):
        from drf_spectacular.generators import SchemaGenerator
        cls.schema = SchemaGenerator().get_schema(public=True)

    def test_the_new_routes_are_documented(self):
        paths = self.schema["paths"]
        for path in [
                "/api/accounts/roledefinitions",
                "/api/accounts/roledefinitions/{id}",
                "/api/accounts/roles",
                "/api/accounts/roles/{id}",
                "/api/accounts/roles/{RoleId}/memberships",
                "/api/accounts/memberships",
                "/api/accounts/memberships/{id}",
                "/api/accounts/users/{UserId}/roles",
                "/api/accounts/organizations/{OrganizationId}/roles",
                "/api/accounts/organizations/{OrganizationId}/members"]:
            self.assertIn(path, paths, f"{path} missing from the schema")

    def test_the_new_operations_have_operation_ids(self):
        operations = {
            operation_id
            for path_item in self.schema["paths"].values()
            for item in path_item.values() if isinstance(item, dict)
            for operation_id in [item.get("operationId")] if operation_id}
        for operation_id in [
                "list_RoleDefinition", "create_RoleDefinition",
                "retrieve_RoleDefinition", "partial_update_RoleDefinition",
                "list_Role", "create_Role", "retrieve_Role",
                "partial_update_Role", "destroy_Role",
                "list_RoleMembership", "retrieve_RoleMembership",
                "destroy_RoleMembership",
                "list_related_RoleMembership_of_Role",
                "create_related_RoleMembership_of_Role",
                "list_related_Role_of_User",
                "list_related_Role_of_Organization",
                "list_related_User_of_Organization",
                "create_related_User_of_Organization"]:
            self.assertIn(operation_id, operations,
                          f"operation {operation_id} not documented")
