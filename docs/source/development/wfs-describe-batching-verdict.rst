.. _wfs-describe-batching-verdict:

==============================================
Why WFS DescribeFeatureType is not batched
==============================================

Epic `#1408 <https://github.com/mrmap-community/mrmap/issues/1408>`_ phase C
(`#1414 <https://github.com/mrmap-community/mrmap/issues/1414>`_) asks whether
the per-feature-type ``DescribeFeatureType`` requests of the backend should be
batched into multi-``typeNames`` requests, and - per its own first work item -
whether repeated single-type requests occur in one workflow at all. **The
verdict is: they do not. Batching is not implemented and would save zero
requests on today's code.** This page is the evidence the issue's last
acceptance item asks for, plus the guard that keeps the premise from rotting
silently.

The call path, traced
=====================

The candidate named in the issue is
:meth:`registry.models.service.FeatureType.fetch_describe_feature_type_document`
(one request with ``type_names=[self.identifier]``). Tracing every reference of
that method, of its downstream chain (:meth:`~registry.models.service.FeatureType.parse`
and :meth:`~registry.models.service.FeatureType.create_element_instances`) and of
the KVP builder behind it
(:meth:`registry.ows_lib.wfs.wfs.WebFeatureServiceClient.describe_feature_type_request`):

- **No production module calls any of them.** The only references in the whole
  repository are the definitions in ``registry/models/service.py`` and the unit
  tests ``tests/django/registry/models/tests_document.py``. Registration,
  update, monitoring, harvest, preview, the security proxy, the API views, the
  management commands and ``scripts/`` never build a ``DescribeFeatureType``
  request; the proxy only *forwards* such operations when a browser client
  sends one, which is the client's traffic, not a registry download, and never
  an mrmap-issued series.
- **The repeated consumer existed and was removed.** The Celery task
  ``create_feature_type_elements`` - a chord header of one task per feature
  type, each paying one describe request - was deleted in commit
  ``6b3110891`` ("implement recommended async post for ogcservice",
  2021-11-22). Nothing replaced it. The methods survived as a tested but
  unconnected capability; audit finding R6 of :ref:`outbound-ogc-request-audit`
  counted the traffic at "0 requests in registration, update, monitoring,
  harvest and preview today" and told #1414 to start from exactly that fact.
- **The reader of the chain's output tolerates its emptiness.** The chain is
  the only writer of ``FeatureTypeProperty``: the mapping
  ``("DescribeFeatureType", "2.0.0")`` in ``mappers/configs/wfs200.py`` is
  reached only through :meth:`~registry.models.service.FeatureType.parse`.
  (This corrects the R6 parenthetical, which attributed those rows to the
  capabilities config: the capabilities config never mapped
  ``FeatureTypeProperty`` - the one ``_model`` reference to it is inside the
  describe mapping.) Production therefore stores no properties at all, and both
  readers degrade by design: the WFS security annotation falls back through
  ``Coalesce(F("geometry_property_name"), V("THE_GEOM"))``
  (``registry/managers/security.py``) with the same default in
  ``ows_lib/request/ogc_request.py``, and the GML preview passes ``None`` as
  the tie-breaker name (``registry/helper/preview.py``). Wiring a describe
  fetch back in would *change* secured and previewed behaviour; that is a
  product decision, not an optimization.

The guard
=========

``backend/tests/django/registry/models/tests_describe_call_path.py`` is the
call-path fixture R6 named as missing. It scans the production sources and
asserts that no module outside the defining ones references the fetch chain or
the request builder, and it fails with this page's address if one does. It
forbids nothing forever: a deliberate consumer updates the guard with itself
named - but only after facing the requirements below.

What would re-open batching
===========================

The issue stays reusable as the specification for whoever wires a consumer:

- A consumer that describes **several feature types of one service in one
  workflow** (an operator command, an import, a restored properties-refresh
  flow) is the repetition batching needs. Until it exists, batching answers a
  request nobody sends.
- When one exists, the acceptance list of #1414 applies unchanged: WFS
  1.x/2.0 ``typeNames``/``typeName`` compatibility with an optional,
  fallback-capable path and a bound on request length and type count; XML
  Schema elements, types, imports and namespaces mapped back per feature type;
  partial or invalid responses decided per type without losing individual
  failures; results never shared across distinct service auth, version or
  permission scope, and never served stale.
