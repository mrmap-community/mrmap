"""/api/schema documents the `sort` contract every list endpoint enforces.

The json:api `OrderingFilter` polices `sort` strictly: any term outside the
view's valid fields answers 400. Issue #944 measured that the generated schema
hid that parameter where a view declares no explicit `ordering_fields`
(drf-spectacular-jsonapi drops the parameter then) and documented it without
values where a view whitelists the fields as a tuple (only `list` and
"__all__" build an enum there). Both made a generated client guess.

These tests generate the schema the way `/api/schema` serves it and pin that
every paginated list operation documents `sort` with the enum of terms the
runtime accepts - and that the strict 400 for terms outside the enum is
unchanged (the contract the issue asked to document, not to relax).
"""
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APIClient

JSONAPI = "application/vnd.api+json"

#: list endpoints which documented no sort parameter at all before #944,
#: with the terms their runtime filter accepts (serializer fields, camelized,
#: each negatable) - one per view family (plain list, nested related list)
FORMERLY_HIDDEN = {
    "/api/accounts/groups": ["id", "userSet", "name", "permissions"],
    "/api/accounts/users/{UserId}/groups": ["id", "userSet", "name", "permissions"],
    "/api/registry/security/wms-authentication": [
        "id", "username", "password", "authType", "keyFile", "service"],
}

#: the list endpoints whose generic pickers render and sort by the display
#: string of the serializer (#1035); the viewsets whitelist it together with
#: the model fields, and the schema has to show the very term the pickers
#: send - the camelized `stringRepresentation`
DISPLAY_SORTED = {
    "/api/registry/keywords": ["id", "keyword", "stringRepresentation"],
    "/api/registry/layers/{LayerId}/keywords":
        ["id", "keyword", "stringRepresentation"],
    "/api/registry/time-extents": [
        "id", "begin", "end", "resolution", "isRelative",
        "stringRepresentation"],
    "/api/accounts/users": [
        "id", "username", "firstName", "lastName", "email", "isActive",
        "dateJoined", "stringRepresentation"],
    "/api/accounts/organizations": [
        "id", "name", "description", "personName", "email", "phone",
        "facsimile", "city", "postalCode", "addressType", "address",
        "stateOrProvince", "country", "stringRepresentation"],
    "/api/registry/harvesting/harvesting-jobs": [
        # #1080: phase and total_records joined the offer; date_created could
        # not join then - a sort that cannot sort shows a false arrow in the
        # table. #1079 filled the moment every run was made, which is what
        # brings it into the offer here. The progress of a run is the answer of
        # #1071, annotated on the way out, so it joins the offer with it (#1130)
        "id", "doneAt", "stringRepresentation", "phase", "totalRecords",
        "dateCreated", "progress"],
    "/api/notify/background-processes": ["id", "dateCreated", "progress"],
}

#: list endpoints whose `ordering_fields` tuple stayed an untyped string
#: parameter before #944 (the update viewsets share the tuple shape)
FORMERLY_UNTYPED = {
    "/api/registry/update/webmapservice-update-jobs":
        ["id", "dateCreated", "doneAt", "status"],
}

#: the hand-written whitelist of the alerts list; the schema parameter is
#: built from the very constant the view checks against (registry.views.alerts)
ALERT_SORT_TERMS = ["id", "severity", "occurredAt"]


def _paginated_list_operations(schema):
    """The GET operations which answer a paginated json:api resource list."""
    components = schema.get("components", {}).get("schemas", {})
    for path, item in schema.get("paths", {}).items():
        operation = item.get("get")
        if not operation:
            continue
        response = operation.get("responses", {}).get("200", {})
        response_schema = response.get("content", {}).get(JSONAPI, {}).get("schema", {})
        if "$ref" in response_schema:
            response_schema = components.get(response_schema["$ref"].split("/")[-1], {})
        properties = response_schema.get("properties", {})
        if "meta" not in properties or properties.get("data", {}).get("type") != "array":
            continue
        yield path, operation


def _sort_enum(operation):
    """The enum of sort terms the operation documents (None if it does not)."""
    sort_param = next(
        (param for param in operation.get("parameters", []) if param.get("name") == "sort"),
        None)
    if not sort_param:
        return None
    schema = sort_param.get("schema", {})
    return schema.get("enum") or schema.get("items", {}).get("enum")


def _negated(terms):
    return sorted(term for field in terms for term in (field, f"-{field}"))


