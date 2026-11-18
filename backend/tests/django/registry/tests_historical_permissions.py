"""The permission gate of the historical endpoints (#1449).

``HistoricalViewSetMixin`` declared no permission class of its own: it fell
back to the floor of #1444, which asks an identity of a write and nothing
more. Every authenticated caller could therefore ``PATCH`` an audit row —
rewriting the compliance record the history exists to prove (#741 premise).
The mixin now names ``DjangoObjectPermissionsOrAnonReadOnly`` and no longer
accepts ``PATCH`` at all:

* the reads stay exactly as they were: DRF asks nothing of safe methods, so
  the changelog keeps answering from the whole change log — what
  ``list_historical_webmapservices.feature:10`` pins for anonymous, pins
  unchanged for the new class;
* the anonymous ``PATCH`` ends at the gate with 403 ``not_authenticated``,
  an identity no longer suffices, and since ``patch`` left
  ``http_method_names`` even the break-glass superuser gets 405: nobody
  edits history, which is what the history is for.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
from registry.models.service import WebMapService
from registry.views.historical import (
    CatalogueServiceHistoricalViewSet, DatasetMetadataRecordHistoricalViewSet,
    FeatureTypeHistoricalViewSet, LayerHistoricalViewSet,
    ServiceMetadataRecordHistoricalViewSet,
    WebFeatureServiceHistoricalViewSet, WebMapServiceHistoricalViewSet)
from rest_framework.test import APIClient

JSONAPI_ACCEPT = "application/vnd.api+json"

#: every concrete viewset of the mixin, by the path it is registered under
HISTORICAL_ENDPOINTS = {
    "historical-wms": WebMapServiceHistoricalViewSet,
    "historical-layers": LayerHistoricalViewSet,
    "historical-wfs": WebFeatureServiceHistoricalViewSet,
    "historical-featuretypes": FeatureTypeHistoricalViewSet,
    "historical-csw": CatalogueServiceHistoricalViewSet,
    "historical-dataset-metadata": DatasetMetadataRecordHistoricalViewSet,
    "historical-service-metadata": ServiceMetadataRecordHistoricalViewSet,
}

#: the tampered payload an attempt to rewrite an audit row would carry
TAMPER = {
    "data": {
        "type": "HistoricalWebMapService",
        "attributes": {"title": "tampered"},
    },
}


class HistoricalPermissionTests(TestCase):
    fixtures = ["test_users.json", "test_keywords.json", "test_wms.json"]

    @classmethod
    def setUpTestData(cls):
        cls.reader = get_user_model().objects.get(username="User1")
        cls.admin = get_user_model().objects.create_superuser(
            "historical-admin", password="not-a-secret-pw1")
        # the fixture carries the creation record and one change of WMS1
        cls.audit_row = WebMapService.change_log.order_by("history_date").first()

    def setUp(self):
        self.client = APIClient()
        # guardian maps an anonymous request to the user named AnonymousUser;
        # a TransactionTestCase run earlier in the process flushed the row
        # post_migrate created (see tests/AGENTS.md)
        get_user_model().objects.get_or_create(username="AnonymousUser")

    # -- what the viewsets declare ------------------------------------------

    def test_every_viewset_names_the_gate_and_no_write_verb(self):
        """The fix on the mixin, asserted on all seven concrete classes.

        Asserted on the classes and not only through requests: the requests
        below pin one observable answer each, this pins the declaration every
        one of them reads from.
        """
        for path, viewset in HISTORICAL_ENDPOINTS.items():
            with self.subTest(viewset=viewset.__name__):
                self.assertEqual(
                    viewset.permission_classes,
                    [DjangoObjectPermissionsOrAnonReadOnly],
                    f"{path} does not gate through the facade class")
                self.assertEqual(
                    list(viewset.http_method_names),
                    ["get", "head", "options"],
                    f"{path} still accepts a write verb")

    # -- the reads the changelogs live off -----------------------------------

    def test_anonymous_reads_of_the_lists_stay_open(self):
        for path in HISTORICAL_ENDPOINTS:
            with self.subTest(path=path):
                response = self.client.get(
                    f"/api/registry/{path}", HTTP_ACCEPT=JSONAPI_ACCEPT)
                self.assertEqual(response.status_code, 200, response.content)

    def test_options_still_answers_under_the_new_gate(self):
        """OPTIONS is a safe method: the gate lets it, as the mixin promised
        to preserve the verb before."""
        response = self.client.options(
            "/api/registry/historical-wms", HTTP_ACCEPT=JSONAPI_ACCEPT)
        self.assertEqual(response.status_code, 200, response.content)

    # -- the writes end ------------------------------------------------------

    def test_an_anonymous_patch_is_refused_before_the_method_question(self):
        """No identity, no answer — the permission gate runs before dispatch.

        The client learns it has to identify itself, which is the answer the
        floor of #1444 gave and which stays: what closes additionally is the
        write of the caller who DOES identify itself.
        """
        for path in HISTORICAL_ENDPOINTS:
            for url in (f"/api/registry/{path}",
                        f"/api/registry/{path}/00000000-0000-0000-0000-000000000000"):
                with self.subTest(url=url):
                    response = self.client.patch(
                        url, data=TAMPER, format="vnd.api+json",
                        HTTP_ACCEPT=JSONAPI_ACCEPT)
                    self.assertEqual(response.status_code, 403, response.content)
                    self.assertEqual(
                        response.json()["errors"][0]["code"],
                        "not_authenticated")

    def test_no_authenticated_caller_can_patch_an_audit_row(self):
        """Even the break-glass superuser gets 405: PATCH left the endpoint.

        Under the floor any identity could rewrite the row; the gate of the
        facade would now ask an object grant over the audit row itself, and
        the verb is gone before either question is answered.
        """
        url = f"/api/registry/historical-wms/{self.audit_row.pk}"
        for user in (self.reader, self.admin):
            with self.subTest(user=user.username):
                self.client.force_authenticate(user=user)
                response = self.client.patch(
                    url, data=TAMPER, format="vnd.api+json",
                    HTTP_ACCEPT=JSONAPI_ACCEPT)
                self.assertEqual(response.status_code, 405, response.content)
        # and the row still reads what the fixture wrote
        fresh = WebMapService.change_log.get(pk=self.audit_row.pk)
        self.assertNotEqual(fresh.title, "tampered")

    def test_the_gate_does_not_narrow_the_anonymous_changelog(self):
        """Reads answer from the whole change log, as before the gate.

        DRF's object gate asks nothing of safe methods (the 404-vs-403 shape
        of ``has_object_permission`` is decided by the required read
        permission, which the class does not ask on GET), so what keeps
        history readable for the frontend changelogs is the same
        unpermission-filtered change-log queryset the pinned feature counts.
        Asserting the count against the table — not a made-up number — is
        the pin that the new class did not start filtering the answer.
        """
        response = self.client.get(
            "/api/registry/historical-wms", HTTP_ACCEPT=JSONAPI_ACCEPT)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response.json()["meta"]["pagination"]["count"],
            WebMapService.change_log.count())
