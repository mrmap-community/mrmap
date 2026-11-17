"""The visibility tri-state over the API (#739): annotation, filter, write.

The list, the detail route and the PATCH must answer one and the same question
about one and the same resource - the split between "the list shows it" and
"the detail 403s it" is what #727 called the bug and #734's facade resolved
for a single object. #739 answers the list:

* every WMS/WFS read annotates ``visibility`` from guardian's own tables -
  public (the anonymous viewer group holds the view grant), organization-
  internal (a role group of the owning organization does) or restricted
  (neither) - so a page answers it without a query per row,
* whether the LIST is narrowed to what the caller may view is the per-model
  rollout switch ``PERMISSION_FILTERED_LIST_MODELS``: off, the list answers
  what it answered before this issue; on, list, detail and count agree because
  the same ``objects_for_user`` SQL that decides the detail decides the page -
  in one SELECT, not one query per role or per row,
* the PATCH moves the resource across the public axis only, gated on
  ``registry.publish_resource`` (and ``manage_access_rules`` for the way
  back); ``restricted`` is not writable - shaping it is #740.
"""
import re

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext, override_settings
from django.urls import reverse

from accounts.models.groups import Organization
from accounts.models.roles import Role, RoleMembership
from accounts.utils import ensure_anonymous_viewer
from extras.permissions import Visibility
from registry.models.metadata import MetadataContact
from registry.models.service import WebFeatureService, WebMapService
from rest_framework.test import APIClient

User = get_user_model()

JSONAPI = "application/vnd.api+json"

#: the fixture rows the services are modelled on (test_wms.json, test_wfs.json)
TEMPLATE_WMS = "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"
TEMPLATE_WFS = "9cc4889d-0cd4-4c3b-8975-58de6d30db41"

#: the rollout switch, spelled for WMS only where a test wants WFS untouched
FILTER_WMS = ["registry.WebMapService"]


class VisibilityDataMixin:
    """Three services answering the three states, beside the fixture's own."""

    fixtures = ["test_keywords.json", "test_wms.json", "test_wfs.json"]

    def setUp(self):
        super().setUp()
        # the rows 0009 seeds, recreated through the paths of a deployment -
        # robust against a truncation before this class (tests/AGENTS.md)
        call_command("sync_role_definitions", verbosity=0)
        ensure_anonymous_viewer()

        self.org_a = Organization.objects.create(name="Sichtbar Amt")
        self.org_b = Organization.objects.create(name="Anderes Amt")

        self.contact = MetadataContact.objects.get(pk=1)

        self.internal = self.create_wms("Internal Service", self.org_b)
        self.restricted = self.create_wms("Restricted Service", None)
        self.public = self.create_wms("Public Service", self.org_a)
        self.publish(self.public)

        # the fixture's own service stays ownerless: restricted too
        self.fixture_service = WebMapService.objects.get(pk=TEMPLATE_WMS)

    def create_wms(self, title, owner):
        template = WebMapService.objects.get(pk=TEMPLATE_WMS)
        service = WebMapService(
            title=title,
            service_url="https://www.example.com/wms",
            version=template.version,
            origin=template.origin,
            metadata_contact=self.contact,
            service_contact=self.contact,
            owner=owner)
        service.save()
        return service

    @staticmethod
    def publish(service):
        from extras.permissions import set_public
        set_public(service, True)

    def member_of(self, username, organization, *definition_slugs):
        """A user in the organization and in the named roles of it."""
        user = User.objects.create_user(username=username, password="x")
        for slug in definition_slugs:
            role = Role.objects.for_org(organization).with_definition(
                slug).get()
            RoleMembership.objects.create(role=role, user=user)
        if not definition_slugs:
            user.groups.add(organization)
        return user


class AnnotationTests(VisibilityDataMixin, TestCase):
    """The SQL answer per row, without the API around it."""

    def test_the_three_states_are_answered_by_the_annotation(self):
        answered = dict(
            WebMapService.objects.filter(
                pk__in=[self.public.pk, self.internal.pk,
                        self.restricted.pk]).with_visibility().values_list(
                            "pk", "visibility"))
        self.assertEqual(
            answered,
            {self.public.pk: Visibility.PUBLIC.value,
             self.internal.pk: Visibility.ORGANIZATION_INTERNAL.value,
             self.restricted.pk: Visibility.RESTRICTED.value})

    def test_a_public_service_of_an_organization_reads_public(self):
        """The precedence of the CASE: the anonymous statement wins."""
        # ``public`` is owned by org_a and org_a's editor role holds the view
        # grant from the creation bootstrap - and it still reads public
        self.assertEqual(
            WebMapService.objects.filter(pk=self.public.pk).with_visibility(
            ).values_list("visibility", flat=True).get(),
            Visibility.PUBLIC.value)

    def test_the_feature_type_kind_answers_the_same_case(self):
        template = WebFeatureService.objects.get(pk=TEMPLATE_WFS)
        wfs = WebFeatureService(
            title="Feature Service",
            service_url="https://www.example.com/wfs",
            version=template.version,
            origin=template.origin,
            metadata_contact=self.contact,
            service_contact=self.contact,
            owner=self.org_b)
        wfs.save()

        self.assertEqual(
            WebFeatureService.objects.filter(
                pk=wfs.pk).with_visibility().values_list(
                    "visibility", flat=True).get(),
            Visibility.ORGANIZATION_INTERNAL.value)


