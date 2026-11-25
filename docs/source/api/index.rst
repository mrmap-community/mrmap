.. _api-reference:

=============
API reference
=============

The interface an integrator codes against. Two kinds of page live under this
heading and they differ in how they come to exist, which is worth knowing before
trusting one:

- The REST and OGC description on this page and the pages it links is **derived
  from the source** of the release this portal documents - the routers, viewsets
  and settings that ship in it. It is complete in every build.
- The Python reference on :ref:`models`, :ref:`managers` and :ref:`modules` is
  **extracted from the application** by autodoc. A portal build runs without the
  backend environment - no database, no GDAL, no application imports - so those
  sections name the module and state that its reference was not generated,
  instead of leaving an empty space where one should be. Setting
  ``MRMAP_DOCS_AUTODOC=on`` turns a module that cannot be imported into a build
  error instead, which is how the docs image keeps the extraction honest. See
  :ref:`api-generated-vs-authored`.

.. _api-generated-vs-authored:

What is derived, what is extracted
==================================

.. list-table::
   :header-rows: 1
   :widths: 30 30 40

   * - Surface
     - Produced by
     - Behaviour without the backend environment
   * - REST resources, their verbs and their permission classes
     - source of the release
     - complete
   * - The JSON:API envelope, paging and error shape
     - ``backend/MrMap/settings.py``
     - complete
   * - OGC interfaces and the security proxy in front of them
     - source of the release
     - complete
   * - Python reference of ``registry``, ``system``, ``notify``, ``accounts``
     - autodoc over the importable application
     - explicit placeholder naming the module (#1597)
   * - Screenshots and behavioural claims about a running instance
     - the demo stack and its browser evidence (#1601, #1602)
     - not built here; the epic publishes those as declared stubs

Where to look for an interface
==============================

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - To understand
     - Read
   * - How a client authenticates
     - :ref:`api-authentication`
   * - The envelope, paging and errors a client parses
     - :ref:`api-jsonapi-envelope`
   * - The OGC endpoints and the proxy
     - :ref:`api-ogc-interfaces`
   * - Working request examples to run against a development instance
     - ``docs/source/api/examples.http`` in the repository, openable with the
       VS Code REST Client
   * - The exact field names and enum values of a resource
     - the OpenAPI document of your instance, :ref:`api-openapi`
   * - The Python objects behind a resource
     - :ref:`models`, :ref:`managers`, :ref:`modules`
   * - Which caller may do what
     - :doc:`../administration/permissions`

The mount points are the ones in ``backend/MrMap/urls.py``: ``/api/registry/``,
``/api/accounts/``, ``/api/system/``, ``/api/notify/`` and ``/api/auth/`` for
REST, ``/csw`` for the catalogue, ``/mrmap-proxy/`` for the secured OGC
operations and ``/mapbender/search`` for the compatibility endpoint. Which of
those the edge proxies to the application and which it answers with the single
page application is itself a tested contract -
``scripts/nginx_routing_smoke.py`` (#1036).

.. _api-openapi:

The OpenAPI document
====================

``drf_spectacular`` is configured and the running instance publishes its own
description, cached for a quarter of an hour:

.. code-block:: http

    GET /api/schema HTTP/1.1
    Host: mrmap.example.com
    Accept: application/yaml

``/api/schema/swagger-ui`` renders the same document interactively. That document
is produced by the code that answers the request, which makes it the authority
for field names; this page documents the *shape* of the exchange, so that it
stays readable when no instance is at hand. Its hooks - including the JSON:API
ones and the operation-id class - are configured under ``SPECTACULAR_SETTINGS``
and ``REST_FRAMEWORK["DEFAULT_SCHEMA_CLASS"]`` in ``backend/MrMap/settings.py``.

.. _api-authentication:

Authentication
==============

The REST interface is Django REST framework behind Mr.Map's own permission
classes. Two mechanisms reach it and they are not interchangeable (#835, accepted
decision Q8=B):

.. code-block:: http

    GET /api/registry/wms HTTP/1.1
    Host: mrmap.example.com
    Authorization: Basic <username and password of a user>

    -> 200, and the body carries a token the caller keeps itself

.. code-block:: http

    GET /api/registry/wms HTTP/1.1
    Host: mrmap.example.com
    Authorization: Bearer <that token>
    Accept: application/vnd.api+json

.. code-block:: http

    POST /api/auth/session HTTP/1.1
    Host: mrmap.example.com
    Content-Type: application/vnd.api+json
    X-CSRFToken: <csrf cookie of this browser>
    Referer: https://mrmap.example.com/api/auth/session

    {"data": {"type": "Login", "attributes": {"username": "...", "password": "..."}}}

``/api/auth/login`` is the machine path: HTTP Basic in, a knox token out, valid
for ten hours and capped at five live tokens per user, enforced server side
against the token's own row, with no automatic refresh and revocation per token.
``/api/auth/session`` is the browser path the single page application uses; it
opens a Django session, and a session carries a CSRF requirement on unsafe
methods - which is why the examples above send ``X-CSRFToken`` and a matching
``Referer`` on the state-changing calls and neither on the reads. The credential
types, their lifetimes, and how an expired credential is told apart from a
refused action are in :doc:`../administration/authentication`.

Only those two endpoints accept the password, and each names Basic authentication
on the view itself; the global authentication stack is session plus knox token
(#1450). Who the caller is changes the answer and not only whether it is allowed:
the same endpoint returns a different result set - and on some resources a
different field set - for a cataloguer, a member of the owning organization and a
superuser, because the permission filtering happens in the query rather than after
it. :doc:`../administration/permissions` describes that model; this page describes
only the shape of the exchange.

One floor is worth stating because it is the deployment's default and not a
per-view choice: ``REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"]`` is
``IsAuthenticatedOrReadOnly`` (#1444), so a view that forgets to name its own
permission class still refuses a write to an anonymous caller.

.. _api-jsonapi-envelope:

The JSON:API envelope
=====================

Collections and single resources are wrapped, and the wrapper is the contract a
client parses:

.. code-block:: json

    {
      "data": [
        {
          "type": "WebMapService",
          "id": "12",
          "attributes": {"title": "Demographie", "service_type": "wms"},
          "relationships": {}
        }
      ],
      "meta": {"pagination": {"count": 1, "page": 1, "pages": 1}},
      "links": {"self": "https://mrmap.example.com/api/registry/wms?page=1"}
    }

Four properties a client can rely on come from ``backend/MrMap/settings.py``
rather than from any single endpoint, which is what makes them uniform:

- The renderers are ``extras.renderers.JSONRenderer`` and, outside a production
  deployment, the browsable API. A request with no ``Accept`` header or with
  ``Accept: */*`` receives the JSON:API representation; an explicitly HTML-only
  request against a production instance is answered ``406`` rather than with an
  API browser page.
- The parsers and the metadata class are ``rest_framework_json_api``'s, so the
  envelope above is what a ``POST`` body has to look like too, not only what a
  ``GET`` returns.
- ``REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"]`` is
  ``drf_spectacular_jsonapi.schemas.pagination.JsonApiPageNumberPagination``,
  which is where ``meta.pagination`` comes from. The page size and its ceiling
  are the two settings ``PAGE_SIZE`` and ``MAX_PAGE_SIZE`` and not a per-view
  decision, so one client implementation pages every resource the same way.
- ``REST_FRAMEWORK["EXCEPTION_HANDLER"]`` is
  ``rest_framework_json_api.exceptions.exception_handler``, so an error carries
  the JSON:API error object beside the HTTP status and a validation failure names
  the attribute that failed. That is the difference between "the server refused"
  and "rename this field", and integrations depend on it.

Filtering is uniform as well: the backends are ``rest_framework_json_api``'s
beside the project's own search-vector filter, which is why search and ordering
are asked with ``filter[search]`` and ``sort`` rather than with per-endpoint query
parameters.

A long-running registration answers ``202`` and names its own polling resource:
the ``Content-Location`` header points at the background process whose record
carries the queued, running and terminal states and, once it exists, the service
it built in ``relatedResource``. An integration therefore never has to guess
whether a ``202`` eventually succeeded - see the ``@name getProcess`` request in
``docs/source/api/examples.http`` and
:doc:`../development/background-operations`.

.. _api-ogc-interfaces:

OGC interfaces
==============

Beyond REST the instance speaks OGC protocols directly, and this is where most
integrations land:

.. list-table::
   :header-rows: 1
   :widths: 26 28 46

   * - Interface
     - Reached at
     - Documented in
   * - CSW 2.0.2 catalogue
     - ``/csw``
     - *Metadata Catalouge* in :doc:`../usage/index`
   * - WMS of a registered service
     - ``/mrmap-proxy/wms/<service uuid>``
     - :doc:`../design/ows-context`,
       :doc:`../design/ows-context-interoperability`
   * - WFS of a registered service
     - ``/mrmap-proxy/wfs/<service uuid>``
     - as above
   * - Capabilities of one layer or feature type
     - ``/mrmap-proxy/wms/layer/<uuid>``,
       ``/mrmap-proxy/wfs/featuretype/<uuid>``
     - ``backend/registry/proxy/resource_capabilities.py``
   * - OWS context of a service
     - ``/mrmap-proxy/ows/<pk>``
     - :doc:`../design/ows-context`
   * - MapBender compatibility search
     - ``/mapbender/search``
     - :ref:`modules`

The proxy in front of the OGC interfaces is the access control that decides
whether a request - including an anonymous one - reaches a service at all, and it
decides on the operation and layer level rather than the resource level. It is
configured in the administration section, implemented under
``backend/registry/proxy/`` and reference-documented in :ref:`modules`. Note the
verb caveat the routes above explain: the OGC XML POST binding carries a
``GetFeature``, which is a read, over HTTP ``POST``, which is why the proxy names
no permission class of its own and enforces its own rules instead.

.. _api-python-reference:

Python reference
================

The three indexes below are the autodoc surfaces. Their headings are always
present; their content depends on whether the application could be imported
during the build, and each page states which of the two it is rather than leaving
the reader to guess.

.. toctree::
   :maxdepth: 3

   ../models/index
   ../managers/index
   ../modules/index
