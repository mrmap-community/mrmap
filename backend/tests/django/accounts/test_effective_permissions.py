"""``GET /api/accounts/effective-permissions`` - the decision down to its grant.

The acceptance criterion of #741 this module pins is the sentence an
administrator reads: an answer names **which layer decided** and **the concrete
grant behind it** - the direct object grant, the grant which reaches through a
role, or the retired global grant of an upgraded instance - and an account which
has nothing to do with the object is refused.

The object the questions are asked about is an ``Organization``: it is a model
whose grants are stored in its own dedicated tables (#735), it is its own
organization for the role axis (#734) and the bootstrap of #732 grants on it, so
both layers which can decide are present without a service fixture. The two
permissions the tests ask differ on purpose: ``view_organization`` is written as
an object grant onto the group of the ``organization_admin`` role, so the object
axis decides it and the answer has to name the role behind that group, while
``can_publish_for_organization`` is in the permission set of that definition but
granted by the bootstrap onto the *default* role's group only - so for the
administrator it can only be answered by the role axis, which is the "grant via
role" answer the issue names.

For the retired *global* grant the test asks :func:`extras.permissions.explain`
directly: the endpoint refuses an unrelated caller by design, and the retired
grant must stay visible in an answer without ever deciding one (Q5 = B).
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models.guardian import OrganizationGroupObjectPermission
from accounts.models.groups import Organization
from accounts.utils import anonymous_viewer_group
from extras.permissions import (DENIED_LAYER, OBJECT_GRANT_LAYER,
                                ORGANIZATION_ROLE_LAYER, PLATFORM_ROLE_LAYER,
                                PUBLIC_GRANT_LAYER, explain)
from tests.django.accounts.test_roles_api import (ADMIN_SLUG,
                                                  RoleAPITestCaseMixin)

ORGANIZATION_MODEL = "accounts.organization"

#: the answer of this endpoint is plain JSON, not a JSON:API document: it is
#: one object about the caller, not a collection of resources. So the accept
#: header of the JSON:API endpoints - which ``RoleAPITestCaseMixin`` sets on
#: the client, as every screen of the deployment does - is refused here with a
#: 406, and the test asks with the media type the endpoint promises. The
#: distinction is the one ``test_browser_session.py`` already draws.
PLAIN_JSON = "application/json"

#: the permission the ``organization_admin`` definition holds while the
#: bootstrap writes it onto the *default* role's group only: for the
#: administrator no object grant of it exists, so only the role axis answers it
ROLE_ONLY_PERM = "accounts.can_publish_for_organization"


class EffectivePermissionsAPITest(RoleAPITestCaseMixin, TestCase):
    """The endpoint: the answer it gives, and who is refused it."""

    def setUp(self):
        super().setUp()
        self.url = reverse("accounts:effective-permissions")

    def ask(self, user, model=ORGANIZATION_MODEL, object_pk=None, perm=None):
        """One question of one account, with the defaults an admin uses."""
        self.login(user)
        self.as_plain_json()
        params = {"model": model,
                  "object": (self.organization.pk if object_pk is None
                             else object_pk)}
        if perm:
            params["perm"] = perm
        return self.api.get(self.url, params)

    def as_plain_json(self):
        """Ask for the media type this endpoint answers (see ``PLAIN_JSON``)."""
        self.api.credentials(HTTP_ACCEPT=PLAIN_JSON)

    def test_a_direct_object_grant_is_named_with_the_role_behind_it(self):
        """The grant the object axis answers is shown *with* its group.

        The bootstrap grants ``view_organization`` onto the role group, so the
        object axis decides - and the honest form of that answer is "the group
        of the ``organization_admin`` role of Role API Org holds it", which is
        what the auditor asks and not "a row in a table".
        """
        response = self.ask(self.admin, perm="view_organization")
        self.assertEqual(response.status_code, 200)
        answer = response.json()["answers"][0]

        self.assertTrue(answer["allowed"])
        self.assertEqual(answer["decided_by"], OBJECT_GRANT_LAYER)
        self.assertEqual(answer["permission"], "accounts.view_organization")
        grant = answer["grants"][0]
        self.assertEqual(grant["kind"], "group")
        self.assertEqual(grant["role_definition"], ADMIN_SLUG)
        self.assertEqual(grant["organization"], "Role API Org")

    def test_a_grant_which_only_a_role_gives_is_answered_as_such(self):
        """``decided_by`` names the layer, and the grant names the decision.

        ``can_publish_for_organization`` is in the definition's set and no
        object grant of it exists for this account: the ORGANIZATION-role axis
        answers, and the grant entry is the whole chain of the decision - who
        was granted the role, by whom (#732 keeps the grantor) and until when
        it holds. The grantor is named here and not read off the fixture,
        because the bootstrap's own membership has no person to credit - and an
        answer which invented one would be a worse audit than one which says
        that nobody decided.
        """
        membership = self.admin_role.memberships.get(user=self.admin)
        membership.granted_by = self.superuser
        membership.valid_until = timezone.now() + timedelta(days=30)
        membership.save()

        response = self.ask(self.admin, perm=ROLE_ONLY_PERM)
        self.assertEqual(response.status_code, 200)
        answer = response.json()["answers"][0]

        self.assertTrue(answer["allowed"])
        self.assertEqual(answer["decided_by"], ORGANIZATION_ROLE_LAYER)
        self.assertEqual(answer["permission"], ROLE_ONLY_PERM)
        grant = answer["grants"][0]
        self.assertEqual(grant["kind"], "membership")
        self.assertEqual(grant["role_definition"], ADMIN_SLUG)
        self.assertEqual(grant["organization"], "Role API Org")
        self.assertEqual(grant["granted_by"], "root")
        self.assertEqual(
            grant["valid_until"][:10],
            (timezone.now() + timedelta(days=30)).strftime("%Y-%m-%d"))

    def test_the_administrator_of_another_organization_is_refused(self):
        """Delegated scope stops at the organization it was delegated for.

        #727's Q3 says membership in one organization says nothing about
        another; the audit answer is no exception, so the administrator of one
        organization is answered a refusal over a foreign one. The layers of
        that refusal are pinned in :class:`ExplainAnswerTest`, where the same
        question is asked of the facade without the endpoint's gate.
        """
        response = self.ask(self.admin,
                            object_pk=self.other_organization.pk,
                            perm="view_organization")
        self.assertEqual(response.status_code, 403)

    def test_an_unrelated_caller_is_refused(self):
        """No grant, no audit duty, no answer: an outsider learns nothing.

        The endpoint explains the calling account's own rights and is the audit
        duty of a platform holder or the administrator of the object's
        organization - never of a stranger.
        """
        response = self.ask(self.outsider,
                            object_pk=self.other_organization.pk,
                            perm="view_organization")
        self.assertEqual(response.status_code, 403)

    def test_an_anonymous_caller_is_refused(self):
        self.api.force_authenticate(None)
        self.as_plain_json()
        response = self.api.get(self.url, {
            "model": ORGANIZATION_MODEL, "object": self.organization.pk})
        self.assertIn(response.status_code, (401, 403))

    def test_the_superuser_is_answered_the_break_glass(self):
        """The superuser decides before every axis - and the answer says so.

        Decision Q6 = A keeps the superuser the break-glass privilege rather
        than a role; an audit which named a grant for it would invent one.
        """
        response = self.ask(self.superuser, perm="change_organization")
        self.assertEqual(response.status_code, 200)
        answer = response.json()["answers"][0]
        self.assertTrue(answer["allowed"])
        self.assertEqual(answer["decided_by"], "break_glass_superuser")
        self.assertEqual(answer["grants"], [])

    def test_the_default_answers_the_object_permissions_of_the_model(self):
        """Without ``perm`` the screen gets view, change and delete at once."""
        response = self.ask(self.admin)
        self.assertEqual(response.status_code, 200)
        answered = response.json()["answers"]
        self.assertEqual(
            [answer["permission"] for answer in answered],
            ["accounts.change_organization", "accounts.delete_organization",
             "accounts.view_organization"])

    def test_an_unknown_model_is_a_bad_request(self):
        response = self.ask(self.admin, model="accounts.notathing")
        self.assertEqual(response.status_code, 400)

    def test_a_missing_object_is_not_found(self):
        response = self.ask(self.admin, object_pk=999999)
        self.assertEqual(response.status_code, 404)

    def test_a_permission_of_another_model_is_a_bad_request(self):
        """An answer which would be empty is answered as a mistake instead."""
        response = self.ask(self.admin, perm="view_webmapservice")
        self.assertEqual(response.status_code, 400)


class ExplainAnswerTest(TestCase):
    """The answer of the facade itself, including the retired global grant."""

    def setUp(self):
        self.organization = Organization.objects.create(name="Explain Org")
        self.user = get_user_model().objects.create_user(
            username="explained", password="x")

    def permission(self, codename, app_label="accounts"):
        return Permission.objects.get(
            content_type__app_label=app_label, codename=codename)

    def test_a_refusal_names_no_layer_and_no_grant(self):
        """Nothing holds: ``denied``, with every layer asked and none holding."""
        answer = explain(self.user, "accounts.change_organization",
                         self.organization)

        self.assertFalse(answer["allowed"])
        self.assertEqual(answer["decided_by"], DENIED_LAYER)
        self.assertEqual(answer["grants"], [])
        self.assertEqual(
            [(layer["layer"], layer["holds"]) for layer in answer["layers"]],
            [(OBJECT_GRANT_LAYER, False), (PUBLIC_GRANT_LAYER, False),
             (PLATFORM_ROLE_LAYER, False), (ORGANIZATION_ROLE_LAYER, False)])

    def test_a_retired_global_grant_is_reported_without_deciding(self):
        """The grant Q5 = B retires is the one an upgrade is audited for.

        A pre-role deployment carried ``change_organization`` as a *global*
        permission. The facade does not let it decide an object, so the answer
        is still ``denied`` - but it names the grant, because "did the upgrade
        find her legacy rights?" is exactly the question #741 is asked, and the
        migration of those grants onto roles is what the auditor wants to see.
        """
        self.user.user_permissions.add(self.permission("change_organization"))
        self.user = get_user_model().objects.get(pk=self.user.pk)

        answer = explain(self.user, "accounts.change_organization",
                         self.organization)

        self.assertTrue(
            answer["legacy_global_grant"],
            "the retired global grant is not reported: the audit of an "
            "upgraded instance cannot see what the migration had to map")
        self.assertFalse(answer["allowed"])
        self.assertEqual(answer["decided_by"], DENIED_LAYER)
        self.assertFalse(answer["global_grants_effective"])

    def test_an_answer_about_a_public_object_names_the_public_layer(self):
        """A grant onto the anonymous viewer's group is answered as public.

        Publishing is an explicit act (Q2 of #727); the answer must say so, and
        must not let a logged-in caller's own missing grant hide it.
        """
        group = anonymous_viewer_group()
        if group is None:
            self.skipTest("the anonymous viewer group is not seeded")
        OrganizationGroupObjectPermission.objects.create(
            group=group,
            permission=self.permission("view_organization"),
            content_object=self.organization)

        answer = explain(self.user, "accounts.view_organization",
                         self.organization)

        self.assertTrue(answer["allowed"])
        self.assertEqual(answer["decided_by"], PUBLIC_GRANT_LAYER)
        self.assertEqual(answer["grants"][0]["kind"], "group")

    def test_an_inactive_user_is_answered_the_refusal(self):
        """``is_active`` refuses before every axis - the facade's rule, stated."""
        self.user.is_active = False
        self.user.save()

        answer = explain(self.user, "accounts.view_organization",
                         self.organization)

        self.assertFalse(answer["allowed"])
        self.assertEqual(answer["decided_by"], DENIED_LAYER)
        self.assertEqual(answer["layers"][-1]["layer"], "inactive_user")
