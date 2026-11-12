"""HTTP caching of the OpenAPI schema document (#946).

The SPA loads ``/api/schema`` on every boot; the document is megabytes in
size and does not depend on the requesting user. These tests pin the two
properties that make it cheap to ship repeatedly:

* the document generated for an anonymous request is byte-identical to the
  one generated for an authenticated request - the honesty precondition of
  ``Vary`` without ``Authorization``/``Cookie`` and of ``Cache-Control:
  public``, and
* the response carries a strong ``ETag`` so a reload revalidates with
  ``If-None-Match`` to a 304, while anonymous access keeps answering the
  document it answers today.

The requests go through the full stack (URLconf, ``cache_page`` wrap,
middleware) because the Vary and Cache-Control additions that the test
guards against are exactly what the cache decorator contributes. The
``local-memory`` cache is cleared between generations so an assertion
never measures a recycled cache entry.
"""

from django.contrib.auth import get_user_model
from django.core.cache import caches
from django.test import Client, TestCase

SCHEMA_URL = "/api/schema"


class OpenApiSchemaCachingTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = get_user_model().objects.create_user(
            username="schema-cache-probe", password="not-a-secret-pw1")
        # knox returns the full key only alongside the created row.
        from knox.models import AuthToken
        _, key = AuthToken.objects.create(cls.user)
        cls.auth_header = f"Token {key}"

    def setUp(self):
        # Every test that wants a freshly *generated* document must not
        # inherit the page cache entry of its predecessor.
        caches["local-memory"].clear()
        self.client = Client()

    def _vary(self, response):
        return [
            value.strip().lower()
            for value in response.headers.get("Vary", "").split(",")
            if value.strip()]

    def test_anonymous_access_still_answers_the_document(self):
        """The serve-public behaviour of the spectacular view is unchanged."""
        response = self.client.get(SCHEMA_URL)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"openapi", response.content)

    def test_the_document_is_not_per_user(self):
        """Anonymous and authenticated generation answer byte-identical."""
        anonymous = self.client.get(SCHEMA_URL)
        self.assertEqual(anonymous.status_code, 200)
        caches["local-memory"].clear()
        authenticated = self.client.get(
            SCHEMA_URL, HTTP_AUTHORIZATION=self.auth_header)
        self.assertEqual(authenticated.status_code, 200)
        self.assertEqual(anonymous.content, authenticated.content)
        self.assertEqual(
            anonymous.headers.get("ETag"), authenticated.headers.get("ETag"))

    def test_the_response_declares_itself_public_and_revalidatable(self):
        response = self.client.get(
            SCHEMA_URL, HTTP_AUTHORIZATION=self.auth_header)
        cache_control = response.headers.get("Cache-Control", "")
        self.assertIn("public", cache_control)
        self.assertIn("max-age=900", cache_control)
        etag = response.headers.get("ETag", "")
        # A strong validator: quoted, without the W/ prefix.
        self.assertTrue(etag.startswith('"') and not etag.startswith('W/'),
                        f"not a strong tag: {etag!r}")
        self.assertIn("sha256-", etag)

    def test_an_authenticated_request_does_not_vary_on_the_credentials(self):
        response = self.client.get(
            SCHEMA_URL, HTTP_AUTHORIZATION=self.auth_header)
        vary = self._vary(response)
        self.assertNotIn("authorization", vary)
        self.assertNotIn("cookie", vary)

    def test_if_none_match_with_the_current_tag_is_answered_with_304(self):
        response = self.client.get(
            SCHEMA_URL, HTTP_AUTHORIZATION=self.auth_header)
        etag = response.headers.get("ETag")
        # The page cache entry has to be regenerated to evaluate the tag -
        # the cache_page wrap serves a hit before the view is consulted.
        caches["local-memory"].clear()
        revalidation = self.client.get(
            SCHEMA_URL, HTTP_AUTHORIZATION=self.auth_header,
            HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(revalidation.status_code, 304)
        self.assertEqual(revalidation.content, b"")
        self.assertEqual(revalidation.headers.get("ETag"), etag)

    def test_a_weak_copy_of_the_tag_still_revalidates_to_304(self):
        """nginx weakens the tag of every response it gzips; the browser
        revalidates with that W/ copy and must still get a 304."""
        response = self.client.get(SCHEMA_URL)
        etag = response.headers.get("ETag")
        caches["local-memory"].clear()
        revalidation = self.client.get(
            SCHEMA_URL, HTTP_IF_NONE_MATCH="W/" + etag)
        self.assertEqual(revalidation.status_code, 304)

    def test_a_cookieless_response_does_not_vary_on_the_session(self):
        """Without a session cookie the schema response sets no cookie, so
        SessionMiddleware's conservative Vary: Cookie marking is measurably
        false and the SchemaVaryMiddleware drops it - the cache key of
        anonymous and logged-out boots stays stable."""
        response = self.client.get(SCHEMA_URL)
        self.assertNotIn("set-cookie",
                         [k.lower() for k in response.headers])
        self.assertNotIn("cookie", self._vary(response))

    def test_a_session_user_keeps_the_cookie_refresh_policy_and_the_answer(
            self):
        """A request that carries a session cookie gets its rolling refresh
        back (SESSION_SAVE_EVERY_REQUEST stays untouched), so its response
        really does set a cookie and keeps Vary: Cookie - what must not
        change is the document itself."""
        self.client.login(username="schema-cache-probe",
                          password="not-a-secret-pw1")
        response = self.client.get(SCHEMA_URL)
        self.assertIn("sessionid", response.cookies)
        self.assertIn("cookie", self._vary(response))
        anonymous = Client().get(SCHEMA_URL)
        self.assertEqual(response.content, anonymous.content)

    def test_the_scoping_of_the_vary_middleware_leaves_the_rest_alone(self):
        """An endpoint that may depend on the session keeps its marking."""
        self.client.login(username="schema-cache-probe",
                          password="not-a-secret-pw1")
        response = self.client.get(
            "/api/registry/wms",
            HTTP_ACCEPT="application/vnd.api+json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("cookie", self._vary(response))

    def test_a_stale_tag_is_answered_with_the_full_document(self):
        response = self.client.get(SCHEMA_URL, HTTP_IF_NONE_MATCH='"stale"')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"openapi", response.content)

    def test_a_repeated_request_is_served_from_the_page_cache(self):
        """The generation cache keeps working for the new view."""
        first = self.client.get(SCHEMA_URL)
        self.assertEqual(first.status_code, 200)
        self.assertNotIn("Age", first)
        second = self.client.get(SCHEMA_URL)
        self.assertEqual(second.status_code, 200)
        # cache_page stamps Age from the stored expiry onto cache hits.
        self.assertIn("Age", second)
        self.assertEqual(first.content, second.content)
