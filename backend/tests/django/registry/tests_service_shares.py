"""The share endpoints of one service (#740).

``/api/registry/{wms|wfs}/{id}/share`` answers the registry access axis:
guardian object grants written onto a role group or a user, with the
decision recorded in the row. These are NOT the OGC proxy's access rules
(``Allowed*Operation`` under the ``allowed-*-operations`` routes) - the
naming apart is part of the issue.

Pinned here:

* the gate: registered callers only; the list needs ``view`` over the
  service, every write needs ``registry.share_resource`` over it - held
  through the ``resource_publisher`` definition inside the owning
  organization (the role axis of #734), never through the retired global;
* the list answers decided rows only: the bootstrap grants of the owning
  organization's own roles are who manages the resource at home, not
  somebody it was shared with;
* POST writes onto the GROUP OF A ROLE - one lookup of organization plus
  role slug - and refuses unknown targets, missing roles and actions the
  service cannot carry (``publish`` is the WMS capability, so a WFS has no
  such action);
* DELETE revokes exactly one answered grant id; a bootstrap row is not a
  share and cannot be revoked here;
* a re-share keeps the row's original provenance: the earlier decision is
  on record, not the one which changed nothing.
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models.groups import Organization
from accounts.models.roles import Role
from registry.models.guardian import WebMapServiceGroupObjectPermission
from registry.models.service import WebFeatureService, WebMapService
from registry.models.shares import grant_actions, share_grants

JSONAPI = "application/vnd.api+json"

ORGANIZATION = "Share Organization"

#: the fixture WMS whose fields a created service copies
TEMPLATE_WMS = "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"
#: the fixture WFS used as the second, non-carrier service kind
FIXTURE_WFS = "9cc4889d-0cd4-4c3b-8975-58de6d30db41"


class ServiceShareApiTestCase(TestCase):
    """GET/POST/DELETE of ``…/wms/{id}/share`` through the full stack."""

    fixtures = ["test_users.json", "test_keywords.json", "test_wms.json",
                "test_wfs.json"]

    def setUp(self):
        self.organization = Organization.objects.create(name=ORGANIZATION)
        self.publisher_role = Role.objects.for_org(
            self.organization).with_definition("resource_publisher").get()
        self.editor_role = Role.objects.for_org(
            self.organization).with_definition("resource_editor").get()
        template = WebMapService.objects.get(pk=TEMPLATE_WMS)
        self.service = WebMapService(
            title="Shared WMS",
            service_url="https://www.example.com/service",
            version=template.version,
            origin=template.origin,
            metadata_contact=template.metadata_contact,
            service_contact=template.service_contact)
        self.service.owner = self.organization
        self.service.save()

        # publisher holds view + share_resource of the owning organization
        # through its definition; editor holds view but nothing share related
        self.publisher = get_user_model().objects.get(username="User2")
        self.publisher.groups.add(self.publisher_role.group)
        self.editor = get_user_model().objects.get(username="User1")
        self.editor.groups.add(self.editor_role.group)

    def url(self, suffix=""):
        tail = f"{suffix}/" if suffix else ""
        return f"/api/registry/wms/{self.service.pk}/share/" + tail

    def post_share(self, attributes, user):
        client = APIClient()
        client.force_authenticate(user=user)
        document = {
            "data": {"type": "WebMapService", "attributes": attributes}}
        return client.post(self.url(), data=json.dumps(document),
                           content_type=JSONAPI)

    def get_share(self, user=None):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user=user)
        return client.get(self.url())

    # ------------------------------------------------------------------ gate

    def test_anonymous_is_refused_the_grant_list(self):
        """A grant list names who got rights: administration, not content"""
        self.assertEqual(self.get_share().status_code, 403)

    def test_the_list_needs_view_over_the_service(self):
        """An outsider with only the fixture globals: the 404 answer

        Without view the object answers like it was never there - the
        404-vs-403 shape of the base permission class (#1319).
        """
        outsider = get_user_model().objects.create_user(
            "share-outsider", password="test")
        self.assertEqual(self.get_share(outsider).status_code, 404)

    def test_the_list_answers_for_a_publisher_of_the_owning_organization(
            self):
        """The bootstrap grants are not shares: the list starts empty"""
        response = self.get_share(self.publisher)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"grants": []})
        # the bootstrap wrote rows - three for the editor role, none decided
        self.assertEqual(WebMapServiceGroupObjectPermission.objects.filter(
            content_object=self.service).count(), 3)

    def test_writing_needs_share_resource_not_edit(self):
        """An editor may change the service and still may not share it"""
        response = self.post_share(
            {"organization": self.organization.pk, "role": "resource_editor",
             "actions": ["view"]}, self.editor)
        self.assertEqual(response.status_code, 403)

    # ----------------------------------------------------------------- write

    def test_post_grants_actions_to_the_group_of_a_role(self):
        """One organization + role lookup, and the decided rows come back"""
        response = self.post_share(
            {"organization": self.organization.pk, "role": "resource_editor",
             "actions": ["view", "change"]}, self.publisher)
        self.assertEqual(response.status_code, 201)
        grants = response.json()["grants"]
        self.assertEqual(
            sorted(grant["action"] for grant in grants),
            ["change", "view"])
        for grant in grants:
            self.assertEqual(grant["targetKind"], "role")
            self.assertEqual(grant["role"], "resource_editor")
            self.assertEqual(grant["organization"], ORGANIZATION)
            self.assertEqual(grant["grantedBy"], str(self.publisher))

        rows = WebMapServiceGroupObjectPermission.objects.filter(
            content_object=self.service, group=self.editor_role.group,
            granted_by__isnull=False)
        self.assertEqual(rows.count(), 2)
        self.assertTrue(all(row.granted_by == self.publisher
                            for row in rows))

    def test_the_list_then_shares_the_decided_rows(self):
        self.post_share({"organization": self.organization.pk,
                         "role": "resource_editor",
                         "actions": ["view"]}, self.publisher)
        grants = self.get_share(self.publisher).json()["grants"]
        self.assertEqual(len(grants), 1)
        self.assertEqual(grants[0]["targetKind"], "role")
        self.assertEqual(grants[0]["action"], "view")
        self.assertTrue(grants[0]["id"].startswith("group-"))
        self.assertIsNotNone(grants[0]["createdAt"])

    def test_post_refuses_targets_and_actions_the_service_cannot_answer(
            self):
        """Four refusals, one POST shape"""
        shareable = {"organization": self.organization.pk,
                     "role": "resource_editor", "actions": ["view"]}
        cases = [
            # no target named at all
            {"actions": ["view"]},
            # two targets at once
            dict(shareable, user=self.publisher.pk),
            # an organization without the role it must name (#740 shares
            # with a role, not with everybody in an organization)
            {"organization": self.organization.pk, "actions": ["view"]},
            # an unknown user
            {"user": 0, "actions": ["view"]},
            # an action this service kind cannot carry: publish is the WMS
            # capability - a WMS CAN carry it, an unknown action can never
            dict(shareable, actions=["approve"]),
        ]
        for attributes in cases:
            response = self.post_share(attributes, self.publisher)
            self.assertEqual(response.status_code, 400,
                             f"{attributes} was not refused")

    def test_the_publish_action_carries_the_wms_capability(self):
        """``publish`` is shareable on the capability carrier (WMS)"""
        response = self.post_share(
            {"organization": self.organization.pk,
             "role": "resource_editor", "actions": ["publish"]},
            self.publisher)
        self.assertEqual(response.status_code, 201)
        grant = response.json()["grants"][0]
        self.assertEqual(grant["action"], "publish")
        self.assertEqual(grant["permission"], "publish_resource")

    def test_a_wfs_has_no_publish_action(self):
        """One Permission row for the capability, carried by webmapservice

        A guardian object grant and its permission must agree on the
        content type, so a second row per service kind would be a second
        vocabulary: the WFS share refuses ``publish`` and shares its own
        ``view`` just fine.
        """
        # the role axis of the facade scopes by ownership, so the fixture
        # service gets one - without an owner nobody may share it
        wfs = WebFeatureService.objects.get(pk=FIXTURE_WFS)
        wfs.owner = self.organization
        wfs.save()
        client = APIClient()
        client.force_authenticate(user=self.publisher)
        url = f"/api/registry/wfs/{FIXTURE_WFS}/share/"
        refused = client.post(
            url, data=json.dumps({"data": {"type": "WebFeatureService",
                                           "attributes": {
                                               "organization":
                                                   self.organization.pk,
                                               "role": "resource_editor",
                                               "actions": ["publish"]}}}),
            content_type=JSONAPI)
        self.assertEqual(refused.status_code, 400)

        granted = client.post(
            url, data=json.dumps({"data": {"type": "WebFeatureService",
                                           "attributes": {
                                               "organization":
                                                   self.organization.pk,
                                               "role": "resource_editor",
                                               "actions": ["view"]}}}),
            content_type=JSONAPI)
        self.assertEqual(granted.status_code, 201)

    # ---------------------------------------------------------------- revoke

    def test_delete_revokes_exactly_the_answered_grant(self):
        created = self.post_share(
            {"organization": self.organization.pk,
             "role": "resource_editor", "actions": ["view", "change"]},
            self.publisher).json()["grants"]
        self.assertEqual(len(created), 2)
        keep = [grant for grant in created if grant["action"] == "view"][0]
        drop = [grant for grant in created if grant["action"] == "change"][0]

        client = APIClient()
        client.force_authenticate(user=self.publisher)
        response = client.delete(self.url(drop["id"]))
        self.assertEqual(response.status_code, 204)

        remaining = self.get_share(self.publisher).json()["grants"]
        self.assertEqual([grant["id"] for grant in remaining], [keep["id"]])
        # the id is gone: revoking it twice says so
        self.assertEqual(client.delete(self.url(drop["id"])).status_code,
                         404)

    def test_a_bootstrap_grant_is_not_revocable_as_a_share(self):
        """The list hides the bootstrap rows; the delete route does too

        Administering who manages the resource at home belongs to the role
        work, not to this endpoint - reaching a bootstrap pk deletes nothing.
        """
        bootstrap = WebMapServiceGroupObjectPermission.objects.filter(
            content_object=self.service).first()
        client = APIClient()
        client.force_authenticate(user=self.publisher)
        response = client.delete(self.url(f"group-{bootstrap.pk}"))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(WebMapServiceGroupObjectPermission.objects.filter(
            pk=bootstrap.pk).exists())

    def test_revoking_needs_the_share_capability_too(self):
        created = self.post_share(
            {"organization": self.organization.pk,
             "role": "resource_editor", "actions": ["view"]},
            self.publisher).json()["grants"]
        client = APIClient()
        client.force_authenticate(user=self.editor)
        self.assertEqual(client.delete(
            self.url(created[0]["id"])).status_code, 403)


class ShareModelTestCase(TestCase):
    """The row semantics the API rests on, without HTTP."""

    fixtures = ["test_users.json", "test_keywords.json", "test_wms.json"]

    def setUp(self):
        self.organization = Organization.objects.create(name=ORGANIZATION)
        self.editor_role = Role.objects.for_org(
            self.organization).with_definition("resource_editor").get()
        template = WebMapService.objects.get(pk=TEMPLATE_WMS)
        self.service = WebMapService(
            title="Model Shared",
            service_url="https://www.example.com/service",
            version=template.version,
            origin=template.origin,
            metadata_contact=template.metadata_contact,
            service_contact=template.service_contact)
        self.service.owner = self.organization
        self.service.save()
        self.actor = get_user_model().objects.get(username="User2")

    def test_a_re_share_keeps_the_original_provenance(self):
        """``get_or_create`` semantics on the decided rows (#741)

        The second call which names the same action changes nothing: the
        row keeps the person and the timestamp of the decision which
        created it.
        """
        first, = grant_actions(self.service, self.editor_role.group,
                               ["view"], granted_by=self.actor)
        self.assertEqual(share_grants(self.service), [first])

        other = get_user_model().objects.get(username="User1")
        again, = grant_actions(self.service, self.editor_role.group,
                               ["view"], granted_by=other)
        self.assertEqual(share_grants(self.service), [first])
        self.assertEqual(first[1].granted_by, self.actor)
