"""View for serving the OpenAPI schema document to the frontend.

The SPA builds its data provider, resources, forms and filters from the
OpenAPI document at start-up, so ``/api/schema`` is the most loaded resource
in the system and the largest: megabytes of JSON on every boot (#946).
The document itself changes only with the deployed code - not with the
requesting user - which is what this view exploits:

* A strong ``ETag`` over the rendered document lets the browser revalidate
  with ``If-None-Match`` and receive a bodyless 304 instead of the whole
  document again. The hash is taken over the JSON rendering of the schema
  dict; since the rendering is a deterministic function of the document,
  the tag is also correct for the YAML representations, which content
  negotiation can select for the same URL (those vary together with it).
* ``Cache-Control: public`` marks the response as shareable. That matters
  beyond nginx, which does not cache here: ``cache_page`` (``django.views.
  decorators.cache``, applied in the URLconf around this view) adds
  ``Vary: Authorization`` to any cached response whenever the *request*
  carried an authorization header, unless the response declares itself
  public (``django.middleware.cache``). With that Vary, the page cache key
  includes the token, so every user regenerates the multi-megabyte document
  on their own and anonymous clients cannot reuse an authenticated entry.
  Dropping the Vary is honest precisely because the document is not
  per-user; ``tests/django/test_schema_views.py`` pins that the anonymous
  and the authenticated document are byte-identical.

Authentication behaviour: the document answers with spectacular's serve
permissions (public by default) for every client today; the view declares
``authentication_classes = []`` so no authenticator reads the session as a
side effect - the default SessionAuthentication did exactly that on every
request, and SessionMiddleware's response marking made the document carry
``Vary: Cookie`` although no cookie is ever set here. Credentials in the
request are therefore simply not looked at for this one public document;
the rest of the API keeps its full authentication stack. The 15-minute
``cache_page`` wrap in the URLconf stays as the generation cache; this view
only adds the response headers and the 304 short-circuit.
"""

import hashlib

from drf_spectacular.renderers import OpenApiJsonRenderer
from drf_spectacular.views import SpectacularJSONAPIView
from rest_framework.response import Response


class RevalidatableOpenApiSchemaView(SpectacularJSONAPIView):
    # The view answers the same document to every client (see the module
    # docstring), so it authenticates nobody: leaving the default classes
    # in place would have SessionAuthentication read the session, and
    # SessionMiddleware then marks the response ``Vary: Cookie`` although
    # no cookie is ever set here. The API's own endpoints keep their full
    # authentication stack; this document has never required credentials
    # (spectacular's serve permissions default to none).
    authentication_classes = []

    def _get_schema_response(self, request):
        response = super()._get_schema_response(request)
        if response.status_code != 200:
            return response

        # The tag is quoted per RFC 9110; hashing the rendered JSON bytes
        # costs tens of milliseconds next to the seconds the generation of
        # this very response took.
        digest = hashlib.sha256(
            OpenApiJsonRenderer().render(response.data)).hexdigest()
        etag = f'"sha256-{digest}"'

        if self._if_none_match_matches(request, etag):
            # The 304 repeats the two headers the 200 carries: the browser
            # refreshes them on its stored copy, and the cache_page wrap
            # around this view only skips its "Vary: Authorization" addition
            # when the response it sees already says public.
            return Response(status=304, headers={
                "ETag": etag, "Cache-Control": "public"})

        response["ETag"] = etag
        response["Cache-Control"] = "public"
        return response

    @staticmethod
    def _if_none_match_matches(request, etag):
        """Whether an If-None-Match header selects this document version.

        Compared weakly per RFC 9110 Section 13.1.3: a revalidating client
        often echoes a ``W/``-prefixed copy of the tag it was given - nginx
        weakens the tag of every response it gzips, which is honest for the
        transformed bytes and must still revalidate to 304. "*" matches
        every version.
        """
        header = request.META.get("HTTP_IF_NONE_MATCH")
        if not header:
            return False
        candidates = [
            candidate.strip().removeprefix("W/") for candidate in
            header.split(",")]
        return etag in candidates or "W/*" in candidates or "*" in candidates


class SchemaVaryMiddleware:
    """Drop the ``Vary: Cookie`` marking from the schema response.

    ``SessionMiddleware`` adds it to every response for which the request
    carried a session cookie - it opens that cookie, that read alone counts
    as an access, and the marking is a conservative claim that *this*
    response might have read the session. For ``/api/schema`` the claim is
    measurably false: the answering view has no authentication classes and
    no session code on its path, the document is byte-identical with and
    without credentials (pinned by the tests), and the response sets no
    cookie of its own. As long as no cookie is set, leaving ``Cookie`` in
    the Vary would only make every cache key depend on a header that
    cannot change the answer - which is exactly the reload cost #946 is
    about: a login (or any cookie churn) invalidating a multi-megabyte
    entry the session has never influenced.

    The middleware runs above ``SessionMiddleware`` (first in MIDDLEWARE
    means seeing the response late) and touches this one path only.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path != "/api/schema":
            return response
        # Only responses that carry no cookie of their own may drop the
        # marking; if anything did set a cookie, varying on Cookie is the
        # truth again and stays.
        if response.cookies or response.status_code not in (200, 304):
            return response
        kept = [
            entry for entry in
            (value.strip() for value in
             response.headers.get("Vary", "").split(","))
            if entry and entry.lower() != "cookie"]
        del response.headers["Vary"]
        if kept:
            response.headers["Vary"] = ", ".join(kept)
        return response
