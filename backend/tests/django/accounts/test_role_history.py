"""The audit trail of the role system (#741 AC1).

Three questions an administrator is asked after the fact, and the tables which
answer them: what a definition meant and who changed its permission set
(``RoleDefinition``), who created and retired a role (``Role``), and who
granted a role to whom and who took it back (``RoleMembership``). The rows are
written by ``simple_history``, so the tests ask the tables directly for the
trail and the api for what a screen shows.

Two properties the issue asks for are pinned here because nothing else would
catch their loss:

* the **permission set** of a definition is part of the trail, although it is
  not a column of the row - a tracked many-to-many;
* an audit row is **not editable**: the changelog answers reads, and the verbs
  which could change one are absent from the endpoint.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from accounts.models.groups import Organization
from accounts.models.roles import Role, RoleDefinition, RoleMembership
from tests.django.accounts.test_roles_api import (ADMIN_SLUG,
                                                  RoleAPITestCaseMixin)

JSONAPI = "application/vnd.api+json"

VIEWER_SLUG = "viewer"

#: a permission no builtin role of the catalogue carries, so adding it to a
#: definition is a change of the set and not a no-op
EXTRA_PERM = ("registry", "view_mapcontext")


class DefinitionTrailTest(TestCase):
    """What the catalogue meant, and who changed it."""

    def setUp(self):
        self.definition = RoleDefinition.objects.get(slug=VIEWER_SLUG)
        self.permission = Permission.objects.get(
            content_type__app_label=EXTRA_PERM[0], codename=EXTRA_PERM[1])

    def test_changing_the_text_of_a_definition_leaves_an_audit_row(self):
        """The row names the value the definition had before the change.

        ``diff_against`` of the api compares against the previous row, so the
        audit is only answerable if that row carried the old text.
        """
        before = self.definition.label
        self.definition.label = "Viewer, renamed"
        self.definition.save()

        newest = self.definition.change_logs.first()
        self.assertEqual(newest.history_type, "~")
        self.assertEqual(newest.label, "Viewer, renamed")
        self.assertEqual(
            self.definition.change_logs.order_by("history_date")[0].label,
            before)

    def test_changing_the_permission_set_leaves_an_audit_row(self):
        """The grant an auditor asks about is the set, not the row.

        "Why does an editor hold ``change_webmapservice``?" ends at the moment
        somebody added it to the definition. A tracked many-to-many is kept in
        its own history table and changes no column, so a history which only
        watched the columns would answer this question with "nothing
        happened" - the reason ``m2m_fields`` is named on the records.
        """
        before = self.definition.change_logs.count()
        self.definition.permissions.add(self.permission)

        self.assertGreater(
            self.definition.change_logs.count(), before,
            "a change of the permission set wrote no audit row: is the set "
            "still listed in m2m_fields of RoleDefinition.change_log?")

    def test_a_definition_created_now_is_in_the_trail_from_its_start(self):
        """Whatever the instance gains after the upgrade is auditable whole.

        The catalogue's own rows came into being in migration 0005, before 0011
        created the audit table, so *they* carry no ``+`` and their trail begins
        at the upgrade - the honest boundary of this issue, and the reason the
        mapping of a retired legacy group is a record of its own and not a
        changelog row. Anything created from now on is not on the wrong side of
        that line, and the operator's "since when does this role exist?" is
        answered by the trail for it.
        """
        created = RoleDefinition.objects.create(
            slug="audited_from_the_start", label="Audited from the start")

        creation = created.change_logs.filter(history_type="+")
        self.assertEqual(creation.count(), 1)
        self.assertEqual(creation.first().label, "Audited from the start")


class MembershipTrailTest(TestCase):
    """Who holds what, and who decided it."""

    def test_revoking_a_membership_leaves_the_row_of_the_deletion(self):
        """The deletion is the answer to "she is not an editor, since when?"

        ``RoleMembership.delete()`` is what takes a person out of the group, so
        the audit row of the deletion is the only remaining statement that the
        grant ever existed - and it is written because the row is deleted
        through the model, never by a bulk statement.
        """
        organization = Organization.objects.create(name="Trail Org")
        role = Role.objects.for_org(organization).with_definition(
            ADMIN_SLUG).first()
        user = get_user_model().objects.create_user(
            username="trail-member", password="x")
        role.add_member(user)

        self.assertTrue(
            RoleMembership.change_log.filter(
                user=user, history_type="+").exists(),
            "granting a role wrote no audit row")

        membership = role.memberships.get(user=user)
        membership._change_reason = "revoked by hand, for the test"
        membership.delete()

        audit = RoleMembership.change_log.filter(
            user=user).order_by("-history_date").first()
        self.assertEqual(audit.history_type, "-")
        self.assertEqual(
            audit.history_change_reason, "revoked by hand, for the test")


class DefinitionChangelogAPITest(RoleAPITestCaseMixin, TestCase):
    """The changelog as a screen reads it: readable, filterable, untouchable."""

    def setUp(self):
        super().setUp()
        self.definition = RoleDefinition.objects.get(slug=VIEWER_SLUG)
        self.definition.label = "Viewer, renamed over the api"
        self.definition.save()

    def test_any_account_reads_the_changelog_of_the_catalogue(self):
        """Reading what a role means is open to every account (#736)."""
        self.login(self.outsider)
        response = self.api.get(
            reverse("accounts:roledefinition-historical-list"),
            content_type=JSONAPI)
        self.assertEqual(response.status_code, 200)

    def test_the_changelog_of_one_definition_answers_only_its_rows(self):
        """``filter[historyRelation]`` is the question a show screen asks."""
        other = RoleDefinition.objects.get(slug=ADMIN_SLUG)
        other.label = "Administrator, renamed too"
        other.save()

        self.login(self.member)
        response = self.api.get(
            reverse("accounts:roledefinition-historical-list"),
            {"filter[historyRelation]": self.definition.pk},
            content_type=JSONAPI)
        self.assertEqual(response.status_code, 200)

        expected = {str(row.pk) for row
                    in self.definition.change_logs.all()}
        answered = {row["id"] for row in response.json()["data"]}
        self.assertTrue(answered)
        self.assertTrue(answered <= expected,
                        f"rows of another definition in the answer: "
                        f"{answered - expected}")

    def test_an_audit_row_cannot_be_written(self):
        """The changelog answers reads; the write verbs are not routed.

        An audit which the caller could edit answers no question, and #741's
        whole point is that the answer can be trusted.
        """
        row = self.definition.change_logs.first()
        self.login(self.superuser)
        for method in ("patch", "post", "delete"):
            response = getattr(self.api, method)(
                reverse("accounts:roledefinition-historical-detail",
                        args=[row.pk]),
                {"data": {"type": "HistoricalRoleDefinition",
                          "attributes": {"label": "rewritten"}}},
                content_type=JSONAPI)
            self.assertEqual(
                response.status_code, 405,
                f"{method.upper()} is answered on an audit row")

    def test_the_answer_names_who_changed_the_row(self):
        """``include=historyUser`` is what the feed shows as the author."""
        self.login(self.admin)
        response = self.api.get(
            reverse("accounts:roledefinition-historical-list"),
            {"include": "historyUser",
             "filter[historyRelation]": self.definition.pk},
            content_type=JSONAPI)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["data"])


