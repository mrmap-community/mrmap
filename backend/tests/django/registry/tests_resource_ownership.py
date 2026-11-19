"""The stored ownership of #733: which organization a resource belongs to.

Before #733 the create serializers answered an ``owner`` relation which no
model stored: a client could name any organization, the value was dropped
between the view and the registration task and the service stayed ownerless
without a word. These tests pin the shape the accepted Q3=A of #727 decided:

* the create serializer is the place the owner is decided - a named owner
  must be an organization the creating user is a member of, a user with
  exactly one organization gets that one by default, and a user with no or
  with several organizations gets a validation error instead of a guess,
* the decided owner is written by the task which persists the service, so
  the row comes into the world with its owner and never stands ownerless
  by an omitted default,
* an update candidate is the same service under update: it carries the
  owner of the published service,
* the read API answers the ``owner`` relation verifiably and does not let
  a PATCH move a resource into another organization.

The legacy rows stay ownerless (see the migration which adds the column);
a task message without an owner stores that same shape, which the last
test of the task group pins.
"""
from pathlib import Path
from unittest.mock import patch

from accounts.models.groups import Organization
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, TransactionTestCase
from django.test.utils import override_settings
from django.urls import reverse
from notify.models import BackgroundProcess
from registry.enums.update import UpdateJobStatusEnum
from registry.models.service import WebMapService
from registry.models.update import WebMapServiceUpdateJob
from registry.serializers.service import (
    CatalogueServiceCreateSerializer, WebFeatureServiceCreateSerializer,
    WebMapServiceCreateSerializer)
from registry.tasks.service import build_ogc_service
from rest_framework.test import APIRequestFactory, APIClient

User = get_user_model()

#: the capabilities document the registration task of the task tests serves
CAPABILITIES_WMS = Path(
    __file__).resolve().parents[1] / "test_data/capabilities/wms/1.3.0.xml"
CAPABILITIES_URL = ("https://maps.dwd.de/geoserver/wms?SERVICE=WMS"
                    "&VERSION=1.3.0&REQUEST=GetCapabilities")

#: the create serializers of the three concrete kinds of resource
CREATE_SERIALIZERS = {
    "WebMapService": WebMapServiceCreateSerializer,
    "WebFeatureService": WebFeatureServiceCreateSerializer,
    "CatalogueService": CatalogueServiceCreateSerializer,
}

JSONAPI = "application/vnd.api+json"


def serve_capabilities(request, *args, **kwargs):
    """Serves the document the task of the registration fetches."""
    from tests.django.utils import MockResponse
    return MockResponse(status_code=200, content=CAPABILITIES_WMS)


class OrganizationMembershipMixin:
    """The users and organizations the ownership question is asked of."""

    def setUp(self):
        super().setUp()
        self.org_a = Organization.objects.create(name="Owning Amt")
        self.org_b = Organization.objects.create(name="Other Amt")
        self.member = User.objects.create_user(
            username="member", password="x")
        self.member.groups.add(self.org_a)
        self.outsider = User.objects.create_user(
            username="outsider", password="x")
        self.multi = User.objects.create_user(
            username="multi", password="x")
        self.multi.groups.add(self.org_a, self.org_b)
        self.admin = User.objects.create_superuser(
            username="ownership-admin", password="x")


def serialize(serializer_cls, data, user):
    """Runs a create serializer against data as the given user.

    Returns:
        tuple: (is_valid, serializer) - the serializer holds either the
            decided owner in ``validated_data`` or the field errors.
    """
    request = APIRequestFactory().post("/api/registry/wms")
    # a factory request reaches the serializer without the view's wrapping,
    # so the authenticated user is the one this test names directly
    request.user = user
    serializer = serializer_cls(data=data, context={"request": request})
    return serializer.is_valid(), serializer


