"""Who may read a group, and who may write a membership (#1448).

``GroupViewSet`` and ``OrganizationViewSet`` were plain ``ModelViewSet``s with
no permission class of their own, and ``GroupSerializer.users`` was a
*writable* to-many relation. Object permissions are granted to the role groups
of the organizations (#732), so the membership of a group is the grant of
whatever that group holds: adding oneself to the role group of another
organization makes one whoever that role may act for, and an ``Organization``
*is* its ``Group`` row, so the same write against
``/api/accounts/groups/{organization id}`` joined any organization. The
endpoint answered that write without asking who the caller was.

Both viewsets now name ``DjangoObjectPermissions``, the class the users
endpoint already names (`accounts/views/users.py`): reading needs an identity,
writing is asked twice - the global model permission and the same codename on
the object. Role groups only ever hold object grants, so no member of an
organization writes a group through this endpoint; that is the boundary
#727 Q7 drew, and the sanctioned way to change a membership is
``POST /organizations/{id}/members`` of #736, which asks exactly one
organization and fails closed. The tests below walk both sides of that.

The relation stays *answerable*: it is what the group screens read, so the
answer keeps the members and the write drops them. Reading a page of groups
used to ask the members of every row of the page one more time, which the
read plan test measures on the through table of the relation.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from accounts.models.roles import Role
from accounts.models.users import User
from tests.django.accounts.test_roles_api import (EDITOR_SLUG,
                                                  RoleAPITestCaseMixin,
                                                  envelope)
from tests.django.utils import QueryPlanMixin

#: the table of the members relation the group serializer answers: the through
#: table of ``User.groups``, named by every statement which reads it
MEMBERSHIP_TABLE = User._meta.get_field("groups").m2m_db_table()

JSONAPI = "application/vnd.api+json"


def members_document(group, pks, attributes=None):
    """A JSON:API document writing the to-many members relation of ``group``.

    The shape the escalation of #1448 was written with, and the shape a client
    of before #736 still sends. ``envelope`` of ``test_roles_api`` answers
    to-one relations only, so the to-many document is built here.
    """
    data = {
        "type": "Group",
        "id": str(group.pk),
        "relationships": {
            "users": {"data": [
                {"type": "User", "id": str(pk)} for pk in pks]}}}
    if attributes:
        data["attributes"] = attributes
    return {"data": data}


class GroupAccessTest(RoleAPITestCaseMixin, TestCase):
    """The groups endpoint: readable with an identity, never writable blindly."""

    def setUp(self):
        super().setUp()
        # guardian maps an anonymous request to the user named AnonymousUser;
        # a TransactionTestCase run earlier in the process flushed the row
        # post_migrate created (see tests/AGENTS.md)
        get_user_model().objects.get_or_create(username="AnonymousUser")
        # the role group of *another* organization: the group whose object
        # grants are the prize of the escalation #1448 is about
        self.other_editor_role = Role.objects.for_org(
            self.other_organization).with_definition(EDITOR_SLUG).get()

    def _members_of_the_role_group(self):
        return set(self.other_editor_role.group.user_set.values_list(
            "pk", flat=True))

    def test_anonymous_may_not_read_the_groups(self):
        self.anonymous()
        response = self.api.get(reverse("accounts:group-list"))
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(self.error_code(response), "not_authenticated")

    def test_anonymous_may_not_create_a_group(self):
        self.anonymous()
        response = self.api.post(
            reverse("accounts:group-list"),
            envelope("Group", {}, {"name": "Anonymous Group"}),
            format="vnd.api+json")
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(self.error_code(response), "not_authenticated")
        self.assertFalse(Group.objects.filter(name="Anonymous Group").exists())

    def test_an_anonymous_relationship_patch_adds_no_member(self):
        """The regression #1448 asks for: no identity, no membership.

        Before the permission class this document was answered: the relation
        was writable and the viewset asked nobody.
        """
        self.anonymous()
        before = self._members_of_the_role_group()
        response = self.api.patch(
            reverse("accounts:group-detail",
                    args=[self.other_editor_role.group_id]),
            members_document(self.other_editor_role.group, [self.member.pk]),
            format="vnd.api+json")
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(self.error_code(response), "not_authenticated")
        self.assertEqual(self._members_of_the_role_group(), before)

    def test_a_member_of_another_organization_adds_no_member(self):
        """The same document by an account which is somebody, but not here.

        The caller administers *an* organization, which is no say in another
        one's role group (#727's Q3): the role groups hold object grants only,
        so the global model permission ``has_permission`` asks for is missing.
        """
        self.login(self.admin)
        before = self._members_of_the_role_group()
        response = self.api.patch(
            reverse("accounts:group-detail",
                    args=[self.other_editor_role.group_id]),
            members_document(self.other_editor_role.group, [self.admin.pk]),
            format="vnd.api+json")
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(self.error_code(response), "permission_denied")
        self.assertEqual(self._members_of_the_role_group(), before)

    def test_joining_an_organization_over_the_groups_endpoint_is_refused(self):
        """An ``Organization`` *is* its ``Group`` row, so its id answers here.

        Writing the members of that group is joining the organization, which
        is what ``POST /organizations/{id}/members`` of #736 does under the
        administration check of that organization.
        """
        self.login(self.outsider)
        before = set(self.other_organization.user_set.values_list(
            "pk", flat=True))
        response = self.api.patch(
            reverse("accounts:group-detail", args=[self.other_organization.pk]),
            members_document(self.other_organization, [self.outsider.pk]),
            format="vnd.api+json")
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(self.error_code(response), "permission_denied")
        self.assertEqual(set(self.other_organization.user_set.values_list(
            "pk", flat=True)), before)

    def test_any_authenticated_user_reads_the_groups(self):
        """Reading stays the open part: the screens of #737 list these rows."""
        self.login(self.outsider)
        response = self.api.get(
            reverse("accounts:group-list"),
            {"filter[id]": self.other_organization.pk})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            [row["attributes"]["name"]
             for row in self.json_body(response)["data"]],
            [self.other_organization.name])

    def test_the_answer_carries_the_members_relation(self):
        """Read-only is not removed: the relation is still answered."""
        self.login(self.member)
        response = self.api.get(
            reverse("accounts:group-detail", args=[self.admin_role.group_id]))
        self.assertEqual(response.status_code, 200, response.content)
        members = self.json_body(response)["data"]["relationships"]["users"][
            "data"]
        self.assertIn({"type": "User", "id": str(self.admin.pk)}, members)

    def test_the_members_of_the_relation_are_not_written_by_a_superuser(self):
        """The relation is read-only, so even the break-glass account ignores it.

        A write which is silently dropped is the point: the sanctioned member
        endpoint is the only way in, and a client holding the members document
        of an older deployment changes nothing by accident.
        """
        self.login(self.superuser)
        before = self._members_of_the_role_group()
        group = self.other_editor_role.group
        response = self.api.patch(
            reverse("accounts:group-detail", args=[group.pk]),
            members_document(group, [self.outsider.pk],
                             {"name": "Renamed by root"}),
            format="vnd.api+json")
        self.assertEqual(response.status_code, 200, response.content)
        group.refresh_from_db()
        self.assertEqual(group.name, "Renamed by root")
        self.assertEqual(self._members_of_the_role_group(), before)

    def test_the_sanctioned_membership_write_still_works(self):
        """Closing the relation leaves the way in open: #736's POST adds."""
        self.login(self.admin)
        response = self.api.post(
            reverse("accounts:organization-members-list",
                    args=[self.organization.pk]),
            {"data": {"type": "User", "id": str(self.outsider.pk)}},
            format="vnd.api+json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(self.organization.user_set.filter(
            pk=self.outsider.pk).exists())


