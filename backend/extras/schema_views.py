"""View for serving the OpenAPI schema document to the frontend.

The SPA builds its data provider, resources, forms and filters from the
OpenAPI document at start-up, so ``/api/schema`` is the most loaded resource
in the system and the largest: megabytes of JSON on every boot (#946).
The document itself changes only with the deployed code - not with the
requesting user - which is what this view exploits:

* A strong ``ETag`` over the rendered document lets the browser revalidate
  with ``If-None-Match`` and receive a bodyless 304 instead of the whole
  document again. The hash is taken over the JSON rendering of the delivered
  document; the two media types this view serves render byte-identically, so
  one tag covers whichever content negotiation picks. Both paths that can
  answer the document revalidate: the view on a cache miss, where the check
  also skips the rendering, and ``SchemaConditionalGetMiddleware`` on a
  ``cache_page`` hit, where no view code runs at all.
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
* What is delivered here is the deduplicated rendering: the repeated
  parameter objects and pagination fragments are lifted into ``components``
  as references (``extras.schema.lift_duplicated_components``), which the
  SPA's client dereferences transparently. The generator keeps the inlined
  shape - and with it ``manage.py spectacular`` and the contract tests that
  read the raw document.

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
import json
import threading

from django.core.cache import caches
from django.http import HttpResponse
from django.utils import translation
from drf_spectacular.renderers import (OpenApiJsonRenderer,
                                       OpenApiJsonRenderer2)
from drf_spectacular.views import SpectacularJSONAPIView
from rest_framework.response import Response

from MrMap import VERSION as MRMAP_VERSION
from extras.schema import lift_duplicated_components


def if_none_match_matches(request, etag):
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


class CompactOpenApiJsonRenderer(OpenApiJsonRenderer):
    """Serve the document without the pretty-print indent.

    ``OpenApiJsonRenderer`` forces ``indent=4`` (it inherits that from
    DRF's JSONRenderer contract of serving humans reading a browser). The
    consumer of ``/api/schema`` is the SPA's schema parser, not a reader;
    the indent alone measured 6.2 MB of wire bytes for a 2.1 MB document,
    which every boot downloads.

    An explicit ``Accept: ...; indent=4`` is deliberately not honoured on
    top of that: the ``ETag`` is taken over exactly these bytes, so the
    rendering must not depend on what a client asked for.
    """

    def get_indent(self, accepted_media_type, renderer_context):
        return None


class CompactOpenApiJsonRenderer2(CompactOpenApiJsonRenderer,
                                  OpenApiJsonRenderer2):
    """The same compact bytes under the plain ``application/json`` type.

    ``SpectacularJSONAPIView`` serves two media types, and both the SPA's
    axios default (``application/json, text/plain, */*``) and the API's own
    clients (``application/json``) name the second one, so it is the one
    content negotiation actually picks for them. Dropping this renderer
    instead of compacting it answers those clients ``406`` - the acceptance
    feature ``json:api/schema/retreive_schema.feature`` sends exactly that
    header and failed on the first version of this change.
    """

    media_type = "application/json"


class RevalidatableOpenApiSchemaView(SpectacularJSONAPIView):
    # The view answers the same document to every client (see the module
    # docstring), so it authenticates nobody: leaving the default classes
    # in place would have SessionAuthentication read the session, and
    # SessionMiddleware then marks the response ``Vary: Cookie`` although
    # no cookie is ever set here. The API's own endpoints keep their full
    # authentication stack; this document has never required credentials
    # (spectacular's serve permissions default to none).
    authentication_classes = []
    renderer_classes = [CompactOpenApiJsonRenderer,
                        CompactOpenApiJsonRenderer2]

    # The document changes only with the deployed code, so within one
    # worker process it is generated exactly once and kept in the same
    # ``local-memory`` cache the ``cache_page`` wrap already uses (whose
    # key the tests clear between generations — this entry is cleared with
    # it). The lock makes concurrent cold requests a single flight: the
    # measured stampede of 8 clients triggered 8 full generations of the
    # same document, seconds each.
    _generation_lock = threading.Lock()

    def _document_cache_key(self, request):
        lang = request.GET.get("lang") or translation.get_language()
        return f"openapi-document:{MRMAP_VERSION}:{lang}"

    def _get_schema_response(self, request):
        cache = caches["local-memory"]
        key = self._document_cache_key(request)
        document = cache.get(key)
        if document is None:
            with self._generation_lock:
                # double-checked: a waiting thread must not regenerate
                # what the first thread just produced.
                document = cache.get(key)
                if document is None:
                    response = super()._get_schema_response(request)
                    if response.status_code != 200:
                        return response
                    # The delivered document is the deduplicated rendering;
                    # the round trip through the compact bytes also settles
                    # the lazy translation proxies into plain data, which is
                    # what the cache and the renderer below then work with.
                    compact = CompactOpenApiJsonRenderer()
                    data = lift_duplicated_components(json.loads(
                        compact.render(response.data)))
                    # The tag is quoted per RFC 9110 and taken over the very
                    # bytes this view serves; hashing the rendered JSON costs
                    # tens of milliseconds next to the seconds the generation
                    # of this very response took.
                    wire = compact.render(data)
                    document = {
                        "data": data,
                        "etag": f'"sha256-'
                                f'{hashlib.sha256(wire).hexdigest()}"',
                        "disposition":
                            response.headers.get("Content-Disposition"),
                    }
                    cache.set(key, document, timeout=None)

        etag = document["etag"]
        if if_none_match_matches(request, etag):
            # The 304 repeats the two headers the 200 carries: the browser
            # refreshes them on its stored copy, and the cache_page wrap
            # around this view only skips its "Vary: Authorization" addition
            # when the response it sees already says public. With the tag
            # taken from the cached document, the revalidation no longer
            # regenerates the document it is about to refuse to send.
            return Response(status=304, headers={
                "ETag": etag, "Cache-Control": "public"})

        headers = {"ETag": etag, "Cache-Control": "public"}
        if document.get("disposition"):
            headers["Content-Disposition"] = document["disposition"]
        return Response(document["data"], headers=headers)


class SchemaConditionalGetMiddleware:
    """Answer a matching ``If-None-Match`` with 304 for a page-cache hit.

    ``cache_page`` (the URLconf wrap) serves a stored response without
    consulting the view, and Django's page cache has no conditional-GET
    handling: a browser whose 15 minutes of freshness have expired
    revalidates with the tag it was given and was answered the whole
    document again - measured 1.47 MB for a request whose tag matched,
    which is the cost the ETag exists to prevent. The view short-circuits
    the same comparison for a *miss* (and thereby skips the rendering);
    this middleware covers the hit, where no view code runs.

    Runs below ``SchemaVaryMiddleware`` in the response phase (listed
    before it), so the ``Vary`` it repeats on the 304 is the cleaned one:
    a 304 refreshes the stored headers of the client's copy, so a stale
    ``Vary: Cookie`` handed out here would re-enter the cache key.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (request.path != "/api/schema"
                or request.method not in ("GET", "HEAD")
                or response.status_code != 200):
            return response
        etag = response.headers.get("ETag")
        if not etag or not if_none_match_matches(request, etag):
            return response
        conditional = HttpResponse(status=304)
        # RFC 9110 Section 15.4.5: a 304 carries the stored validators and
        # cache directives of the selected representation, and no body.
        for header in ("ETag", "Cache-Control", "Vary", "Content-Location"):
            value = response.headers.get(header)
            if value:
                conditional.headers[header] = value
        return conditional


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
