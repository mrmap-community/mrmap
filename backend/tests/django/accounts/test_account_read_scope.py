"""Who may read an account, and what of it (#1807).

The accounts endpoint guarded its reads with DRF's stock
``DjangoObjectPermissions``, whose ``perms_map`` answers a safe method with
*no* permission at all: ``has_permission`` and ``has_object_permission`` both
reduce to ``user.has_perms([])`` → ``True``. The consequence the issue
measures on a reference stack: every authenticated principal - a ``viewer``, a
``harvester``, the machine account of a harvesting integration - reads the
complete account table, with ``email``, ``isStaff``, ``isSuperuser``,
``lastLogin`` and the confirmation flags, and the detail route of any account
below it. The shipped catalogue names ``accounts.view_user`` for
``platform_admin`` and ``support`` only, two of its nine definitions.

The answers pinned below are the scoped-and-reduced branch of the issue, which
keeps the member picker of #737 working:

* the collection and the detail answer the accounts of the organizations the
  caller belongs to or administers - never another organization's people;
* of those accounts the caller sees what a picker renders
  (``username``, ``stringRepresentation``); ``email``, ``isSuperuser``,
  ``lastLogin``, ``dateJoined``, ``settings`` and the confirmation flags answer
  the reader of ``accounts.view_user`` and the account itself;
* an account outside that scope answers 404, the shape which does not confirm
  that it exists (#1319).

The same hole sat on the members relation of ``/api/accounts/groups``: a
role group is named ``"<organization>: <role>"`` and its ``users`` relation
names the accounts behind it, which is the payload #727's Q3 and
``RoleMembershipAccessPermission`` put behind the organization - and which
``/roles/{id}/memberships`` and ``/users/{id}/roles`` refuse. The names of the
groups stay readable, as #1448 pinned them; the members do not.

The actors are production-shaped: an organization administrator holds the
``organization_admin`` role of #732, the platform holder the platform-scope
``platform_admin``, and nobody here is handed a global permission by hand.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from accounts.models.roles import Role, RoleDefinition, RoleScope
from accounts.models.users import User
from tests.django.accounts.test_roles_api import (PLATFORM_SLUG,
                                                  RoleAPITestCaseMixin,
                                                  VIEWER_SLUG)

JSONAPI = "application/vnd.api+json"

#: the attributes a member picker needs and therefore everybody authenticated
#: may read of a person (#1035), as the renderer names them
PICKER_ATTRIBUTES = {"username", "stringRepresentation"}

#: the same answer before the renderer: the keys of a serializer are python
#: names, the api's camel case arrives with the JSON:API renderer
PICKER_SERIALIZER_FIELDS = {"username", "string_representation"}

#: the attributes the issue names as reserved for ``accounts.view_user``, as
#: the renderer names them
PRIVATE_ATTRIBUTES = {"email", "firstName", "lastName", "isStaff",
                      "isSuperuser", "lastLogin", "dateJoined",
                      "confirmedDsgvo", "confirmedNewsletter",
                      "confirmedSurvey", "settings"}

#: the same set before the renderer, for the assertions on a serializer
PRIVATE_SERIALIZER_FIELDS = {"email", "first_name", "last_name", "is_staff",
                             "is_superuser", "last_login", "date_joined",
                             "confirmed_newsletter", "confirmed_survey",
                             "confirmed_dsgvo", "settings"}


class AccountReadScopeTest(RoleAPITestCaseMixin, TestCase):
    """``GET /api/accounts/users`` answers colleagues, never other people."""

    def setUp(self):
        super().setUp()
        get_user_model().objects.get_or_create(username="AnonymousUser")
        # the caller is a plain member of the organization: the ``viewer``
        # role of the catalogue, which holds no ``accounts.view_user``
        self.viewer_role.add_member(self.member)
        # the fixture ships its users without an address; the read of a person
        # is the point, so the row the tests assert on has one
        self.member.email = "user2@example.com"
        self.member.save()
        # a person of the *other* organization: the account every outsider has
        # to be refused, with its address
        self.foreign = get_user_model().objects.create_user(
            username="foreign", email="foreign@other.example")
        self.foreign.groups.add(self.other_organization)
        self.other_editor_role = Role.objects.for_org(
            self.other_organization).with_definition(VIEWER_SLUG).get()
        self.other_editor_role.add_member(self.foreign)
        self.foreign.set_password("x")
        self.foreign.save()

    def _rows(self, response):
        return {row["id"]: row for row in
                self.json_body(response)["data"]}

    def _attributes(self, response, user):
        rows = self._rows(response)
        self.assertIn(str(user.pk), rows, sorted(rows))
        return rows[str(user.pk)]["attributes"]

    def test_anonymous_may_not_read_the_accounts(self):
        self.anonymous()
        response = self.api.get(reverse("accounts:user-list"))
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(self.error_code(response), "not_authenticated")

    def test_a_member_reads_the_accounts_of_its_own_organization(self):
        self.login(self.member)
        response = self.api.get(reverse("accounts:user-list"))
        self.assertEqual(response.status_code, 200, response.content)
        ids = set(self._rows(response))
        self.assertIn(str(self.member.pk), ids)
        self.assertIn(str(self.admin.pk), ids)

    def test_a_member_does_not_read_an_account_of_another_organization(
            self):
        """The measurement of the issue: 24 of 24 rows, a foreign one included."""
        self.login(self.member)
        response = self.api.get(reverse("accounts:user-list"))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertNotIn(str(self.foreign.pk), self._rows(response))
        # the refusal holds against the filters and the search too - scoping
        # the queryset, not hiding a page of it
        self.login(self.member)
        response = self.api.get(
            reverse("accounts:user-list"),
            {"filter[id]": str(self.foreign.pk)})
        self.assertEqual(self._rows(response), {})
        self.login(self.member)
        response = self.api.get(
            reverse("accounts:user-list"),
            {"filter[search]": "foreign"})
        self.assertEqual(self._rows(response), {})

    def test_an_outsider_reads_no_account_but_its_own(self):
        self.login(self.outsider)
        response = self.api.get(reverse("accounts:user-list"))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(set(self._rows(response)), {str(self.outsider.pk)})

    def test_the_list_answers_a_colleague_the_picker_fields_only(self):
        self.login(self.member)
        response = self.api.get(reverse("accounts:user-list"))
        attributes = self._attributes(response, self.admin)
        self.assertTrue(PICKER_ATTRIBUTES <= set(attributes), attributes)
        self.assertFalse(PRIVATE_ATTRIBUTES & set(attributes), attributes)

    def test_a_colleague_answers_the_picker_fields_only(self):
        self.login(self.member)
        response = self.api.get(
            reverse("accounts:user-detail", args=[self.admin.pk]))
        self.assertEqual(response.status_code, 200, response.content)
        attributes = self.json_body(response)["data"]["attributes"]
        self.assertTrue(PICKER_ATTRIBUTES <= set(attributes), attributes)
        self.assertFalse(PRIVATE_ATTRIBUTES & set(attributes), attributes)

    def test_the_detail_of_an_unrelated_account_answers_404(self):
        """Not 403: a refusal would confirm the account exists (#1319)."""
        self.login(self.outsider)
        response = self.api.get(
            reverse("accounts:user-detail", args=[self.foreign.pk]))
        self.assertEqual(response.status_code, 404, response.content)

    def test_an_account_reads_itself_with_the_full_answer(self):
        """``who-am-i`` and the client's own cache stay truthful (#833)."""
        self.login(self.member)
        response = self.api.get(
            reverse("accounts:user-detail", args=[self.member.pk]))
        self.assertEqual(response.status_code, 200, response.content)
        attributes = self.json_body(response)["data"]["attributes"]
        self.assertEqual(attributes["email"], "user2@example.com")
        self.assertIn("lastLogin", attributes)
        self.assertIn("isSuperuser", attributes)

    def test_who_am_i_still_answers_the_full_row(self):
        self.login(self.member)
        response = self.api.get(reverse("accounts:whoami"))
        self.assertEqual(response.status_code, 200, response.content)
        body = self.json_body(response)["data"]
        self.assertEqual(body["attributes"]["email"], "user2@example.com")
        self.assertIn({"type": "Role", "id": str(self.viewer_role.pk)},
                      body["relationships"]["roles"]["data"])

    def test_the_platform_holder_reads_every_account_with_its_fields(self):
        """The two definitions the catalogue names do get the read (#1807)."""
        platform_role = Role.objects.filter(
            organization__isnull=True).with_definition(PLATFORM_SLUG).get()
        platform_role.add_member(self.outsider)
        self.login(self.outsider)
        response = self.api.get(reverse("accounts:user-list"))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn(str(self.foreign.pk), self._rows(response))
        attributes = self._attributes(response, self.foreign)
        self.assertEqual(attributes["email"], "foreign@other.example")

    def test_the_break_glass_reads_every_account_with_its_fields(self):
        self.login(self.superuser)
        response = self.api.get(reverse("accounts:user-list"))
        self.assertEqual(response.status_code, 200, response.content)
        attributes = self._attributes(response, self.foreign)
        self.assertEqual(attributes["email"], "foreign@other.example")

    def test_a_colleague_may_not_read_which_groups_an_account_is_in(self):
        """The relation states which roles a person holds - the Q3 payload."""
        self.login(self.member)
        response = self.api.get(
            reverse("accounts:user-detail", args=[self.foreign.pk]))
        self.assertEqual(response.status_code, 404, response.content)
        response = self.api.get(
            reverse("accounts:user-groups-list", args=[self.foreign.pk]))
        self.assertEqual(response.status_code, 403, response.content)

    def test_an_account_reads_its_own_groups(self):
        self.login(self.member)
        response = self.api.get(
            reverse("accounts:user-groups-list", args=[self.member.pk]))
        self.assertEqual(response.status_code, 200, response.content)
        names = {row["attributes"]["name"]
                 for row in self.json_body(response)["data"]}
        self.assertIn(self.organization.name, names)

    def test_a_superuser_may_still_create_an_account(self):
        """The write half of #1448/#1451 is untouched by the read guard."""
        self.login(self.superuser)
        response = self.api.post(
            reverse("accounts:user-list"),
            {"data": {"type": "User", "attributes": {
                "username": "written", "password": "Kr4ft-V0ll-Text-P4ssw0rt"},
                "relationships": {"groups": {"data": []}}}},
            format="vnd.api+json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(User.objects.filter(username="written").exists())

    def test_a_member_may_not_write_an_account_it_can_read(self):
        self.login(self.member)
        response = self.api.patch(
            reverse("accounts:user-detail", args=[self.admin.pk]),
            {"data": {"type": "User", "id": str(self.admin.pk),
                      "attributes": {"firstName": "Hijacked"}}},
            format="vnd.api+json")
        self.assertEqual(response.status_code, 403, response.content)
        self.admin.refresh_from_db()
        self.assertNotEqual(self.admin.first_name, "Hijacked")


class GroupMembersReadScopeTest(RoleAPITestCaseMixin, TestCase):
    """The members relation of a group is the membership it names (#1807)."""

    def setUp(self):
        super().setUp()
        get_user_model().objects.get_or_create(username="AnonymousUser")
        self.editor_role.add_member(self.member)
        self.member.email = "user2@example.com"
        self.member.save()
        # the group of a role of the *other* organization: name and members
        # together spell out who holds which role where
        self.foreign_editor_role = Role.objects.for_org(
            self.other_organization).with_definition(VIEWER_SLUG).get()
        self.foreign_editor_role.add_member(self.foreign_member())

    def foreign_member(self):
        if not hasattr(self, "_foreign_member"):
            self._foreign_member = get_user_model().objects.create_user(
                username="south", email="south@other.example")
            self._foreign_member.groups.add(self.other_organization)
        return self._foreign_member

    def test_anonymous_may_not_read_the_groups(self):
        self.anonymous()
        response = self.api.get(reverse("accounts:group-list"))
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(self.error_code(response), "not_authenticated")

    def test_the_name_of_a_foreign_group_stays_readable(self):
        """#1448 pinned the collection as the open part; #1807 keeps that."""
        self.login(self.outsider)
        response = self.api.get(
            reverse("accounts:group-list"),
            {"filter[id]": self.other_organization.pk})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            [row["attributes"]["name"]
             for row in self.json_body(response)["data"]],
            [self.other_organization.name])

    def test_the_members_of_a_foreign_role_group_answer_no_accounts(self):
        """The canary of the issue: the relation used to name every member."""
        self.login(self.outsider)
        response = self.api.get(
            reverse("accounts:group-detail",
                    args=[self.foreign_editor_role.group_id]))
        self.assertEqual(response.status_code, 200, response.content)
        data = self.json_body(response)["data"]
        self.assertEqual(data["relationships"]["users"]["data"], [])
        self.assertNotIn(
            str(self.foreign_member().pk),
            str(data["relationships"]["users"]))

    def test_a_member_of_the_organization_reads_the_members_of_its_roles(
            self):
        self.login(self.member)
        response = self.api.get(
            reverse("accounts:group-detail", args=[self.editor_role.group_id]))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn({"type": "User", "id": str(self.member.pk)},
                      self.json_body(response)["data"]["relationships"]
                      ["users"]["data"])

    def test_an_administrator_reads_the_members_of_its_organizations_groups(
            self):
        self.login(self.admin)
        response = self.api.get(
            reverse("accounts:group-detail", args=[self.editor_role.group_id]))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn({"type": "User", "id": str(self.member.pk)},
                      self.json_body(response)["data"]["relationships"]
                      ["users"]["data"])

    def test_the_platform_holder_reads_the_members_of_any_group(self):
        platform_role = Role.objects.filter(
            organization__isnull=True).with_definition(PLATFORM_SLUG).get()
        platform_role.add_member(self.outsider)
        self.login(self.outsider)
        response = self.api.get(
            reverse("accounts:group-detail",
                    args=[self.foreign_editor_role.group_id]))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn({"type": "User", "id": str(self.foreign_member().pk)},
                      self.json_body(response)["data"]["relationships"]
                      ["users"]["data"])

    def test_the_catalogue_decides_a_platform_wide_group_read(self):
        """``auth.view_group`` is named by nobody - adding it opens the read.

        The platform-scope answer: a definition of the ``PLATFORM`` scope
        which names the right opens the read over every organization, the way
        ``accounts.view_user`` does for the accounts.
        """
        definition = RoleDefinition.objects.create(
            slug="group_auditor", label="Group auditor",
            scope=RoleScope.PLATFORM)
        definition.permissions.add(
            Permission.objects.get_by_natural_key(
                "view_group", "auth", "group"))
        auditor = Role.objects.create(
            role_definition=definition, organization=None,
            group=Group.objects.create(name="Platform: group_auditor"))
        auditor.add_member(self.member)
        self.login(self.member)
        response = self.api.get(
            reverse("accounts:group-detail",
                    args=[self.foreign_editor_role.group_id]))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn({"type": "User", "id": str(self.foreign_member().pk)},
                      self.json_body(response)["data"]["relationships"]
                      ["users"]["data"])

    def test_the_writes_of_the_relation_stay_refused(self):
        """The write half of #1448 is untouched by the read guard."""
        self.login(self.admin)
        before = set(self.foreign_editor_role.group.user_set.values_list(
            "pk", flat=True))
        response = self.api.patch(
            reverse("accounts:group-detail",
                    args=[self.foreign_editor_role.group_id]),
            {"data": {"type": "Group",
                      "id": str(self.foreign_editor_role.group_id),
                      "relationships": {"users": {"data": [
                          {"type": "User", "id": str(self.admin.pk)}]}}}},
            format="vnd.api+json")
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(set(self.foreign_editor_role.group.user_set
                             .values_list("pk", flat=True)), before)


class EmbeddedAccountReadScopeTest(RoleAPITestCaseMixin, TestCase):
    """An account which answers *through another resource* stays reduced.

    ``createdBy`` and ``lastModifiedBy`` of #738, ``historyUser`` of the
    changelogs of #741 and the members of an organization embed the same
    serializer; the guard of the users viewset never sees those answers, so
    the serializer is where the field surface is decided (#1807).
    """

    def setUp(self):
        super().setUp()
        get_user_model().objects.get_or_create(username="AnonymousUser")
        self.editor_role.add_member(self.member)
        self.member.email = "user2@example.com"
        self.member.save()

    def test_the_members_of_an_organization_answer_no_addresses(self):
        self.login(self.admin)
        response = self.api.get(
            reverse("accounts:organization-members-list",
                    args=[self.organization.pk]))
        self.assertEqual(response.status_code, 200, response.content)
        rows = {row["id"]: row for row in self.json_body(response)["data"]}
        attributes = rows[str(self.member.pk)]["attributes"]
        self.assertTrue(PICKER_ATTRIBUTES <= set(attributes), attributes)
        self.assertFalse(PRIVATE_ATTRIBUTES & set(attributes), attributes)
        # the roles of the member stay answered - that is the answer of #736
        self.assertIn({"type": "Role", "id": str(self.editor_role.pk)},
                      rows[str(self.member.pk)]["relationships"]["roles"]
                      ["data"])

    def test_the_administrator_adding_a_member_reads_the_person_it_searches(
            self):
        """The "add a member" search of #737 must not answer 403 on the picker.

        The dialog searches the platform's own collection for a person who is
        not a member anywhere yet - an account in no organization is nobody's
        organization's people - and renders and submits only what the picker
        answers.
        """
        self.login(self.admin)
        response = self.api.get(
            reverse("accounts:user-list"), {"filter[search]": "outsider"})
        self.assertEqual(response.status_code, 200, response.content)
        rows = {row["id"]: row for row in self.json_body(response)["data"]}
        self.assertIn(str(self.outsider.pk), rows)
        attributes = rows[str(self.outsider.pk)]["attributes"]
        self.assertIn("username", attributes)
        self.assertFalse(PRIVATE_ATTRIBUTES & set(attributes), attributes)

    def test_a_serializer_without_a_caller_answers_the_model(self):
        """No caller to judge: a shell or a schema run keeps the whole answer."""
        from accounts.serializers.users import UserSerializer

        serializer = UserSerializer(self.member)
        serializer.fields.pop("url")          # needs a request to reverse
        data = serializer.data
        self.assertEqual(data["email"], "user2@example.com")
        self.assertIn("is_superuser", data)

    def test_the_embedded_answer_of_an_unrelated_caller_is_the_picker(self):
        """What ``createdBy`` of #738 answers to a stranger of the service."""
        from rest_framework.test import APIRequestFactory

        from accounts.serializers.users import UserSerializer

        request = APIRequestFactory().get("/")
        request.user = self.outsider
        serializer = UserSerializer(self.member, context={"request": request})
        serializer.fields.pop("url")
        data = serializer.data
        self.assertTrue(PICKER_SERIALIZER_FIELDS <= set(data), data)
        self.assertFalse(PRIVATE_SERIALIZER_FIELDS & set(data), data)
        self.assertEqual(list(data["roles"]), [])
        self.assertEqual(list(data["groups"]), [])


class AccountReadScopeRegressionTest(TestCase):
    """The old answer, pinned so this file fails if the guard is loosened."""

    def setUp(self):
        self.api = self._api()
        self.member = get_user_model().objects.create_user(
            username="member", email="member@example.com")
        self.other = get_user_model().objects.create_user(
            username="other", email="other@example.com", is_staff=True)
        Group.objects.create(name="unrelated group").user_set.add(self.other)

    def _api(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.credentials(HTTP_ACCEPT=JSONAPI)
        return client

    def test_a_session_without_any_organization_reads_no_foreign_account(self):
        self.api.force_authenticate(self.member)
        response = self.api.get(reverse("accounts:user-list"))
        self.assertEqual(response.status_code, 200, response.content)
        ids = {row["id"] for row in response.json()["data"]}
        self.assertEqual(ids, {str(self.member.pk)})
        self.assertNotIn("other@example.com", response.content.decode())

    def test_a_session_without_any_organization_reads_no_group_members(self):
        self.api.force_authenticate(self.member)
        group = Group.objects.get(name="unrelated group")
        response = self.api.get(
            reverse("accounts:group-detail", args=[group.pk]))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response.json()["data"]["relationships"]["users"]["data"], [])
        self.assertNotIn(str(self.other.pk), response.content.decode())
