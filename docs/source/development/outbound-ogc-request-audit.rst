.. _outbound-ogc-request-audit:

====================================
Outbound OGC request and parse audit
====================================

This page is the static audit of #1409: the inventory of every first-party
outbound HTTP/OGC call and of every repeated document parse or serialization in
the backend, the reachable call path of each (including the Celery retries, the
recoveries and the operations the frontend triggers), the actual number of
requests and parser invocations a flow pays for, and the owner of each confirmed
redundancy. It is the evidence base the later children of epic #1408 must work
from: #1410 (shared acquisition of advertised ISO references), #1411 (CSW page
coalescing), #1412 (single-pass ``GetRecords`` parsing), #1413 (avoiding
downstream work for an unchanged service), #1414 (``DescribeFeatureType``
batching) and #1415 (duplicate mapping/transform work).

SQL-only findings are **not** re-solved here. Where a flow's cost is database
work rather than a request or a parse, the row names the owner in epic #1387
(the task ORM/SQL audit of #1388 is
:ref:`celery-task-orm-audit`, its guards are
:ref:`celery-task-sql-regression`) and stops there.

Scope rules honored here (from #1408 and #1409)
################################################

- The audit is **static**: source inspection and call-path tracing only. No
  production telemetry, no runtime sampling, no dashboards and no new
  instrumentation were added; nothing in ``backend/`` changed to produce it.
- **No behavioral change** is proposed by this page. Rows are marked
  ``confirmed`` (the code demonstrably does this), ``hypothesis`` (plausible,
  needs a measurement or a standards reading before it is trusted) or
  ``no change`` (deliberate, already fixed elsewhere, or out of the epic's
  boundaries). Each row names an implementation owner.
- Reusing one response for several logical consumers is **only** recorded as a
  candidate where the reuse is correct for that flow. The correctness question
  is answered per flow under `Reuse correctness per flow`_ — independent
  monitoring probes are never a coalescing candidate, and a protected proxy
  response never crosses an authentication or authorization context.
- Behaviors already fixed by #1044, #688, #690, #694, #1100, #1257, #1259,
  #1261, #1263, #1274, #958 and #1153 are recorded as *existing protection*
  under `Already answered — do not recreate it`_, not as work to redo.

How to re-derive the inventory
##############################

Four searches answer the whole inventory; they are exhaustive because every
byte Mr. Map asks from another host travels through one of two transports.

- every call through the OGC client: ``grep -rn "send_request(" backend --include=*.py``
  (``registry/ows_lib/client/core.py:229`` is ``OgcClient.send_request``,
  overridden once by ``CatalogueServiceClient.send_request``,
  ``registry/ows_lib/csw/csw.py:16``);
- every call beside the OGC client: ``grep -rn "session.send(\|requests\.\(get\|post\|delete\)(" backend --include=*.py``;
- every construction of a client or session: ``grep -rn "Client(\|Session()" backend --include=*.py``;
- every document parse: ``grep -rn "etree.fromstring\|etree.parse\|etree.tostring" backend --include=*.py``.

The transports, and what each one guarantees:

``OgcClient.send_request`` (``registry/ows_lib/client/core.py:229-279``)
  The project's OGC transport. Explicit ``timeout`` argument (default 10 s),
  redirects asked hop by hop with a budget of ``MAX_REDIRECTS = 5``
  (``core.py:18``) and refused as ``RedirectChainError`` when a hop leaves the
  host of the endpoint (``core.py:272-276``, #1100). Requests come from
  ``service.operation_urls`` / the parsed capabilities document, never from a
  caller.
``requests.Session`` built at the call site
  Three places: the registration of a service
  (``registry/tasks/service.py:96-103``, proxy settings applied, timeout
  ``REGISTRATION_REQUEST_TIMEOUT_SECONDS = 15`` from ``registry/settings.py:42``),
  the download seam of an advertised reference
  (``registry/models/metadata.py:530-543``, connection-only retries, the same
  15 s timeout) and ``OgcService.remote_capabilities``
  (``registry/models/service.py:293-306``). None of the three goes through the
  client, so #1100's bounded, same-host walk and its ``RedirectChainError`` do
  not apply to any of them; of the three, ``remote_capabilities`` is the only
  one which also passes **no timeout at all** — see row R11.
A live preview request
  ``registry/helper/preview.py:60-95`` — a ``Session`` subclass which forces
  ``timeout=(3, 3)``, ``stream=True``, ``allow_redirects=False`` and refuses
  any redirect or 4xx/5xx answer, bounding the body it buffers. This is the
  pattern an intentional outbound read should look like; it is reached only
  from the preview endpoints.

Outbound request entrypoints
############################

Every site which asks another host, with the identity of the request it sends.
``Reached by`` names the first-party path; the fan-out multiplicities are in
the matrix below.

Through ``OgcClient`` (client = ``service.client``, built from the **stored**
document, ``registry/models/service.py:415-427`` — no remote request is needed
to build it, #1044):

.. list-table::
   :header-rows: 1
   :widths: 26 30 22 22

   * - Site
     - Request identity (method / operation / params)
     - Auth scope
     - Reached by
   * - ``registry/models/monitoring.py:765``
     - one request per probe: ``GetCapabilities`` (``:812``), WMS ``GetMap``
       (``:890``), WMS/WFS ``GetFeature`` / CSW ``GetRecords`` (``:972``,
       ``:1053``); URL from the stored document, params from the probe row
     - the service's own stored credentials
       (``get_session_for_request``, ``service.py:237``)
     - ``run_probe_check`` (``tasks/monitoring.py:16``), one
       message per probe of the run's setting; the settings' beat rows and the
       review flow which starts a run
   * - ``registry/models/harvest.py:795`` and ``:809``
     - CSW ``GetRecords`` KVP, ``resultType=hits``, constraint from
       ``get_record_types()``; ``:809`` repeats it with
       ``typeNames=csw:Record`` when the first answered 0 records (#689)
     - catalogue's stored credentials
     - ``call_fetch_total_records``
       (``tasks/harvest.py:1621``), the harvest root and its recovery
   * - ``registry/models/harvest.py:879``
     - CSW ``GetRecords`` ``resultType=hits`` with ``maxRecords=size``, one per
       halved size of the probe of #694
     - catalogue's stored credentials
     - same task, ``probe_max_step_size``
   * - ``registry/models/harvest.py:1086``
     - CSW ``GetRecords`` ``resultType=results`` with
       ``maxRecords``/``startPosition`` of one step; timeout scales with the
       size (``:850-860``)
     - catalogue's stored credentials
     - ``call_fetch_records`` chord member
       (``tasks/harvest.py:1660``), one message per page
   * - ``registry/models/service.py:1133``
     - WFS ``DescribeFeatureType`` for **one** ``typeNames``, output format
       picked from the advertised ``MimeType`` rows
     - service's stored credentials
     - **no first-party caller** (only
       ``tests/django/registry/models/tests_document.py``) — see row R6
   * - ``registry/proxy/mixins.py:320``
     - the caller's OGC request re-pointed at the registered operation URL,
       method/data/params kept; ``Authorization``, ``Cookie`` and ``Host`` of
       the caller are stripped (``:314-315``) and the service's own credentials
       are used
     - service credentials, caller's permissions applied **before** the send
     - every proxied operation of a
       secured-or-not service which is not answered from storage
       (``get_and_post``, ``:245-264``)
   * - ``registry/proxy/wfs_proxy.py:188``
     - WFS ``GetFeature`` rebuilt with the caller's filter plus the allowed-area
       filter
     - service credentials, one caller's areas
     - spatially secured WFS ``GetFeature``
   * - ``registry/proxy/wms_proxy.py:399`` and ``:460``
     - WMS ``GetFeatureInfo`` (``:460``), then again at ``:399`` plus a second
       variant with ``INFO_FORMAT=text/xml`` (``:402-403``)
     - service credentials, one caller's areas
     - spatially secured WMS ``GetFeatureInfo`` whose
       allowed areas do not cover the requested bbox — row R7
   * - ``registry/helper/preview.py:270`` and ``:329``
     - WMS ``GetMap`` / WFS ``GetFeature`` of the preview, through the same
       proxy decision the browser would take
     - the **caller's** permission decision, service credentials upstream
     - ``GET .../preview`` and ``.../preview-image``
       (``views/service.py:205``, ``:617``)
   * - ``registry/helper/preview.py:562``
     - CSW ``GetRecords`` ``resultType=results`` of one preview page, URL
       rewritten to the registry's own operation URL (``:565-567``)
     - caller's decision, service credentials
     - ``GET .../preview`` of a catalogue
   * - ``mapbender_compatibility/views.py:93``
     - CSW ``GetRecords`` with a CQL ``BBOX`` filter, page from
       ``searchPages``/``maxResults``
     - catalogue's stored credentials
     - the legacy MapBender search endpoint (explicit compatibility exception
       in ``AGENTS.md``)

Beside ``OgcClient``:

.. list-table::
   :header-rows: 1
   :widths: 26 30 22 22

   * - Site
     - Request identity
     - Auth scope
     - Reached by
   * - ``registry/tasks/service.py:96-103``
     - ``GET`` of ``get_capabilities_url`` (``SERVICE``/``VERSION``/
       ``REQUEST`` set, ``settings.PROXIES`` applied), timeout 15 s
     - ``ServiceAuthentication`` of the registration
       (``_capabilities_auth``, ``:199``)
     - ``build_ogc_service`` — the service
       ``POST`` a client sends
   * - ``registry/models/metadata.py:530-543``
     - ``GET`` of one advertised ``RemoteMetadata.link``, timeout 15 s,
       ``Retry(total=3, read=False)`` — connection attempts only, never a
       re-read
     - **none** — ``:536`` says ``# FUTURE: Re add authentication``
     - ``collect_reference``
       (``tasks/service.py:508``) and ``RemoteMetadata.fetch_remote_content``;
       one message per planned reference
   * - ``registry/models/service.py:293-306``
     - ``GET`` of ``get_capabilities_url`` through
       ``get_session_for_request().send(request.prepare())`` — no timeout is
       passed and ``Session.send`` resolves redirects itself
       (``allow_redirects`` defaults to True, bounded by ``max_redirects`` = 30,
       any host)
     - service's stored credentials (dropped by
       requests when a hop leaves the host)
     - ``update()`` of each update job kind
       (``models/update.py:866``, ``:1075``, ``:1184``)
   * - ``registry/helper/plugins/etf.py:35``, ``:52``, ``:68``, ``:76``, ``:84``, ``:94``
     - ETF REST: ``POST v2/TestRuns``, ``GET <run>/progress`` once per polling
       interval, ``GET <run>``, ``GET <run>.html``, two ``DELETE``; module-level
       ``requests`` verbs, no timeout, no session
     - none (the ETF service is assumed open)
     - ``run_conformity_check_etf``
       (``tasks/conformity.py:49``), started from the conformity API
   * - ``system/status.py:57-70``
     - Docker Engine API of the deployment host, one session per snapshot,
       ``trust_env = False``, per-call deadline of 2 s
     - local docker socket
       URL only
     - the periodic capacity snapshot (``#1326``)

Not outbound, but the reason some flows above exist: ``registry/tasks/alerts.py``,
``registry/tasks/security.py``, ``registry/helper/plugins/internal.py``,
``registry/csw/`` (the local ``/csw`` endpoint), ``registry/views_ows/`` and
``registry/mappers/publish.py`` perform no remote request; the conformity
checker ``QualityInternal`` evaluates database rows only.

Repeated document parse and serialization sites
###############################################

A "transform" is one lxml parse or one serialization of a document Mr. Map
already holds or already parsed. The counts are per unit named in the row.

.. list-table::
   :header-rows: 1
   :widths: 30 16 12 42

   * - Site
     - Unit
     - Parses
     - What is parsed
   * - ``registry/ows_lib/client/core.py:81``
     - per client built
     - 1
     - the stored capabilities bytes. ``Service.client`` is a
       ``cached_property`` (``models/service.py:415``), so one per service
       instance per task/request — but the instance's lifetime is the message,
       not the deployment
   * - ``registry/models/monitoring.py:737``
     - per XML probe
     - 1
     - the probe's response body (``check_is_valid_xml``). The two
       ``check_does_*`` passes (``:713``, ``:724``) decode the same body to
       text again, once per configured needle list
   * - ``registry/models/harvest.py:779``
     - per ``fetch_total_records``
     - 1
     - the ``hits`` answer, for ``numberOfRecordsMatched`` — after
       ``_check_xml_response`` (``:946``) already parsed the same bytes
   * - ``registry/models/harvest.py:952``
     - per ``GetRecords`` answer
     - 1
     - the same answer, hardened parser, to look for an exception report (#815)
   * - ``registry/models/harvest.py:1121``
     - per answered page
     - 1
     - the page body a second time, to cut the ``MD_Metadata`` nodes out
   * - ``registry/models/harvest.py:1152``
     - per record of a page
     - 0 (+1 serialization)
     - ``etree.tostring(md_metadata, pretty_print=True)`` written to
       ``TemporaryMdMetadataFile.md_metadata_file``
   * - ``registry/models/harvest.py:1763``
     - per stored record file
     - 1 (+1, see next row)
     - the file is read back from storage and mapped by
       ``MDMetadataXmlMapper.from_xml``
   * - ``registry/mappers/factory.py:86-87``
     - per ``MD_Metadata`` node
     - 1
     - every node is serialized and parsed **again** to detach it into its own
       document. Runs on the harvest import, on
       ``couple_document`` (``models/metadata.py:614+``, registration and
       update) and on ``extract_mapped_values``
   * - ``registry/mappers/factory.py:17``
     - per capabilities document mapped
     - 1
     - ``OGCServiceXmlMapper.from_xml`` — registration, and every
       ``OGCServiceXmlMapper.to_xml`` render below
   * - ``registry/models/document.py:79-114``
     - per proxied ``GetCapabilities``
     - 1 (+1 serialization)
     - ``get_updated_capabilitites()`` reads the stored file, parses it, syncs
       every DB value into it and serializes; ``xml_secured``
       (``models/service.py:429-472``) does the same plus the URL camouflage
   * - ``csw/views.py:292``
     - per record served by ``/csw``
     - 1
     - ``record.xml_backup`` is read from storage and parsed for **every**
       request which matches that record
   * - ``registry/serializers/service.py:600-606``
     - per serialized WMS row asking ``preview_url``
     - 1
     - ``instance.xml_backup`` is read and a whole
       ``WebMapServiceClient`` is built to name one GetMap URL. The WMS and WFS
       **list** screens put ``preview_url`` in their fieldset
       (``frontend/src/components/Resource/WebMapService/List/ListWebMapService.tsx:42``,
       ``WebFeatureService/List/ListWebFeatureService.tsx:38``)
   * - ``registry/helper/preview.py:102-107``
     - per preview request
     - 2 (+1 serialization)
     - ``stored_client`` reads the stored document, parses it to check for an
       exception report, serializes it and hands the bytes to ``OgcClient``,
       which parses it a second time. The WFS ``preview-image`` and the CSW
       preview each build a **second** client from the same bytes
       (``:452``, ``:555``) → 3 parses
   * - ``mapbender_compatibility/views.py:113`` and ``:120``
     - per legacy search
     - 2 (+ node detaches)
     - the answer is parsed for the matched count and then parsed again by
       ``MDMetadataXmlMapper.from_xml``
   * - ``registry/models/security.py:609-640``
     - per logged proxied response
     - 0
     - not XML: the image the proxy already decoded for the mask is opened
       again from storage, decoded again and materialized as a pixel list
   * - ``registry/models/security.py:85-98``
     - per ``get_auth_for_request()`` — so per client build
     - 0
     - the Fernet key **file** is opened and read on every access of
       ``ServiceAuthentication.key``, then two values are decrypted
       (``:135-143``)
   * - ``registry/ows_lib/csw/csw.py:33`` and ``:55``
     - per ``get_constraint`` / ``advertised_max_records`` call — so per
       ``GetRecords`` request the harvester builds
     - 0
     - an xpath over the parsed capabilities tree plus a regex compiled per
       call; a run of 1000 pages evaluates both 1000+ times
   * - ``registry/mappers/publish.py:221-266``, ``:472-481``
     - per metadata-editor save
     - 3+
     - extract, write and the ``root.iter()`` header guard over the submitted
       document. Human-paced, single document

Prioritized matrix
##################

Priority is (saved traffic × how often the flow runs) against risk. ``Saved``
counts requests or parser invocations, not broker messages or rows.

.. list-table::
   :header-rows: 1
   :widths: 5 30 22 20 23

   * - ID
     - Finding
     - Count today (1 / 2 / 10 consumers)
     - Status → owner
     - Expected saving, risk, fixture
   * - **R1**
     - Every update run re-downloads **all** advertised ISO references, even the
       run which decided the capabilities are byte-identical.
       ``models/update.py:866-890`` → ``finish_after_metadata_step``
       (``:384``) → ``tasks/update.py:120-204`` → ``plan_registration_references``
       → one ``collect_reference`` per row →
       ``metadata.py:530`` fetch. Nothing asks whether the record of that URL is
       already stored and current
     - per run: ``1 + k`` where ``k`` = references of the service. With 1 / 2 / 10
       references: 2 / 3 / 11 requests per cycle; at a daily beat 60 / 90 / 330
       per month per service — forever, for a service nobody changed
     - confirmed → #1413 (refresh policy for an
       unchanged service), sharing the download seam with #1410. The policy
       landed with #1413 in :ref:`update-refresh-policy`
     - not ``k`` of ``k+1``: the rule of #1413 (:ref:`update-refresh-policy`)
       decides that every run revalidates the advertised references, because
       capabilities equality proves nothing about the ISO documents behind
       them - a stale-but-present record may never be reported as collected.
       What the landed change saves instead is the work the hash *does*
       decide: an unchanged run stages no candidate - no parse, no mapped
       persistence, no candidate deletion - and the run which adopted a
       document stops proving "changed" on every later cycle. Risk:
       #1261/#1263 identity and the failed-reference
       inspectability must survive. Fixture:
       ``tests/django/registry/models/tests_update_refresh_policy.py``
       (requests by ``Session.send`` side_effect exhaustion, parses by
       patched ``OGCServiceXmlMapper.from_xml``) +
       ``tests/django/registry/tasks/tests_metadata_collection.py`` +
       ``tests/django/test_data/iso_metadata/dataset.xml``, count
       ``collect_reference`` messages and ``fetch_metadata_document`` calls
   * - **R2**
     - Dedup identity is ``(described resource, url)``, not document identity.
       ``tasks/service.py:360-372`` keys the plan with
       ``build_reference_key(described, url)``, so the same URL advertised by
       ``n`` different Layers/FeatureTypes plans ``n`` rows and ``n`` downloads
       of the same bytes (the epic's starting observation)
     - one document advertised by 1 / 2 / 10 elements: 1 / 2 / 10 downloads, each
       on its own fresh ``Session`` (no connection reuse across references,
       ``metadata.py:530``)
     - confirmed → #1410
     - ``n-1`` of ``n`` downloads and ``n-1`` TCP/TLS handshakes. Risk: the epic
       invariant that one document may map to one ISO record but must couple to
       **every** correct element; a shared failure may never mark an independent
       reference successful. Fixture:
       ``tests/django/registry/tasks/tests_collect_reference.py`` /
       ``tests_reference_work_queue.py`` with 1/2/10 layers on one link,
       asserting fetch count **and** the number of created relations
   * - **R3**
     - One answered CSW page is parsed twice.
       ``models/harvest.py:952`` (``_check_xml_response``) then ``:1121``
       (``_store_page``) parse the same ``response.content``; on the total-count
       step ``:779`` adds a third parse of its answer
     - per page: 2 parses; a run of 1 / 2 / 10 pages: 2 / 4 / 20. Plus 1 parse of
       the ``hits`` answer and 1 of the probe answer per run
     - confirmed → #1412
     - 1 parse per page (half of the page cost). Risk: the hardened parser of
       ``_parse_answer`` (``resolve_entities=False, no_network=True``) must stay
       on the shared tree, and the exception-report check must keep running
       before ``_store_page``. Fixture: existing
       ``tests/django/registry/tasks/tests_harvesting.py`` with
       ``tests/django/test_data/csw/get_records.xml`` — extend the existing
       ``call_count`` assertions (``:203``, ``:255``, ``:278``) with a parse
       counter
   * - **R4**
     - The harvested record makes a storage round trip through a serialization:
       ``_store_page`` serializes the node with ``pretty_print=True`` and writes
       it (``:1152``), the import task reads it back (``:1763``), and
       ``MDMetadataXmlMapper.from_xml`` serializes and parses the node again
       (``factory.py:86-87``)
     - per record: 4 parses + 2 serializations + 2 storage operations against a
       floor of 1 parse. For 1 / 2 / 10 records: 4 / 8 / 40 parses
     - confirmed → #1415 (duplicate
       transform); the page-level half is #1412
     - 2 parses + 1 serialization per record without changing what is persisted.
       Risk: the file **is** the durability boundary of #895/#958 (a retry
       re-reads it) and the ledger of #1039 keeps it for inspection — any
       single-pass design keeps the stored file and passes the tree to the
       mapper. Fixture: ``tests_harvest_import_fan_out.py``,
       ``tests/django/test_data/iso_metadata/*.xml``
   * - **R5**
     - Every proxied ``GetCapabilities`` re-renders the document from the
       database: read of ``xml_backup`` + parse + full DB→XML sync + serialize
       (``models/document.py:79-114``, ``models/service.py:429-472``, via
       ``proxy/mixins.py:266-276``)
     - 1 render per proxied ``GetCapabilities``: 1 / 2 / 10 client refreshes → 1 /
       2 / 10 renders, each touching the whole layer tree
     - hypothesis → #1415 measures first;
       a cache here is a cross-request cache, which #1408 keeps out of scope
       by default
     - unknown until measured per deployment. Risk: the answered document must
       reflect curator edits and permission-scoped camouflage immediately;
       staleness would be a security-relevant change. Fixture:
       ``tests/django/registry/mrmap-proxy/tests_wms_proxy.py:219`` already
       asserts the answer; a render counter is the missing half
   * - **R6**
     - ``DescribeFeatureType`` has **no reachable first-party call path**.
       ``models/service.py:1125-1147`` and ``:1166`` are called only from
       ``tests/django/registry/models/tests_document.py``; ``FeatureTypeProperty``
       rows come from the WFS 2.0.0 **capabilities** config
       (``mappers/configs/wfs200.py:230``), not from a describe
     - 0 requests in registration, update, monitoring, harvest and preview today
     - confirmed (no traffic) → #1414 must start
       from this fact
     - batching would save 0 requests on today's code. Either a consumer exists
       that the audit cannot see (an operator command, an external script) or the
       epic's premise needs re-reading before any batching work is scheduled.
       Fixture: none exists; a call-path test would be the assertion that no
       production path reaches it
   * - **R7**
     - Spatially secured WMS ``GetFeatureInfo`` sends a request whose answer it
       cannot use. ``proxy/wms_proxy.py:460`` assigns the **Response** of
       ``send_request`` to ``request``, then ``:462`` reads ``request.params`` —
       an attribute of ``requests.Request`` (and of the ``OGCRequest`` subclass,
       ``ows_lib/request/ogc_request.py:80``), not of a Response. The
       ``AttributeError`` lands in ``except Exception: pass`` (``:486``) and the
       caller gets ``PermissionDenied``. If it were repaired, ``:399`` sends the
       same request again and ``:402-424`` two more variants
     - per request today: 1 wasted upstream request + a denial. Repaired
       naively: 3 upstream requests per ``GetFeatureInfo``
     - confirmed → not a child of #1408: **proposed
       new issue** (proxy correctness), asked with
       ``scripts/wip ask``
     - 1 request per such call, and the removal of a guaranteed denial. Risk:
       the answer must stay permission-checked — the second variant exists only
       to read ``gml:boundedBy`` for the area test (``:471-484``). Fixture:
       none — ``tests_wms_proxy.py`` has no ``GetFeatureInfo`` scenario
   * - **R8**
     - The CSW step-size probe asks 1..⌈log2(step)⌉ ``hits`` requests per run on
       top of the total-count request (``models/harvest.py:862-899``), plus one
       fallback request when the catalogue answers 0 records (#689)
     - default step 50 (``:260``): 1 + up to 6 hits requests per run; step 1000:
       1 + up to 10
     - no change (deliberate, bounded, #694)
     - none claimed. The probe is what keeps a run from re-refusing every page;
       its cost is paid once per run and it is the mechanism #694 chose.
       Recorded so #1411 does not "optimize" it away
   * - **R9**
     - ``OgcClient.__init__`` takes ``session: Session = Session()``
       (``core.py:56-61``): a **module-level** session shared by every client
       built without one, carrying cookies across hosts, threads and messages.
       ``serializers/service.py:606`` is exactly such a caller
     - 0 requests from the serializer path (bytes, not a URL), but one shared
       connection pool and cookie jar for an unbounded set of services
     - confirmed → not a child of #1408: **proposed new issue**; #1410 must not
       widen it (its shared acquisition must stay inside one auth scope)
     - no traffic saved; the finding is an isolation hazard, made worse by any
       response reuse. Fixture: a unit test that two clients built without a
       session do not share cookies
   * - **R10**
     - ``fetch_metadata_document`` never authenticates an advertised link
       (``models/metadata.py:536``: ``# FUTURE: Re add authentication``), so a
       protected ISO reference answers 401 → ``NoContent`` → a decided failed
       reference
     - 1 request per protected reference, always failing the same way, retried
       by nothing but the task's own bounded retry
     - confirmed, needs a **decision** on the auth
       scope of an advertised link → ask with ``scripts/decisions``, then #1410
       implements the answer
     - removes a class of guaranteed-redundant failing requests. Risk: sending
       service credentials to a **different** host than the service's is a
       widening of access — this must be a decided norm, not a side effect
   * - **R11**
     - ``OgcService.remote_capabilities`` (``models/service.py:293-306``) is the
       only OGC fetch outside the client: it passes **no timeout** and calls
       ``session.send(request.prepare())``, and ``Session.send`` resolves
       redirects on its own — ``allow_redirects`` defaults to True, the chain is
       bounded only by ``max_redirects`` (30) and may leave the host, each hop
       re-sent with the same absent timeout. Neither #1100's same-host rule nor
       the timeout norm applies, and ``session.send`` also skips the client's
       content-type judgement
     - 1 request per update run per service (more with hops); unbounded
       duration when the upstream stalls
     - confirmed → not a child of #1408: **proposed
       new issue** (small: route it through the service's client)
     - none in count; it removes an unbounded worker hold and an off-policy
       redirect walk. Fixture: ``tests/django/registry/tests_capabilities_integrity.py``
       area, asserting the timeout and the redirect refusal
   * - **R12**
     - The list serializer builds a whole client per row to answer
       ``preview_url`` (``serializers/service.py:589-610``): a storage read plus a
       full capabilities parse per serialized service, in the WMS and WFS list
       fieldsets
     - 1 / 2 / 10 rows asking the field: 1 / 2 / 10 reads + 1 / 2 / 10 parses. Mr.
       Map sends **0** upstream requests; the browser fetches the named URL
       itself
     - confirmed → #1415 (transform), with a
       security question for the owner of the proxy: the URL names the
       **upstream** operation endpoint, so a caller who may view a secured
       service gets a direct upstream ``GetMap`` which never passes the proxy
     - ``n-1`` of ``n`` parses if the URL were answered from a cheaper
       projection. Risk: any answer must keep #1044 (no network on a stored
       read) and must not leak an upstream URL where the deployment expects
       camouflage. Fixture: an API test over a 1/2/10 service list with a parse
       counter
   * - **R13**
     - A preview parses its stored document two or three times:
       ``stored_client`` parse → serialize → client parse (``preview.py:102-107``);
       ``feature_preview_image`` (``:452``) and ``catalogue_preview`` (``:555``)
       build a second client from the same bytes
     - per preview request: 2 parses (WMS/WFS data preview) or 3 (WFS preview
       image, CSW preview). 1 / 2 / 10 preview clicks: 2 / 4 / 6 parses
     - confirmed → #1415
     - 1-2 parses per preview request; upstream requests stay 1. Risk: the first
       parse exists to refuse an exception report — the check has to move onto
       the client's tree, not disappear. Fixture: the preview tests behind
       ``views/service.py:205``
   * - **R14**
     - ``/csw`` re-reads and re-parses every served record on every request
       (``csw/views.py:267-299``)
     - 1 read + 1 parse per matched record per request: a page of 1 / 2 / 10
       records costs 1 / 2 / 10 parses, again on the next request
     - hypothesis → new issue proposal (a bounded
       parse cache is a cross-request cache, out of #1408 by default). The
       which-records-and-fields part is #1387, not this epic
     - up to ``page size`` parses per request if a staleness-safe cache exists.
       Risk: an edit to a record must invalidate immediately; serving a stale
       document on an OGC endpoint is a content error. Fixture:
       ``tests/behave/features/`` CSW scenarios already pin the served content
   * - **R15**
     - Concurrent deliveries can fetch the same CSW page. ``fetch_records`` only
       pre-checks stored pages when the message is a recovery/retry/redelivery
       (``tasks/harvest.py:1671-1673``), ``_fetch_range_step`` re-checks per step
       (``models/harvest.py:1063-1066``), and the arbitration is in
       ``_store_page`` **after** the request (``:1130-1137``, #688)
     - two deliveries of one page: 2 identical upstream requests, 1 stored page.
       Ten concurrent deliveries: 10 requests, 1 page
     - confirmed → #1411
     - ``n-1`` of ``n`` page requests while keeping the snapshot semantics of
       #690. Risk: the stored-page count is the idempotency key; any in-flight
       coalescing must not make a refused page invisible to
       ``log_missing_records``. Fixture: ``tests_harvest_duplicated_delivery.py``
       and the ``call_count`` assertions of ``tests_harvesting.py:640``
   * - **R16**
     - An ETF conformity check holds no session and no timeout:
       4 fixed requests + one ``GET <run>/progress`` per polling interval, each on
       a fresh connection (``helper/plugins/etf.py``); ETF itself then fetches
       ``BASE_URL_FOR_ETF + resource.get_xml_view_url()`` **back into** MrMap,
       which re-renders the document from the database (R5's path)
     - per check: ``4 + polls`` outbound, plus the inbound re-render. With
       ``polling_interval_seconds`` doubling to its max, a long run is dozens of
       unpooled requests
     - confirmed → #1415 for the
       re-render; the transport itself is not a child of #1408 (proposal)
     - bounded, but each unpooled request pays a handshake and each unbounded
       one can hold a worker; the ``requests`` norm in the project's OGC skill
       asks for an explicit timeout. Fixture:
       ``tests/django/registry/tasks/tests_conformity_tasks.py``
   * - **R17**
     - A logged proxied response is decoded twice: once for the mask
       (``proxy/wms_proxy.py:369-375``) and again from storage in the analysis
       task (``models/security.py:609-640``, published per saved response log by
       ``:544-557``)
     - per logged secured ``GetMap``: 2 image decodes + one full alpha-channel
       list. 1 / 2 / 10 requests → 2 / 4 / 20 decodes
     - confirmed, low priority → #1415
     - 1 decode per logged response. Risk: the analysis runs after the response
       and must not hold the body in memory across the request
   * - **R18**
     - A WMS/WFS/CSW monitoring run rebuilds the client — storage read, full
       capabilities parse, session build and key-file read
       (``models/security.py:85-98``, ``models/service.py:237-245``) — once per
       probe message (``tasks/monitoring.py:16-41``, one message per probe in the
       chord)
     - a run with ``p`` probes: ``p`` upstream requests (required) + ``p``
       capability parses and ``p`` key-file reads
     - **no change** on the requests (independence
       is a #1408 invariant: probes measure today's service, each on its own);
       the per-message parse cost is inherent to one message per probe → record
       only
     - nothing claimed. If a deployment measures it as a problem, the fix is
       cheaper parsing, not shared probes
   * - **R19**
     - The legacy MapBender search parses its answer twice and detaches every
       record node again (``mapbender_compatibility/views.py:113``, ``:120``);
       each result row also re-derives a ``GetRecordById`` URL through a
       capabilities xpath (``:133-146``)
     - per search: 2 + ``r`` parses for ``r`` rows, on 1 upstream request
     - **no change** (explicit compatibility
       exception in ``AGENTS.md``) unless a consumer asks
     - none claimed; recorded so the endpoint is not mistaken for live design
       work

Reuse correctness per flow
##########################

The question #1409 asks for each flow: may the same response be handed to
several consumers?

.. list-table::
   :header-rows: 1
   :widths: 22 16 62

   * - Flow
     - Reuse
     - Why
   * - Advertised ISO references of one run (R1, R2)
     - **yes**, inside one run and one auth scope
     - The document is the same bytes for every element advertising it; the
       *outcome* stays per reference. #1263's per-row lease and #1261's supersede
       bookkeeping are what make the coupling per element, so sharing the fetch
       must leave the rows, the counters and the failure kinds alone
   * - Update run of an unchanged service (R1)
     - **the references, always** — decided by #1413
     - :ref:`update-refresh-policy`: the sha256 comparison of
       ``document_equals`` (``models/document.py:66-71``) proves
       *capabilities* equality, not record equality, so the advertised
       documents are revalidated every run; what an unchanged run skips is
       the candidate, and an adoption now refreshes the stored document the
       comparison reads
   * - Monitoring probes (R18)
     - **never**
     - Independent probes measure the service independently; coalescing would
       change what a monitoring run measures, which the epic rules out and
       #682's stored artifacts would make invisible
   * - Security proxy responses (R7, and ``proxy/mixins.py:285-348``)
     - **never across callers or auth contexts**
     - The answer is computed for one user's areas and one service credential;
       the caller's ``Authorization``/``Cookie`` headers are stripped before the
       send (``:314-315``). Any cache would have to be keyed by the permission
       decision, not the URL — which is the "unrelated proxy response caching"
       the epic excludes
   * - Live previews (R13)
     - **no** (transient by design)
     - ``PreviewProxyMixin.log_response`` is deliberately a no-op
       (``preview.py:264``): a preview is not a stored state
   * - Harvest pages (R3, R15)
     - **yes within one delivery**, and coalescing across deliveries only with
       the #690 trace intact
     - The stored-page count keyed on ``requested_url`` is the page's identity
       (``models/harvest.py:959-963``); the short-page and refusal traces of #690
       must survive, and paging completeness is an epic invariant
   * - ``/csw`` served documents (R14)
     - only with a staleness-safe key
     - The document a record serves changes with curator edits; #1150's
       ``check_xml_backups`` posture is that a missing/broken document is an
       operator problem, not something to paper over

Already answered — do not recreate it
#####################################

.. list-table::
   :header-rows: 1
   :widths: 14 86

   * - Fix
     - What it already guarantees here
   * - #1044
     - ``Service.capabilities`` and ``Service.client`` never fetch: a missing
       stored document raises ``CapabilitiesBackupMissing`` instead of paying a
       synchronous ``GetCapabilities`` per access. The URL-string branch of
       ``OgcClient.__init__`` (``core.py:66-74``) is the shape it removed —
       nothing in ``backend/`` may pass a URL to a client constructor again
   * - #688
     - A page whose records are already stored is not asked again, and
       ``_store_page`` re-counts under the job lock (``models/harvest.py:1130-1137``).
       R15 is about the window **before** that lock, not about a missing check
   * - #694 / #690
     - The step-size probe, the size-scaled timeout and the bounded halving; the
       missing-record trace which distinguishes an end-of-catalogue from a silent
       cap. Any page coalescing must keep both
   * - #1263 (+ #1259, #1257, #1265)
     - The reference work row: one plan per run, one row per logical reference,
       single-use claim token, lease, bounded retry, authorized retry, orphan
       sweep, recovery after restart, and the counters the process reports.
       Shared acquisition runs **under** this, never instead of it
   * - #1261
     - ``drop_superseded_relations_for_link`` closes a stale coupling when a link
       resolves to a different record — the reason re-collecting a reference is
       idempotent for relations today
   * - #1274
     - The update's metadata step is the registration machinery, re-planned per
       run (which is exactly R1's cost) and reading the references of the
       published service only
   * - #1100
     - ``MAX_REDIRECTS`` and the same-host refusal — and the reason R11 is a
       finding rather than a style comment
   * - #981 / #982 / #990
     - ``extract_mapped_values`` / ``mapped_values`` answer a document from one
       forward traversal with no persistence and no global cache; identity rules
       keep a record's ``fileIdentifier`` across updates
   * - #1150, #1153, #958, #895
     - stored-document integrity, the proxy log's independence from the response,
       coalesced import progress, and the retry/keep semantics of the import
       files

Instrumentation outline (deterministic call-count baselines)
############################################################

No production telemetry. Each hotspot gets a host-runnable Django test that
counts at the transport seam, the same way the harvest suite already does
(``tests/django/registry/tasks/tests_harvesting.py:181-278``,
``:323-370`` — ``patch.object(OgcClient, "send_request", side_effect=...)``
plus ``self.assertEqual(mock.call_count, N)``).

Two seams are enough for every row:

- **requests**: patch ``OgcClient.send_request`` for the client rows, and
  ``registry.models.metadata.fetch_metadata_document`` for the advertised-reference
  rows. Patch the *function on the importing module* where the caller imported it
  by name, and record ``(method, url, timeout)`` per call so a test can assert
  the identity of what was asked, not just how often.
- **parses**: patch ``lxml.etree.fromstring`` **inside the module under test**
  (``registry.models.harvest``, ``registry.mappers.factory``,
  ``registry.helper.preview``, ``csw.views``, ``registry.serializers.service``)
  with a counter wrapper that returns the real result, and assert the count per
  unit. A wrapper keeps the assertion about *this* flow rather than about every
  parse in the process.

Per-row baseline, to be added by the owner before the change and re-measured
after it:

.. list-table::
   :header-rows: 1
   :widths: 10 40 22 28

   * - Row
     - Deterministic fixture
     - Unit
     - Baseline to pin
   * - R1
     - a WMS with ``k`` advertised links; run one update with the byte-identical
       capabilities answer
     - per update run
     - ``1`` capabilities request + ``k`` reference fetches
   * - R2
     - ``k`` Layers advertising the **same** link (1 / 2 / 10)
     - per registration
     - ``k`` fetches, ``k`` relations, ``1`` distinct document body
   * - R3
     - ``tests/django/test_data/csw/get_records.xml`` as one answered page
     - per page
     - 2 parses → 1 after #1412
   * - R4
     - ``tests/django/test_data/iso_metadata/dataset.xml`` as one stored record
       file
     - per record import
     - 4 parses + 2 serializations
   * - R12
     - a list of 1 / 2 / 10 WMS rows with ``preview_url`` in the sparse fieldset
     - per list response
     - ``n`` storage reads + ``n`` parses
   * - R13
     - one preview request per protocol
     - per request
     - 2 parses (WMS/WFS), 3 (WFS image, CSW), 1 upstream request
   * - R15
     - two concurrent deliveries of one page (the existing duplicated-delivery
       harness)
     - per page
     - 2 upstream requests, 1 stored page
   * - R7
     - a spatially secured WMS, ``GetFeatureInfo`` outside the allowed area
     - per call
     - 1 upstream request + the current denial (the test which shows the bug
       before anybody fixes it)

The rows marked *hypothesis* (R5, R14) get a measurement, not a test: count in a
throwaway test over a realistic fixture (a catalogue's page, a list of services
with a real capabilities document) and put the number in the issue before any
change is designed.

Proposed issues for confirmed uncovered cases
#############################################

These are confirmed findings with **no** child of #1408 to own them. Filing
issues is a human act, so they are listed here and handed over with
``scripts/wip ask`` rather than created from this session:

- **P-1 (from R7)** — spatially secured WMS ``GetFeatureInfo``: one upstream
  request is sent and its answer discarded through an ``AttributeError`` on a
  Response read as a Request, and every such call answers ``PermissionDenied``.
  Either the path is repaired (and then the double/triple request must be
  designed out) or it is removed as unreachable code with its fixture.
- **P-2 (from R11)** — ``OgcService.remote_capabilities`` should ask through the
  service's client: it is the only OGC fetch with neither the client's timeout
  nor #1100's redirect policy.
- **P-3 (from R9)** — ``OgcClient``'s module-level default ``Session`` couples
  unrelated services through one cookie jar and connection pool.
- **P-4 (from R10)** — the auth scope of an advertised ISO reference: a design
  decision (``scripts/decisions``), not a patch, because sending service
  credentials to another host can widen access.
- **P-5 (from R14)** — ``/csw`` document serving re-parses every record per
  request; needs a measurement first, and a staleness-safe key before any cache.
- **P-6 (from R16)** — the ETF client's unpooled, timeout-less transport.

SQL-only findings, crosslinked to #1387 (no work here)
######################################################

Recorded once, owned there: ``get_stored_page_count`` is evaluated three times
per page path (``models/harvest.py:974``, ``:1064``, ``:1134``); the monitoring
``GetMapProbe.build_request`` runs
``layers.with_inherited_attributes_cte()`` per probe message
(``models/monitoring.py:890+``); Layer ``GetMap``/``GetFeatureInfo`` URL
generation repeats operation-format ORM lookups (the epic names #1387/#1393 for
this); ``catalogue_preview`` and ``_remote_search_entry`` read related rows per
served record; the proxy's ``prefetch_whole_service`` +
``prepare_with_security_info`` (``proxy/mixins.py:107-115``) is the read plan of
every proxied request. Each is a read-plan question for epic #1387 and its
guard suite, not a request or parse redundancy of this one.

Recorded no-change decisions
############################

- Monitoring probe independence (R18) and the step-size probe (R8): deliberate,
  bounded, decided by #694/#690 and by the epic's own out-of-scope list.
- Live preview transience (R13's logging) and the MapBender compatibility
  shapes (R19): explicit project exceptions.
- The per-message client build of the harvest import
  (``tasks/harvest.py:148-158``): the import runs on stored documents only and
  ``InitialError`` retry semantics depend on that boundary.
- ``system/status.py``: one bounded, deadline-capped session per snapshot — the
  transport pattern this page recommends, not a candidate.
