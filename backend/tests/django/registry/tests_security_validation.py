"""A geometry the column cannot hold is a bad request, not a broken write (#1148).

Both guards of the security endpoints live in the database: the area of an allowed operation must
not be EMPTY (`..._allowed_area_not_empty`) and a response may only be logged while the proxy
camouflages (`..._log_response_without_camouflage`). Until now neither guard was expressed where a
request is validated, so the row was written and refused by PostgreSQL. A `CheckViolation` is not a
DRF exception, so the client of a refused payload got HTTP 500 with a traceback -- for the area on
both `allowed-*-operations` endpoints, for the proxy settings on `wms-proxy-settings` -- while the
constraint itself was used as an error path instead of an invariant.

What is pinned here: a payload whose geometry the column cannot store is answered with 400 and
names what was refused, a valid area is written as it always was (201, never a 500), an area can
stay absent, and both forms the schema documents for a geometry -- the GeoJSON object and the
serialized string -- reach the same answer.
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

JSONAPI = "application/vnd.api+json"

#: the Berlin box of the harness which reported #1148
BERLIN = [[[
    [12.6, 52.4], [13.4, 52.4], [13.4, 52.9], [12.6, 52.9], [12.6, 52.4]]]]

#: an area without a single polygon: what a client which cleared its drawing area sends
EMPTY_MULTI_POLYGON = {"type": "MultiPolygon", "coordinates": []}
VALID_MULTI_POLYGON = {"type": "MultiPolygon", "coordinates": BERLIN}
#: a POLYGON is no MULTIPOLYGON, and the column of the area stores nothing else
VALID_POLYGON = {"type": "Polygon", "coordinates": BERLIN[0]}

#: handed to `payload()` to leave `allowedArea` out of the request
UNSET = object()

#: both protocols guard the same field of their allowed operations
PROTOCOLS = {
    "wms": {
        "type": "AllowedWebMapServiceOperation",
        "service": "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3",
        "service_type": "WebMapService",
        "contents": [
            "16b93d90-6e2e-497a-b26d-cadbe60ab76e", "226e655b-b6cd-48a4-95e2-8bfe1c933790",
            "c4ecdb87-31f4-4f30-8559-f577c8c59d08", "ab645130-241d-4d6b-84c0-ab49c4bc6e4c",
            "89fa6202-d252-4fb4-a772-22e2a441b312", "d6e47039-b08a-4183-ae51-667083b8a803",
            "4fdda4c4-c7bb-4525-a14d-f555ce0a9217", "e95c2af1-9713-45fa-b6d4-7bb7e9813fdf"],
        "content_relation": "securedLayers",
        "content_type": "Layer",
        "operations": [20, 21],
        "operation_type": "WebMapServiceOperation",
    },
    "wfs": {
        "type": "AllowedWebFeatureServiceOperation",
        "service": "9cc4889d-0cd4-4c3b-8975-58de6d30db41",
        "service_type": "WebFeatureService",
        "contents": [
            "efba476a-d3ff-44f8-a0db-7f2c811f7247", "fa8713a6-875f-48b4-95f2-f9bb7cf47001",
            "b9f6c9d4-0acf-49c0-923f-dced0eeed5da", "f278f616-739f-4a88-8885-1cfed5e9076c"],
        "content_relation": "securedFeatureTypes",
        "content_type": "FeatureType",
        "operations": [30],
        "operation_type": "WebFeatureServiceOperation",
    },
}


def allowed_operation_payload(protocol, area=UNSET):
    """The JSON:API body of an allowed operation for one protocol, with the area asked for."""
    rule = PROTOCOLS[protocol]
    attributes = {"description": "spatial rule"}
    if area is not UNSET:
        attributes["allowedArea"] = area
    return {"data": {
        "type": rule["type"],
        "attributes": attributes,
        "relationships": {
            "operations": {"data": [
                {"id": value, "type": rule["operation_type"]} for value in rule["operations"]]},
            "securedService": {"data": {
                "id": rule["service"], "type": rule["service_type"]}},
            rule["content_relation"]: {"data": [
                {"id": pk, "type": rule["content_type"]} for pk in rule["contents"]]},
        }}}


class AllowedAreaTest(TestCase):
    """`allowedArea` of `allowed-wms-operations` and `allowed-wfs-operations` (#1148)."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json", "test_wfs.json"]

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(get_user_model().objects.create_superuser(
            username="area-guard", password="test"))
        self.client.credentials(HTTP_ACCEPT=JSONAPI)

    def post(self, protocol, area=UNSET):
        return self.client.post(
            f"/api/registry/security/allowed-{protocol}-operations",
            allowed_operation_payload(protocol, area), format="vnd.api+json")

    def test_valid_area_is_written(self):
        """a request carrying a valid non-empty area is written, as the majority always was"""
        for protocol in PROTOCOLS:
            with self.subTest(protocol=protocol):
                response = self.post(protocol, VALID_MULTI_POLYGON)
                self.assertEqual(response.status_code, 201, response.content)

    def test_valid_area_as_serialized_string_is_written(self):
        """the schema documents a geometry as a serialized string as well as an object"""
        for protocol in PROTOCOLS:
            with self.subTest(protocol=protocol):
                response = self.post(protocol, json.dumps(VALID_MULTI_POLYGON))
                self.assertEqual(response.status_code, 201, response.content)

    def test_area_can_stay_absent(self):
        """an operation without a spatial restriction stays expressible: no area, no constraint"""
        for protocol in PROTOCOLS:
            with self.subTest(protocol=protocol):
                response = self.post(protocol)
                self.assertEqual(response.status_code, 201, response.content)

    def test_area_can_be_null(self):
        for protocol in PROTOCOLS:
            with self.subTest(protocol=protocol):
                response = self.post(protocol, None)
                self.assertEqual(response.status_code, 201, response.content)

    def test_empty_area_is_refused(self):
        """the EMPTY area the check constraint of the column refuses is answered with 400"""
        for protocol in PROTOCOLS:
            with self.subTest(protocol=protocol):
                response = self.post(protocol, EMPTY_MULTI_POLYGON)
                self.assertEqual(response.status_code, 400, response.content)
                details = " ".join(
                    str(error.get("detail")) for error in response.json()["errors"])
                self.assertIn("Empty", details)

    def test_area_of_another_type_is_refused(self):
        """a POLYGON is not stored by a MULTIPOLYGON column either"""
        for protocol in PROTOCOLS:
            with self.subTest(protocol=protocol):
                response = self.post(protocol, VALID_POLYGON)
                self.assertEqual(response.status_code, 400, response.content)
                details = " ".join(
                    str(error.get("detail")) for error in response.json()["errors"])
                self.assertIn("Polygon", details)


class ProxySettingConstraintTest(TestCase):
    """`camouflage` and `logResponse` of `wms-proxy-settings` (#1148)."""

    SERVICE = "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"

    fixtures = ["test_users.json", "test_keywords.json", "test_wms.json"]

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(get_user_model().objects.create_superuser(
            username="proxy-guard", password="test"))
        self.client.credentials(HTTP_ACCEPT=JSONAPI)

    def setting_payload(self, attributes, pk=None):
        data = {"type": "WebMapServiceProxySetting", "attributes": dict(attributes)}
        if pk is not None:
            data["id"] = str(pk)
        else:
            data["relationships"] = {"securedService": {"data": {
                "id": self.SERVICE, "type": "WebMapService"}}}
        return {"data": data}

    def create(self, **attributes):
        return self.client.post(
            "/api/registry/security/wms-proxy-settings",
            self.setting_payload(attributes), format="vnd.api+json")

    def patch(self, pk, **attributes):
        return self.client.patch(
            f"/api/registry/security/wms-proxy-settings/{pk}",
            self.setting_payload(attributes, pk=pk), format="vnd.api+json")

    def test_logging_without_camouflage_is_refused(self):
        """the pair the check constraint of the table refuses is answered with 400"""
        response = self.create(logResponse=True, camouflage=False)
        self.assertEqual(response.status_code, 400, response.content)
        details = " ".join(
            str(error.get("detail")) for error in response.json()["errors"])
        self.assertIn("log_response_without_camouflage", details)

    def test_logging_with_camouflage_is_written(self):
        response = self.create(logResponse=True, camouflage=True)
        self.assertEqual(response.status_code, 201, response.content)

    def test_a_setting_can_be_written_without_either_switch(self):
        response = self.create()
        self.assertEqual(response.status_code, 201, response.content)

    def test_logging_can_be_switched_on_for_a_camouflaged_service(self):
        created = self.create(camouflage=True).json()["data"]["id"]
        response = self.patch(created, logResponse=True)
        self.assertEqual(response.status_code, 200, response.content)

    def test_logging_can_not_be_switched_on_without_camouflage(self):
        """a partial update which would leave the row in the refused combination is answered"""
        created = self.create(camouflage=False).json()["data"]["id"]
        response = self.patch(created, logResponse=True)
        self.assertEqual(response.status_code, 400, response.content)

    def test_camouflage_can_not_be_switched_off_while_logging(self):
        created = self.create(camouflage=True, logResponse=True).json()["data"]["id"]
        response = self.patch(created, camouflage=False)
        self.assertEqual(response.status_code, 400, response.content)
