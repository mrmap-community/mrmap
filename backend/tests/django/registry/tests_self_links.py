"""The self link of a proxy setting and the serializer of the operation urls (#1475).

Both are wiring mistakes a green endpoint hid:

*the WFS proxy setting linked to the WMS route:*
    `WebFeatureServiceProxySettingSerializer.url` was the field of its WMS
    neighbour copied over, so a WFS proxy setting answered a self link below
    `security/wms-proxy-settings`. Both routes exist, so nothing failed:
    following the link of a WFS setting read the WMS setting with the same id,
    or answered 404.

*the operation urls had two serializers:*
    `CatalogueServiceOperationUrlSerializer` was defined twice in
    `registry/serializers/service.py`. The class body of
    `CatalogueServiceSerializer` above the second definition captured the
    first, plain one, while `registry/views/service.py` -- importing once the
    module had run -- got the second, which is the one declaring its `service`
    relation with the labels of the model. Which of the two an
    `include=operationUrls` answered was decided by where a class happened to
    sit in the file. There is one definition now, named by its path in the
    include because it is declared below the serializer including it.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from registry.models.security import WebFeatureServiceProxySetting
from registry.models.service import (
    CatalogueService, WebFeatureService)
from registry.serializers.service import (
    CatalogueServiceOperationUrlSerializer, CatalogueServiceSerializer)
from rest_framework.test import APIClient

JSONAPI = "application/vnd.api+json"

#: the second WFS of ``test_wfs.json``, so no proxy setting of the fixture
#: of the other protocol shares its service's id
WFS_ONE = "72bda0a1-a808-48ba-ab1d-bf03081263df"

#: the catalogue of ``test_csw.json``, with two operation urls
CSW_ONE = "9cc4889d-0cd4-4c3b-8975-58de6d30db41"


class SelfLinkTest(TestCase):
    """An authenticated JSON:API client, the one both resources answer to."""

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(get_user_model().objects.create_superuser(
            username="self-links", password="test"))
        self.client.credentials(HTTP_ACCEPT=JSONAPI)


class WfsProxySettingSelfLinkTest(SelfLinkTest):
    """`links.self` of `security/wfs-proxy-settings` (#1475)."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wfs.json"]

    def test_self_link_names_the_wfs_proxy_settings_route(self):
        setting = WebFeatureServiceProxySetting.objects.create(
            secured_service=WebFeatureService.objects.get(pk=WFS_ONE))

        response = self.client.get(
            f"/api/registry/security/wfs-proxy-settings/{setting.pk}")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response.json()["data"]["links"]["self"],
            f"http://testserver/api/registry/security/wfs-proxy-settings/{setting.pk}")


class CatalogueServiceOperationUrlSerializerTest(SelfLinkTest):
    """One serializer answers the `operationUrls` include (#1475)."""

    fixtures = ["test_users.json", "test_keywords.json", "test_csw.json"]

    def test_include_and_module_name_answer_one_serializer(self):
        """the include no longer keeps a serializer the module no longer names"""
        self.assertIs(
            CatalogueServiceSerializer.included_serializers["operation_urls"],
            CatalogueServiceOperationUrlSerializer)

    def test_operation_urls_are_included(self):
        """the path naming the include resolves: the answer carries its resources"""
        response = self.client.get(
            f"/api/registry/csw/{CSW_ONE}", {"include": "operationUrls"})

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            sorted(row["id"] for row in response.json()["included"]
                   if row["type"] == "CatalogueServiceOperationUrl"),
            sorted(str(url.pk) for url in CatalogueService.objects.get(
                pk=CSW_ONE).operation_urls.all()))