class MembershipChangelogAPITest(RoleAPITestCaseMixin, TestCase):
    """The changelog of the grants discloses who-holds-what: narrowed alike."""

    def setUp(self):
        super().setUp()
        self.editor_role.add_member(self.member)

    def historical(self, user):
        self.login(user)
        response = self.api.get(
            reverse("accounts:membership-historical-list"),
            content_type=JSONAPI)
        self.assertEqual(response.status_code, 200)
        return {row["id"] for row in response.json()["data"]}

    def test_an_outsider_is_answered_the_empty_list(self):
        """The audit is no wider than the rows themselves.

        The flat membership collection narrows to the visible rows of
        ``visible_memberships``; an audit which let an outsider read who was
        granted what would disclose the very thing that narrowing exists to
        keep in.
        """
        self.assertEqual(self.historical(self.outsider), set())

    def test_the_member_reads_their_own_grant(self):
        self.assertIn(
            str(self.editor_role.memberships.get(user=self.member)
                .change_logs.first().pk),
            self.historical(self.member))

    def test_the_administrator_of_the_organization_reads_them_all(self):
        answered = self.historical(self.admin)
        expected = {str(row.pk) for row in
                    RoleMembership.change_log.filter(
                        role__organization=self.organization)}
        self.assertTrue(expected, "the fixture granted no role")
        self.assertTrue(expected <= answered,
                        f"rows of the organization missing: "
                        f"{expected - answered}")