class CreateSerializerOwnerDecisionTests(OrganizationMembershipMixin,
                                         TestCase):
    """The serializer decides the owner of every resource kind the same way."""

    def payload(self, owner=None, url="https://example.com/wms?SERVICE=WMS"
                "&VERSION=1.3.0&REQUEST=GetCapabilities"):
        data = {
            "get_capabilities_url": url,
            "collect_metadata_records": False,
        }
        if owner is not None:
            # the json:api field reads a resource identifier object
            data["owner"] = {"type": "Organization", "id": str(owner.pk)}
        return data

    def test_a_member_may_name_its_organization(self):
        for service_kind, serializer_cls in CREATE_SERIALIZERS.items():
            valid, serializer = serialize(
                serializer_cls, self.payload(owner=self.org_a),
                self.member)
            self.assertTrue(
                valid,
                f"{service_kind}: {serializer.errors}")
            self.assertEqual(serializer.validated_data["owner"], self.org_a)

    def test_the_sole_membership_decides_when_no_owner_is_named(self):
        for service_kind, serializer_cls in CREATE_SERIALIZERS.items():
            valid, serializer = serialize(
                serializer_cls, self.payload(), self.member)
            self.assertTrue(
                valid,
                f"{service_kind}: {serializer.errors}")
            self.assertEqual(serializer.validated_data["owner"], self.org_a)

    def test_an_ambiguous_membership_is_refused_not_guessed(self):
        # Q3=A: never default to the first membership
        for service_kind, serializer_cls in CREATE_SERIALIZERS.items():
            valid, serializer = serialize(
                serializer_cls, self.payload(), self.multi)
            self.assertFalse(
                valid, f"{service_kind} accepted an ambiguous owner")
            self.assertIn("owner", serializer.errors)
            self.assertIn(
                "more than one organization",
                str(serializer.errors["owner"][0]))

    def test_a_user_without_membership_is_refused(self):
        for service_kind, serializer_cls in CREATE_SERIALIZERS.items():
            valid, serializer = serialize(
                serializer_cls, self.payload(), self.outsider)
            self.assertFalse(
                valid, f"{service_kind} accepted an ownerless create")
            self.assertIn("owner", serializer.errors)

    def test_an_owner_of_an_unrelated_organization_is_refused(self):
        # the silent no-op is gone: naming an organization is not enough
        for service_kind, serializer_cls in CREATE_SERIALIZERS.items():
            valid, serializer = serialize(
                serializer_cls, self.payload(owner=self.org_b),
                self.outsider)
            self.assertFalse(
                valid, f"{service_kind} accepted a foreign owner")
            self.assertIn("owner", serializer.errors)
            self.assertIn(
                "not a member", str(serializer.errors["owner"][0]))

    def test_a_superuser_may_name_any_organization(self):
        # the superuser holds every permission of every organization
        valid, serializer = serialize(
            WebMapServiceCreateSerializer,
            self.payload(owner=self.org_b), self.admin)
        self.assertTrue(valid, serializer.errors)
        self.assertEqual(serializer.validated_data["owner"], self.org_b)

    def test_a_superuser_must_name_an_organization(self):
        # memberships decide nothing for a user without them
        valid, serializer = serialize(
            WebMapServiceCreateSerializer, self.payload(), self.admin)
        self.assertFalse(valid, "an ownerless create passed")
        self.assertIn("owner", serializer.errors)


class CreateApiOwnerTests(OrganizationMembershipMixin, TestCase):
    """The POSTed owner takes effect or is refused - the no-op is gone.

    Through the API, because the JSON:API relation is what the client
    actually sends, and the validation must guard the real request.
    """

    def setUp(self):
        super().setUp()
        add_wms = Permission.objects.get(
            codename="add_webmapservice",
            content_type__app_label="registry")
        self.member.user_permissions.add(add_wms)
        self.outsider.user_permissions.add(add_wms)
        self.client = APIClient()
        self.client.credentials(HTTP_ACCEPT=JSONAPI)

    def post_as(self, user, owner=None):
        self.client.force_authenticate(user)
        relationships = {}
        if owner is not None:
            relationships["owner"] = {"data": {
                "id": str(owner.pk), "type": "Organization"}}
        return self.client.post("/api/registry/wms", {
            "data": {
                "type": "WebMapService",
                "attributes": {
                    "get_capabilities_url":
                        "https://example.com/wms?SERVICE=WMS&VERSION=1.3.0"
                        "&REQUEST=GetCapabilities",
                    "collect_metadata_records": False,
                },
                "relationships": relationships,
            }
        }, format="vnd.api+json")

    def test_a_foreign_owner_is_answered_with_a_validation_error(self):
        # 202 with a silently dropped owner is the bug this refuses
        response = self.post_as(self.outsider, owner=self.org_a)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(WebMapService.objects.count(), 0)

    def test_an_ambiguous_membership_is_answered_with_a_validation_error(self):
        self.multi.user_permissions.add(Permission.objects.get(
            codename="add_webmapservice",
            content_type__app_label="registry"))
        response = self.post_as(self.multi)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(WebMapService.objects.count(), 0)

    def test_the_decided_owner_travels_with_the_task(self):
        """The view hands the decided owner to the publication (#733).

        The task itself is halted - where the stored owner lands is pinned
        by ``RegistrationTaskOwnerTests``; here it is the transport: the
        relation the serializer decided is in the kwargs of the message.
        """
        with patch.object(
                build_ogc_service, "apply_async",
                autospec=True) as apply_async:
            response = self.post_as(self.member, owner=self.org_a)
            self.assertEqual(response.status_code, 202, response.content)
        task_kwargs = apply_async.call_args.kwargs["kwargs"]
        self.assertEqual(task_kwargs["owner_pk"], self.org_a.pk)
        self.assertEqual(WebMapService.objects.count(), 0,
                         msg="the halted task may not have persisted")