class ListReadTests(VisibilityDataMixin, TestCase):
    """The list answers the annotation - and today still answers everything."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.credentials(HTTP_ACCEPT=JSONAPI)

    def listed(self):
        response = self.client.get(reverse("registry:wms-list"))
        self.assertEqual(response.status_code, 200, response.content)
        return {
            row["id"]: row["attributes"]["visibility"]
            for row in response.json()["data"]}

    def test_anonymous_sees_the_states_of_every_row_before_the_rollout(self):
        """The empty setting keeps today's list, annotation added (#739)."""
        answered = self.listed()
        self.assertEqual(answered[str(self.public.pk)], "public")
        self.assertEqual(answered[str(self.internal.pk)],
                         "organization-internal")
        self.assertEqual(answered[str(self.restricted.pk)], "restricted")
        self.assertIn(str(self.fixture_service.pk), answered)

    @override_settings(PERMISSION_FILTERED_LIST_MODELS=FILTER_WMS)
    def test_the_rollout_switch_hides_the_filter_for_the_other_kind(self):
        """WFS is not named: its list answers everything it answered."""
        response = self.client.get(reverse("registry:wfs-list"))
        self.assertEqual(response.status_code, 200, response.content)
        # the annotation answers there too, whatever the list contains
        rows = response.json()["data"]
        self.assertTrue(
            all("visibility" in row["attributes"] for row in rows),
            "the WFS list must answer visibility even while unfiltered")


class FilteredListTests(VisibilityDataMixin, TestCase):
    """With the switch on, the page is decided in SQL like the detail."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.credentials(HTTP_ACCEPT=JSONAPI)

    def list_ids(self, url=None):
        response = self.client.get(url or reverse("registry:wms-list"))
        self.assertEqual(response.status_code, 200, response.content)
        return {row["id"] for row in response.json()["data"]}

    @override_settings(PERMISSION_FILTERED_LIST_MODELS=FILTER_WMS)
    def test_anonymous_sees_public_rows_alone(self):
        self.assertEqual(self.list_ids(), {str(self.public.pk)})

    @override_settings(PERMISSION_FILTERED_LIST_MODELS=FILTER_WMS)
    def test_detail_and_list_answer_one_question(self):
        """A row hidden from the list cannot be opened by its url either."""
        self.assertEqual(
            self.client.get(reverse(
                "registry:wms-detail", args=[self.internal.pk])).status_code,
            404)
        detail = self.client.get(reverse(
            "registry:wms-detail", args=[self.public.pk]))
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual(
            detail.json()["data"]["attributes"]["visibility"], "public")

    @override_settings(PERMISSION_FILTERED_LIST_MODELS=FILTER_WMS)
    def test_a_member_of_the_owning_organization_keeps_its_rows(self):
        """The org axis of #734 decides the page, not just the object."""
        viewer = self.member_of("viewer-b", self.org_b, "viewer")
        self.client.force_authenticate(viewer)

        self.assertEqual(
            self.list_ids(),
            {str(self.internal.pk), str(self.public.pk)},
            "a viewer must keep seeing its organization's services beside "
            "the public ones")

    @override_settings(PERMISSION_FILTERED_LIST_MODELS=FILTER_WMS)
    def test_a_superuser_sees_every_row(self):
        root = User.objects.create_superuser(
            username="visibility-root", password="x")
        self.client.force_authenticate(root)

        self.assertEqual(
            self.list_ids(),
            {str(self.public.pk), str(self.internal.pk),
             str(self.restricted.pk), str(self.fixture_service.pk)})

    @override_settings(PERMISSION_FILTERED_LIST_MODELS=FILTER_WMS)
    def test_the_filter_is_the_pages_own_statement_not_a_python_narrowing(self):
        """The page is one SELECT whose WHERE carries the permission EXISTS.

        The budget of the answer may not grow with the roles a deployment
        holds: the anonymous viewer's group is named to SQL as a subquery over
        ``accounts_role``, and the org axis arrives as membership ids - no
        query per role group.
        """
        with CaptureQueriesContext(connection) as captured:
            self.list_ids()

        page_selects = [
            q["sql"] for q in captured.captured_queries
            if re.match(r'^\s*SELECT', q["sql"], re.IGNORECASE)
            and re.search(r'FROM\s+"registry_webmapservice"', q["sql"],
                          re.IGNORECASE)]
        self.assertTrue(page_selects, "no page SELECT of the services")
        for sql in page_selects:
            # the rows are already narrowed when the page is read - the count
            # of the pagination asks the same narrowed question
            where = re.split(r'\bWHERE\b', sql, maxsplit=1,
                             flags=re.IGNORECASE)
            self.assertEqual(
                len(where), 2,
                "the permission filter belongs in the WHERE of the page, "
                f"not in python afterwards: {sql[:400]}")
            self.assertRegex(
                where[1], r'\(\s*SELECT',
                "the WHERE carries the permission narrowing as a subquery: "
                f"{where[1][:400]}")
            self.assertIn(
                "registry_webmapservicegroupobjectpermission", where[1],
                "the guardian grants narrow the page in SQL")
        joined = " ".join(page_selects)
        self.assertIn("accounts_role", joined)


