"""The permission floor of the REST API (#1444).

``REST_FRAMEWORK`` named fourteen keys and no ``DEFAULT_PERMISSION_CLASSES``.
DRF's default is an empty list, whose answer to every permission question is
"allowed", so a view class which declared no permission of its own was public
*and writable*: the metadata lookups, the historical endpoints, the groups, the
schedules and the proxy configuration of a service answered an anonymous
``POST``, ``PATCH`` or ``DELETE`` with whatever the handler made of it.

The floor below is what such a view falls back to now: reading stays open, a
write needs an identity. Views which decide access per object still name their
own classes; this is only the fallback underneath them.

Two boundaries of that floor matter and are pinned here:

* an anonymous read of a view without a declared class is answered the way it
  always was - the frontend's pickers and the public map read these endpoints;
* the security proxy is *not* subject to the floor. OGC's XML POST binding
  carries a ``GetMap`` or ``GetFeature``, which are reads, over HTTP POST, and a
  rule keyed on the verb would refuse the anonymous map client the WMS and WFS
  bindings are specified for. The proxy therefore names no permission class on
  purpose and answers by the service's own security rules
  (`registry/managers/security.py` and the ``AllowedWebMapServiceOperation``
  rows), which is what its last test asserts.

A denial of the floor is answered 403 and not 401: mrmap's
``DEFAULT_AUTHENTICATION_CLASSES`` starts with ``SessionAuthentication``, which
offers no ``WWW-Authenticate`` header, and DRF downgrades an unauthenticated
denial to 403 without one (see ``tests/django/accounts/test_logout_revokes_token.py``).
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from lxml import etree
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.settings import api_settings
from rest_framework.test import APIClient

from registry.proxy.wfs_proxy import WebFeatureServiceProxy
from registry.proxy.wms_proxy import WebMapServiceProxy
from registry.views.metadata import KeywordViewSet

#: A view which declares no permission of its own (#1444). The frontend's
#: keyword pickers read it without a login; it must not answer writes that way.
KEYWORDS_URL = "/api/registry/keywords"
JSONAPI_ACCEPT = "application/vnd.api+json"

#: Any uuid will do: the request is refused before the proxy looks a service up.
WFS_PROXY_URL = "/mrmap-proxy/wfs/00000000-0000-0000-0000-000000000000"


class PermissionFloorTests(TestCase):
    """What a view without a declared class answers today."""

    def setUp(self):
        self.client = APIClient()
        # guardian maps an anonymous request to the user named AnonymousUser;
        # a TransactionTestCase run earlier in the process flushed the row
        # post_migrate created (see tests/AGENTS.md)
        get_user_model().objects.get_or_create(username="AnonymousUser")

    def test_the_floor_is_the_configured_default(self):
        self.assertEqual(
            [permission.__name__ for permission
             in api_settings.DEFAULT_PERMISSION_CLASSES],
            ["IsAuthenticatedOrReadOnly"])

    def test_a_view_naming_nothing_falls_back_to_the_floor(self):
        """The fallback is resolved on the view class, not only in settings.

        DRF binds ``permission_classes`` while ``APIView`` is imported, so this
        is what the endpoint actually asks; a settings key nobody imports would
        answer this test in red.
        """
        self.assertEqual(
            [permission.__name__ for permission in KeywordViewSet.permission_classes],
            [IsAuthenticatedOrReadOnly.__name__])

    def test_an_anonymous_read_of_the_view_is_still_answered(self):
        """Reading the lookups is open and stays open: only writes close."""
        response = self.client.get(KEYWORDS_URL, HTTP_ACCEPT=JSONAPI_ACCEPT)

        self.assertEqual(response.status_code, 200, response.content)

    def test_an_anonymous_write_of_the_view_is_refused(self):
        """The behaviour #1444 is about: no identity, no write."""
        response = self.client.post(
            KEYWORDS_URL,
            data={"data": {"type": "Keyword", "attributes": {"keyword": "anonymous"}}},
            format="vnd.api+json",
            HTTP_ACCEPT=JSONAPI_ACCEPT)

        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(
            response.json()["errors"][0]["code"], "not_authenticated")

    def test_a_logged_in_client_is_not_affected_by_the_floor(self):
        """The floor asks for an identity, not for a grant: the keyword add of
        ``add_keyword.feature`` stays green for a user without any grant."""
        user = get_user_model().objects.create_user(
            username="floor-probe", password="not-a-secret-pw1")
        self.client.force_authenticate(user=user)

        response = self.client.post(
            KEYWORDS_URL,
            data={"data": {"type": "Keyword", "attributes": {"keyword": "written"}}},
            format="vnd.api+json",
            HTTP_ACCEPT=JSONAPI_ACCEPT)

        self.assertEqual(response.status_code, 201, response.content)


class SecurityProxyIsNotInTheFloorTests(TestCase):
    """The proxy answers by the security model of the service, not by the floor."""

    def setUp(self):
        self.client = APIClient()
        get_user_model().objects.get_or_create(username="AnonymousUser")

    def test_both_proxies_declare_no_permission_class(self):
        """Explicitly none, which is something else than inheriting the default:
        the proxy's decision is the service's own and answers as an OGC report."""
        self.assertEqual(WebMapServiceProxy.permission_classes, [])
        self.assertEqual(WebFeatureServiceProxy.permission_classes, [])

    def test_an_anonymous_post_is_analysed_by_the_proxy_and_not_refused_by_the_floor(self):
        """An OGC client sends a read as a POST; the proxy must not answer it the
        way the API answers an anonymous write.

        The document asks for a GetFeature and names no ``version``, which the
        proxy refuses in ``initial`` - before it looks a service up, so no service
        is needed here and nothing remote is asked. That refusal is the point: only
        a request the proxy was allowed to analyse can be refused for a parameter
        it does not name. Under the floor the request never reaches that code and
        the answer is the ``Forbidden`` report the proxy's handler makes of a DRF
        refusal (``registry/proxy/mixins.py``).
        """
        get_feature = """
            <?xml version='1.0' encoding='UTF-8'?>
            <wfs:GetFeature
                xmlns:wfs="http://www.opengis.net/wfs/2.0"
                service="wfs">
                <wfs:Query typeNames="ms:Countries"/>
            </wfs:GetFeature>
        """

        response = self.client.post(
            WFS_PROXY_URL,
            data=get_feature.strip(),
            content_type="application/gml+xml; version=3.2")

        self.assertEqual(response.status_code, 400, response.content)
        exception = etree.fromstring(response.content).find(".//{*}Exception")
        self.assertIsNotNone(exception, response.content)
        self.assertEqual(
            exception.get("exceptionCode"), "MissingParameter", response.content)
        self.assertEqual(exception.get("locator"), "version", response.content)