class OrganizationAccessTest(RoleAPITestCaseMixin, TestCase):
    """The organizations endpoint: the contact fields of a person are no lookup."""

    def setUp(self):
        super().setUp()
        get_user_model().objects.get_or_create(username="AnonymousUser")
        self.other_organization.person_name = "Ada Lovelace"
        self.other_organization.email = "ada@lovelace.example"
        self.other_organization.save()

    def test_anonymous_may_not_read_the_organizations(self):
        self.anonymous()
        response = self.api.get(reverse("accounts:organization-list"))
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(self.error_code(response), "not_authenticated")

    def test_anonymous_may_not_write_an_organization(self):
        """The serializer answers ``fields = "__all__"`` over the contact model."""
        self.anonymous()
        response = self.api.patch(
            reverse("accounts:organization-detail",
                    args=[self.other_organization.pk]),
            envelope("Organization", {},
                     {"personName": "Hijacked",
                      "email": "attacker@example.org"},
                     resource_id=self.other_organization.pk),
            format="vnd.api+json")
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(self.error_code(response), "not_authenticated")
        self.other_organization.refresh_from_db()
        self.assertEqual(self.other_organization.person_name, "Ada Lovelace")

    def test_an_authenticated_outsider_is_answered_the_rows_it_always_was(
            self):
        """The narrowing of the contact fields is a product decision, not this one.

        #1448 closes the anonymous read and every blind write; which fields of
        an organization the screens of the frontend need stays open there,
        because the pickers render them. So an authenticated caller of another
        organization still gets the row - the list is not narrowed by
        visibility, which is the rollout switch of #739 - and the change of a
        contact field is what this issue takes away from it.
        """
        self.login(self.member)
        response = self.api.get(
            reverse("accounts:organization-detail",
                    args=[self.other_organization.pk]))
        self.assertEqual(response.status_code, 200, response.content)
        attributes = self.json_body(response)["data"]["attributes"]
        self.assertEqual(attributes["personName"], "Ada Lovelace")

    def test_a_member_of_another_organization_may_not_change_it(self):
        self.login(self.admin)
        response = self.api.patch(
            reverse("accounts:organization-detail",
                    args=[self.other_organization.pk]),
            envelope("Organization", {},
                     {"email": "attacker@example.org"},
                     resource_id=self.other_organization.pk),
            format="vnd.api+json")
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(self.error_code(response), "permission_denied")
        self.other_organization.refresh_from_db()
        self.assertEqual(self.other_organization.email, "ada@lovelace.example")

    def test_the_administrated_organization_is_not_writable_over_either_axis(
            self):
        """The administrator of an organization holds its *object* grant only.

        ``DjangoObjectPermissions`` asks the global model permission first and
        the object grant after, and #727 rules the global one out for a role
        definition - writing the name and the contact of an organization
        therefore stays with the break-glass account, while administering it
        (its members, its roles, its access rules) is what the object grant
        answers. This is the same answer the users endpoint gives for a user.
        """
        self.login(self.admin)
        response = self.api.patch(
            reverse("accounts:organization-detail",
                    args=[self.organization.pk]),
            envelope("Organization", {}, {"name": "Renamed by its admin"},
                     resource_id=self.organization.pk),
            format="vnd.api+json")
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(self.error_code(response), "permission_denied")
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.name, "Role API Org")