class ListSortSchemaTests(SimpleTestCase):
    """The generated contract, run against the whole urlconf like /api/schema."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.schema = SchemaGenerator().get_schema(public=True)
        cls.list_operations = dict(_paginated_list_operations(cls.schema))

    def test_every_paginated_list_operation_documents_its_sort_enum(self):
        """No list endpoint may hide the sort its filter polices with 400s."""
        gaps = sorted(
            path for path, operation in self.list_operations.items()
            if not _sort_enum(operation))
        self.assertEqual(
            gaps, [],
            f"{len(gaps)} of {len(self.list_operations)} paginated list operations "
            f"document no sort enum: {gaps}")

    def test_every_sort_enum_answers_ascending_and_descending(self):
        """Every term is documented with its '-' counterpart (json:api sorting)."""
        for path, operation in sorted(self.list_operations.items()):
            with self.subTest(path=path):
                enum = _sort_enum(operation) or []
                for term in enum:
                    self.assertIn(f"-{term.lstrip('-')}", enum)

    def test_view_without_ordering_fields_documents_the_runtime_fields(self):
        """Views without explicit ordering_fields sort by the serializer fields.

        The filter validates against that fallback at runtime (DRF
        get_default_valid_fields) - the schema must show the same terms.
        """
        for path, fields in FORMERLY_HIDDEN.items():
            with self.subTest(path=path):
                enum = _sort_enum(self.schema["paths"][path]["get"])
                self.assertEqual(sorted(enum), _negated(fields))

    def test_tuple_ordering_fields_are_documented_as_enum(self):
        for path, fields in FORMERLY_UNTYPED.items():
            with self.subTest(path=path):
                enum = _sort_enum(self.schema["paths"][path]["get"])
                self.assertEqual(sorted(enum), _negated(fields))

    def test_the_display_string_sort_is_documented(self):
        """The pickers' `sort=stringRepresentation` is on the documented enum"""
        for path, fields in DISPLAY_SORTED.items():
            with self.subTest(path=path):
                enum = _sort_enum(self.schema["paths"][path]["get"])
                self.assertEqual(sorted(enum), _negated(fields))

    def test_alerts_list_documents_its_hand_written_whitelist(self):
        """The hand-written sort of the alerts list carries its terms, too."""
        from registry.views.alerts import SORT_FIELDS, SORT_TERMS
        enum = _sort_enum(self.schema["paths"]["/api/registry/service-alerts"]["get"])
        # the documented terms, the schema enum and the whitelist the view
        # checks against are one source - a change to one is a change to all
        self.assertEqual(set(enum), set(SORT_TERMS))
        self.assertEqual(set(enum), set(_negated(ALERT_SORT_TERMS)))
        self.assertEqual(set(SORT_FIELDS), {"id", "severity", "occurred_at"})


class ListSortContractTests(TestCase):
    """The strict runtime contract behind the newly documented enums."""

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="sortschema", password="test")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_sort_unknown_still_answers_400_on_the_formerly_hidden_lists(self):
        """Documenting the parameter must not loosen the strict validation."""
        for path in ("/api/registry/keywords", "/api/registry/security/wms-authentication",
                     "/api/registry/update/webmapservice-update-jobs"):
            with self.subTest(path=path):
                response = self.client.get(
                    path, {"page[size]": 1, "sort": "created_at"}, HTTP_ACCEPT=JSONAPI)
                self.assertEqual(response.status_code, 400, response.content)
                self.assertEqual(response.json()["errors"][0]["code"], "invalid")

    def test_documented_terms_are_accepted_by_the_endpoint(self):
        """A term inside the documented enum is a valid request (200)."""
        for path in ("/api/registry/keywords", "/api/registry/security/wms-authentication",
                     "/api/registry/update/webmapservice-update-jobs"):
            with self.subTest(path=path):
                response = self.client.get(
                    path, {"page[size]": 1, "sort": "id"}, HTTP_ACCEPT=JSONAPI)
                self.assertEqual(response.status_code, 200, response.content)

    def test_alerts_list_still_rejects_a_sort_outside_its_documented_terms(self):
        response = self.client.get(
            reverse("registry:service-alert-list"), {"sort": "name"}, HTTP_ACCEPT=JSONAPI)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(
            response.json()["errors"][0]["detail"], "Invalid alert sort field.")

    def test_alerts_list_accepts_its_documented_terms(self):
        for sort in ALERT_SORT_TERMS + [f"-{term}" for term in ALERT_SORT_TERMS]:
            with self.subTest(sort=sort):
                response = self.client.get(
                    reverse("registry:service-alert-list"), {"sort": sort},
                    HTTP_ACCEPT=JSONAPI)
                self.assertEqual(response.status_code, 200, response.content)
