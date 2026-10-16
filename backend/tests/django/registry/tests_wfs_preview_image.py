import json
from copy import deepcopy
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.gis.geos import MultiPolygon, Polygon
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from guardian.shortcuts import assign_perm
from lxml import etree
from PIL import Image
from registry.models.security import AllowedWebFeatureServiceOperation
from registry.models.service import WebFeatureService
from requests import Session
from rest_framework.test import APIClient
from tests.django.registry.tests_live_preview import WFS, capabilities, response


def thumbnail_capabilities():
    return capabilities("WFS").replace(
        b"wfs:Capabilities", b"wfs:WFS_Capabilities",
    ).replace(
        b'<ows:Operation name="GetFeature">',
        b'<ows:Operation name="GetFeature"><ows:DCP><ows:HTTP>'
        b'<ows:Get xlink:href="https://registered.example/features"/>'
        b'</ows:HTTP></ows:DCP>',
    ).replace(
        b'</DefaultCRS>',
        b'</DefaultCRS><ows:WGS84BoundingBox><ows:LowerCorner>-2 0</ows:LowerCorner>'
        b'<ows:UpperCorner>4 8</ows:UpperCorner></ows:WGS84BoundingBox>',
    )


class WfsPreviewImageTests(TestCase):
    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json", "test_wfs_proxy.json"]

    def setUp(self):
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        override = override_settings(MEDIA_ROOT=media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.user = get_user_model().objects.create_superuser(username="thumbnail", password="test")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.client.credentials(HTTP_ACCEPT="image/png", HTTP_AUTHORIZATION="Token caller-secret")
        self.wfs = WebFeatureService.objects.get(pk=WFS)
        self.set_capabilities(thumbnail_capabilities())
        self.wfs.featuretypes.update(is_active=True)
        for operation in self.wfs.operation_urls.all():
            operation.url = f"https://registered.example/{operation.operation}-{operation.method}"
            operation.save()
        self.features = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [1, 1]}}
        ]}
        send = patch("requests.sessions.Session.send", return_value=response(json.dumps(self.features).encode()))
        self.send = send.start()
        self.addCleanup(send.stop)

    def set_capabilities(self, content):
        self.wfs.xml_backup_file = SimpleUploadedFile("thumbnail.xml", content)
        self.wfs.save()

    def request(self, **params):
        return self.client.get(f"/api/registry/wfs/{self.wfs.pk}/preview-image", params)

    def test_image_request_automatically_selects_type_and_returns_uncached_png(self):
        result = self.request()
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.headers["Content-Type"], "image/png")
        self.assertEqual(result.headers["Cache-Control"], "no-store")
        with Image.open(BytesIO(result.content)) as image:
            self.assertEqual(image.format, "PNG")
            self.assertEqual(image.size, (512, 256))
        self.send.assert_called_once()
        sent = self.send.call_args.args[0]
        params = parse_qs(urlsplit(sent.url).query)
        self.assertEqual(params["TYPENAMES"], ["ms:Countries"])
        self.assertEqual(params["COUNT"], ["500"])
        self.assertEqual(params["OUTPUTFORMAT"], ["application/json"])
        self.assertEqual(params["BBOX"], ["0.0,-2.0,8.0,4.0,EPSG:4326"])
        self.assertIn("/30-1", sent.url)
        self.assertNotIn("caller-secret", str(sent.headers))
        self.assertFalse(self.send.call_args.kwargs["allow_redirects"])

    def test_service_details_expose_absolute_preview_url_without_upstream_read(self):
        self.client.credentials(HTTP_ACCEPT="application/vnd.api+json")
        result = self.client.get(
            f"/api/registry/wfs/{self.wfs.pk}", {"fields[WebFeatureService]": "previewUrl"},
        )
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()["data"]["attributes"]["previewUrl"],
                         f"http://testserver/api/registry/wfs/{self.wfs.pk}/preview-image")
        self.send.assert_not_called()

    def test_requested_dimensions_are_applied_and_invalid_dimensions_do_not_read_upstream(self):
        result = self.request(width=160, height=80)
        self.assertEqual(result.status_code, 200, result.content)
        with Image.open(BytesIO(result.content)) as image:
            self.assertEqual(image.size, (160, 80))
        self.send.reset_mock()
        for params in ({"width": 0}, {"height": 2049}, {"width": "invalid"}):
            with self.subTest(params=params):
                result = self.request(**params)
                self.assertEqual(result.status_code, 400, result.content)
        self.send.assert_not_called()

    def test_incompatible_capabilities_and_disabled_types_have_no_thumbnail(self):
        base = thumbnail_capabilities()
        for content in (
            base.replace(b"application/json", b"application/gml+xml"),
            base.replace(b"urn:ogc:def:crs:EPSG::4326", b"EPSG:25832"),
            base.replace(b"ows:WGS84BoundingBox", b"ows:UnknownBoundingBox"),
        ):
            with self.subTest(capabilities=content):
                self.set_capabilities(content)
                result = self.request()
                self.assertEqual(result.status_code, 422, result.content)
                self.assertEqual(result.json()["error"], "unavailable")
        self.set_capabilities(base)
        self.wfs.featuretypes.update(is_active=False)
        self.assertEqual(self.request().status_code, 422)
        self.send.assert_not_called()

    def test_empty_feature_sample_has_no_thumbnail(self):
        self.send.return_value = response(b'{"type":"FeatureCollection","features":[]}')
        result = self.request()
        self.assertEqual(result.status_code, 422, result.content)
        self.assertEqual(result.json()["error"], "unavailable")

    def test_service_permissions_and_disabled_service_prevent_upstream_reads(self):
        user = get_user_model().objects.create_user(username="no-thumbnail")
        self.client.force_authenticate(user)
        self.assertEqual(self.request().status_code, 403)
        self.client.force_authenticate(self.user)
        WebFeatureService.objects.filter(pk=self.wfs.pk).update(is_active=False)
        self.assertEqual(self.request().status_code, 423)
        self.send.assert_not_called()

    def test_capabilities_query_parameters_cannot_bypass_spatial_permissions(self):
        user = get_user_model().objects.create_user(username="spatial-thumbnail-data")
        group = Group.objects.create(name="spatial-thumbnail-readers")
        user.groups.add(group)
        assign_perm("view_webfeatureservice", user, self.wfs)
        allowed = AllowedWebFeatureServiceOperation.objects.create(
            secured_service=self.wfs, allowed_area=MultiPolygon(Polygon.from_bbox((0, 0, 4, 8)), srid=4326))
        allowed.operations.add(30)
        allowed.secured_feature_types.add(self.wfs.featuretypes.get(identifier="ms:Countries"))
        allowed.allowed_groups.add(group)
        self.set_capabilities(thumbnail_capabilities().replace(
            b'https://registered.example/features"',
            b'https://registered.example/features?request=DescribeFeatureType"',
        ))
        self.client.force_authenticate(user)
        outside = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [90, 45]}}
        ]}
        self.send.return_value = response(json.dumps(outside).encode())

        with patch("registry.helper.preview.adjust_axis_order", side_effect=lambda geometry: geometry):
            result = self.request()

        self.assertEqual(result.status_code, 403, result.content)
        self.send.assert_called_once()
        self.assertEqual(self.send.call_args.args[0].method, "POST")

    def test_preview_selects_a_later_feature_type_allowed_for_the_caller(self):
        root = etree.fromstring(thumbnail_capabilities())
        first = root.find("FeatureTypeList/FeatureType")
        second = deepcopy(first)
        second.find("Name").text = "ms:Rivers"
        first.getparent().append(second)
        self.set_capabilities(etree.tostring(root))
        user = get_user_model().objects.create_user(username="rivers-thumbnail")
        group = Group.objects.create(name="rivers-thumbnail-readers")
        user.groups.add(group)
        assign_perm("view_webfeatureservice", user, self.wfs)
        allowed = AllowedWebFeatureServiceOperation.objects.create(secured_service=self.wfs)
        allowed.operations.add(30)
        allowed.secured_feature_types.add(self.wfs.featuretypes.get(identifier="ms:Rivers"))
        allowed.allowed_groups.add(group)
        self.client.force_authenticate(user)

        result = self.request()

        self.assertEqual(result.status_code, 200, result.content)
        self.send.assert_called_once()
        sent = self.send.call_args.args[0]
        self.assertEqual(sent.method, "GET")
        self.assertEqual(parse_qs(urlsplit(sent.url).query)["TYPENAMES"], ["ms:Rivers"])

    def test_whitespace_in_advertised_format_and_crs_does_not_prevent_thumbnail(self):
        self.set_capabilities(thumbnail_capabilities().replace(
            b">application/json<", b">\n application/json \n<",
        ).replace(
            b">urn:ogc:def:crs:EPSG::4326<", b">\n urn:ogc:def:crs:EPSG::4326 \n<",
        ))

        result = self.request()

        self.assertEqual(result.status_code, 200, result.content)
        params = parse_qs(urlsplit(self.send.call_args.args[0].url).query)
        self.assertEqual(params["OUTPUTFORMAT"], ["application/json"])
        self.assertEqual(params["SRSNAME"], ["EPSG:4326"])

    def test_upstream_authentication_is_used_without_forwarding_caller_headers(self):
        session = Session()
        session.auth = ("upstream", "password")
        with patch.object(WebFeatureService, "get_session_for_request", return_value=session):
            result = self.request()
        self.assertEqual(result.status_code, 200, result.content)
        headers = self.send.call_args.args[0].headers
        self.assertTrue(headers["Authorization"].startswith("Basic "))
        self.assertNotIn("caller-secret", str(headers))
        self.assertNotIn("Cookie", headers)

    def test_upstream_failures_and_response_limits_do_not_produce_images(self):
        self.send.return_value = response(b"unavailable", status=503)
        self.assertEqual(self.request().status_code, 502)
        self.send.return_value = response(json.dumps(self.features).encode())
        with patch("registry.helper.preview.RESPONSE_LIMIT", 16):
            result = self.request()
        self.assertEqual(result.status_code, 502, result.content)
        self.assertEqual(result.json()["error"], "limit")

    def test_spatial_rules_are_caller_scoped_and_reject_outside_features(self):
        user = get_user_model().objects.create_user(username="restricted-thumbnail")
        group = Group.objects.create(name="thumbnail-area")
        user.groups.add(group)
        assign_perm("view_webfeatureservice", user, self.wfs)
        element = self.wfs.featuretypes.get(identifier="ms:Countries")
        allowed = AllowedWebFeatureServiceOperation.objects.create(
            secured_service=self.wfs, allowed_area=MultiPolygon(Polygon.from_bbox((0, 0, 4, 8)), srid=4326))
        allowed.operations.add(30)
        allowed.secured_feature_types.add(element)
        allowed.allowed_groups.add(group)
        other = AllowedWebFeatureServiceOperation.objects.create(
            secured_service=self.wfs, allowed_area=MultiPolygon(Polygon.from_bbox((80, 40, 100, 50)), srid=4326))
        other.operations.add(30)
        other.secured_feature_types.add(element)
        other.allowed_groups.add(Group.objects.create(name="unrelated-thumbnail-area"))
        self.client.force_authenticate(user)
        with patch("registry.helper.preview.adjust_axis_order", side_effect=lambda geometry: geometry):
            result = self.request()
        self.assertEqual(result.status_code, 200, result.content)
        sent = self.send.call_args.args[0]
        self.assertEqual(sent.method, "POST")
        root = etree.fromstring(sent.body)
        self.assertEqual(root.get("count"), "500")
        self.assertEqual(root.xpath("count(//*[local-name()='Within'])"), 1)
        self.assertNotIn(b"100", sent.body)
        outside = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [90, 45]}}
        ]}
        self.send.return_value = response(json.dumps(outside).encode())
        with patch("registry.helper.preview.adjust_axis_order", side_effect=lambda geometry: geometry):
            result = self.request()
        self.assertEqual(result.status_code, 403, result.content)
        user.groups.clear()
        self.send.reset_mock()
        self.assertEqual(self.request().status_code, 403)
        self.send.assert_not_called()