class GroupListReadPlanTest(RoleAPITestCaseMixin, QueryPlanMixin, TestCase):
    """The members of a page of groups are read once, not once per row (#1448)."""

    def setUp(self):
        super().setUp()
        self.groups = []
        for name in ("Read Plan A", "Read Plan B", "Read Plan C"):
            group = Group.objects.create(name=name)
            group.user_set.add(self.member, self.admin)
            self.groups.append(group)
        self.login(self.member)
        # one unmeasured request: whatever a first request of a session caches
        # (the permission caches of Django and DRF) is primed for both
        # measurements below, so only the statements of the answer are counted
        self.assertEqual(self._page().status_code, 200)

    def _page(self, **params):
        ids = ",".join(str(group.pk) for group in self.groups)
        return self.api.get(
            reverse("accounts:group-list"),
            {"filter[id__in]": ids, **params},
            HTTP_ACCEPT=JSONAPI)

    def _rows_and_membership_statements(self, **params):
        """The rows of the answer and the statements which read the relation."""
        response, sqls = self.measure(self._page, **params)
        self.assertEqual(response.status_code, 200, response.content)
        return (response.json()["data"],
                [sql for sql in sqls if MEMBERSHIP_TABLE in sql])

    def test_the_membership_table_is_read_once_whatever_the_rows_of_the_page(
            self):
        one, one_sqls = self._rows_and_membership_statements(
            **{"page[size]": 1})
        page, page_sqls = self._rows_and_membership_statements()
        # the second answer really carries more groups, so the comparison
        # measures a page of rows against a page of one
        self.assertGreater(len(page), len(one))
        self.assertEqual(
            len(one_sqls), len(page_sqls),
            "the members of the groups are read per row: %s" % page_sqls)