class PublishWriteTests(VisibilityDataMixin, TestCase):
    """The PATCH across the public axis, gated on the publish permission."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.credentials(HTTP_ACCEPT=JSONAPI)
        # the target belongs to org_a: the editors and publishers below are
        # org_a's, so the permission check which decides the PATCH is the
        # publish axis and not the change axis of a foreign organization
        self.target = self.create_wms("Publishable Service", self.org_a)

        self.editor = self.member_of("editor-a", self.org_a, "resource_editor")
        self.publisher = self.member_of(
            "publisher-a", self.org_a, "resource_editor",
            "resource_publisher")
        self.outsider = self.member_of(
            "editor-b", self.org_b, "resource_editor")
        self.root = User.objects.create_superuser(
            username="publish-root", password="x")

    def patch(self, user, value):
        self.client.force_authenticate(user)
        return self.client.patch(
            reverse("registry:wms-detail", args=[self.target.pk]),
            {
                "data": {
                    "type": "WebMapService",
                    "id": str(self.target.pk),
                    "attributes": {"visibility": value},
                }
            },
            format="vnd.api+json")

    def visibility_now(self):
        return WebMapService.objects.filter(
            pk=self.target.pk).with_visibility().values_list(
                "visibility", flat=True).get()

    def test_the_publisher_makes_it_public_and_the_answer_says_it(self):
        response = self.patch(self.publisher, "public")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response.json()["data"]["attributes"]["visibility"], "public")
        self.assertEqual(self.visibility_now(), Visibility.PUBLIC.value)

    def test_only_a_publisher_makes_it_public(self):
        """The editor may change the service - not publish it (decision Q2)."""
        response = self.patch(self.editor, "public")
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(
            self.visibility_now(), Visibility.ORGANIZATION_INTERNAL.value)

    def test_a_publisher_of_another_organization_may_not(self):
        """The publish axis is scoped to the owning organization (#734)."""
        response = self.patch(self.outsider, "public")
        self.assertIn(response.status_code, (403, 404), response.content)
        self.assertEqual(
            self.visibility_now(), Visibility.ORGANIZATION_INTERNAL.value)

    def test_restricted_is_answered_but_never_written(self):
        """#740 shares; this endpoint refuses to shape the absence (#739)."""
        response = self.patch(self.publisher, "restricted")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(
            self.visibility_now(), Visibility.ORGANIZATION_INTERNAL.value)

    def test_withdrawing_needs_the_publish_or_access_rules_permission(self):
        self.patch(self.publisher, "public")
        # an editor (no publisher) may not take it back
        response = self.patch(self.editor, "organization-internal")
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(self.visibility_now(), Visibility.PUBLIC.value)

        response = self.patch(self.publisher, "organization-internal")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            self.visibility_now(), Visibility.ORGANIZATION_INTERNAL.value)

    def test_withdrawing_what_is_not_public_is_refused(self):
        """The way back is only the way back; other grants are #740."""
        response = self.patch(self.publisher, "organization-internal")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(
            self.visibility_now(), Visibility.ORGANIZATION_INTERNAL.value)

    def test_an_unknown_word_is_a_field_error(self):
        response = self.patch(self.publisher, "unlisted")
        self.assertEqual(response.status_code, 400, response.content)

    def test_the_superuser_may_publish(self):
        response = self.patch(self.root, "public")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.visibility_now(), Visibility.PUBLIC.value)