class RegistrationTaskOwnerTests(TransactionTestCase):
    """The task writes the ownership with the row it persists."""

    def setUp(self):
        self.organization = Organization.objects.create(name="Task Amt")
        self.http_request = {
            "path": "http://example.de",
            "method": "GET",
            "content_type": JSONAPI,
            "data": {},
        }
        self.background_process = BackgroundProcess.objects.create(
            phase="", process_type="registering", description="")

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch("registry.tasks.service.Session.send",
           side_effect=serve_capabilities)
    def test_the_service_row_arrives_with_its_owner(self, mock_send):
        # a TransactionTestCase sees the rows of other transaction tests of
        # this worker - the task's own row is the one which arrives NOW, so
        # the question is which ids the call added, not what the table holds
        before = set(WebMapService.objects.values_list("pk", flat=True))
        build_ogc_service.delay(
            get_capabilities_url=CAPABILITIES_URL,
            collect_metadata_records=False,
            service_auth_pk=None,
            http_request=self.http_request,
            background_process_pk=self.background_process.pk,
            owner_pk=self.organization.pk)

        created = WebMapService.objects.exclude(pk__in=before)
        self.assertEqual(created.count(), 1)
        self.assertEqual(created.get().owner, self.organization)

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch("registry.tasks.service.Session.send",
           side_effect=serve_capabilities)
    def test_a_message_without_an_owner_stays_ownerless(self, mock_send):
        """The shape of a message queued before #733 is the legacy shape.

        It stays ownerless - readable, decided by object grants only, and
        not silently attributed to some organization of the creating user.
        """
        before = set(WebMapService.objects.values_list("pk", flat=True))
        build_ogc_service.delay(
            get_capabilities_url=CAPABILITIES_URL,
            collect_metadata_records=False,
            service_auth_pk=None,
            http_request=self.http_request,
            background_process_pk=self.background_process.pk)

        created = WebMapService.objects.exclude(pk__in=before)
        self.assertEqual(created.count(), 1)
        self.assertIsNone(created.get().owner)


class UpdateCandidateOwnerTests(OrganizationMembershipMixin, TestCase):
    """A candidate is the same service under update: the owner carries."""

    fixtures = ["test_users.json", "test_keywords.json", "test_wms.json"]

    def test_the_candidate_carries_the_owner_of_the_published_service(self):
        service = WebMapService.objects.get(
            pk="cd16cc1f-3abb-4625-bb96-fbe80dbe23e3")
        service.owner = self.org_a
        service.save()

        job = WebMapServiceUpdateJob.objects.create(
            service=service, status=UpdateJobStatusEnum.REVIEW_REQUIRED.value)
        capabilities = CAPABILITIES_WMS.read_bytes()
        job.create_new_service(capabilities)

        candidate = WebMapService.objects.get(update_candidate_of=service)
        self.assertEqual(candidate.owner, self.org_a)


class OwnerReadApiTests(OrganizationMembershipMixin, TestCase):
    """The read side answers the owner and refuses to write it."""

    fixtures = ["test_users.json", "test_keywords.json", "test_wms.json"]

    def setUp(self):
        super().setUp()
        self.service = WebMapService.objects.get(
            pk="cd16cc1f-3abb-4625-bb96-fbe80dbe23e3")
        self.service.owner = self.org_a
        self.service.save()
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.client.credentials(HTTP_ACCEPT=JSONAPI)

    def test_the_detail_answers_the_owner_relation(self):
        response = self.client.get(
            reverse("registry:wms-detail", args=[self.service.pk]))
        self.assertEqual(response.status_code, 200, response.content)
        relationships = response.json()["data"]["relationships"]
        self.assertEqual(
            relationships["owner"]["data"],
            {"type": "Organization", "id": str(self.org_a.pk)})

    def test_the_owner_can_be_included(self):
        response = self.client.get(
            reverse("registry:wms-detail", args=[self.service.pk]),
            {"include": "owner"})
        self.assertEqual(response.status_code, 200, response.content)
        included = response.json().get("included", [])
        self.assertIn(
            str(self.org_a.pk),
            [item["id"] for item in included
             if item["type"] == "Organization"])

    def test_a_patch_may_not_move_the_resource_to_another_owner(self):
        response = self.client.patch(
            reverse("registry:wms-detail", args=[self.service.pk]),
            {
                "data": {
                    "type": "WebMapService",
                    "id": str(self.service.pk),
                    "relationships": {
                        "owner": {"data": {
                            "id": str(self.org_b.pk),
                            "type": "Organization"}}
                    },
                }
            },
            format="vnd.api+json")
        self.assertIn(response.status_code, (200, 400, 403),
                      response.content)
        self.service.refresh_from_db()
        self.assertEqual(
            self.service.owner, self.org_a,
            "the PATCH moved the resource into another organization")
