.. _usage:


=====
Usage
=====


Metadata Catalouge
==================
Mr. Map provides a `csw <https://www.ogc.org/standard/cat/>`_ implementation to provide collected metadata.

The csw api is available under ``{schema}://{hostname}/csw``. The usage is described by the ogc specs and is not content of this documentation.

Inspect metadata records
########################

Open a dataset or service metadata record from the explorer or a catalogue's Records tab.
Both record types have the same detail page:

* Overview shows parsed identity, classification, quality and provenance. Choice fields use the
  labels provided by the API schema.
* Spatial and temporal extent shows the parsed geometry, reference systems and time periods.
  Missing extents are stated explicitly.
* Contacts and use shows contact details, licensing and usage terms.
* Relations lists linked layers, feature types or services, including each link's origin and
  whether it was linked by a user. The catalogues that harvested the record are listed separately.
  A graph view shows up to 100 descriptive links; use the paginated tables for the complete list.
* Harvest history shows the outcome and timing of each run and links to the job and catalogue.
* Change log shows recorded field changes and their previous and new values.

Tabs can be linked directly, for example ``DatasetMetadataRecord/<id>/show/relations``.
The header offers edit and delete actions when the backend grants those object permissions.
The "Written more than once" status reflects ``is_customized``; it does not prove that a user
manually corrected the record. The source action opens the recorded origin URL, when available.

The header also offers *Available services*, which answers which services can deliver what the
record describes: the endpoints the record advertises itself, the endpoints of the harvested service
records which name it and, listed apart from those, the resources which are registered already.
Discovery reads stored data alone and asks no service. A candidate can be checked before it is used;
that answer separates the layer and feature type hints the endpoint confirmed from the ones it did
not, which stays a decision of the user instead of a guessed layer. Choosing a candidate adds it to
the current map without registering it, and the layers which are already on the map stay. A remote
endpoint is asked without credentials, only an endpoint of the MrMap origin is asked with the token
of the session. The same action belongs to every result of the metadata explorer.

A candidate whose endpoint delivers can be registered from the same dialog. *Register service* opens
the ordinary registration form of the service that endpoint announced, prefilled with its
capabilities endpoint, and names beside it the record and stored document it came from together with
the url as the record advertised it: a record may offer the same endpoint as a plain path, while the
registration form asks an url for its service, request and version parameters, so the completed url
is the one the delivered document answered and not a guess of the record. The form registers nothing
until it is saved; the task which follows reports itself with the other background work of Mr. Map.
A registration which already delivers the record is named there with a link to it, because a second
registration of one endpoint creates a second resource. Registering asks the permission of the
service, never the permission of the record: reading the candidates of a record grants nothing over
the services it advertises, and an endpoint which refused or which is no service this registry
knows is answered with that reason instead of a form.

Collect Metadata
################

There are much ways Mr. Map collect metadata records which are described in this subsection.

1. Found by ogc service capabilities
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
If you register wms or wfs services, Mr. Map will find related metadata records inside the capabilities document and collect them inside background tasks.

2. harvested by other csw's
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Register other csw's as a service resource in Mr. Map. Mr. Map then will harvest them inside background tasks.


3. imported by file system
~~~~~~~~~~~~~~~~~~~~~~~~~~
You can also import metadata records by file system import.

First of all you need the container id of the backend container. Run the following command to list all running containers.

.. code-block:: console

    $ docker ps
    CONTAINER ID   IMAGE                           COMMAND                  CREATED        STATUS             PORTS                                             NAMES
    0dde49351793   mrmap_celery-worker             "/opt/mrmap/.bash_sc…"   18 hours ago   Up About an hour   8001/tcp, 0.0.0.0:3002->5678/tcp                  mrmap-celery-worker-1
    e383a3f0cba2   mrmap_backend                   "/opt/mrmap/.bash_sc…"   19 hours ago   Up About an hour   0.0.0.0:8001->8001/tcp, 0.0.0.0:3001->5678/tcp    backend-dev
    39b1d0412b62   mrmap_celery-beat               "/opt/mrmap/.bash_sc…"   19 hours ago   Up About an hour   8001/tcp                                          mrmap-celery-beat-1
    3ddfaa3a3646   postgis/postgis:15-3.3-alpine   "docker-entrypoint.s…"   20 hours ago   Up About an hour   0.0.0.0:5555->5432/tcp, :::5555->5432/tcp         mrmap-postgis-1
    cbe33a40f90d   redis:7.2.0-alpine              "docker-entrypoint.s…"   24 hours ago   Up About an hour   0.0.0.0:5556->6379/tcp, :::5556->6379/tcp         mrmap-redis-1
    27d72bcacffd   camptocamp/mapserver:7.6        "/docker-entrypoint …"   7 weeks ago    Up About an hour   8080/tcp, 0.0.0.0:8090->80/tcp, :::8090->80/tcp   mrmap-mapserver-1

Then you can simply run ``docker cp ./test.xml e383a3f0cba2:/var/mrmap/import`` or ``docker cp ./test.xml backend-dev:/var/mrmap/import`` to copy files to the container.

If the ``celery-beat`` and ``celery-worker`` container is running, the Mr. Map will find the new files automatically. Not importable files are renamed as ``ignore_{datestamp}_{oldfilename}`` and will be ignored by Mr. Map. 
In this case you need to study the logs to get more information why the file can't be imported by Mr. Map.

.. image:: ../images/sequence_diagram_file_import.svg
  :width: 100%
  :alt: Celery tasks livecycle

Protected services in the map viewer
====================================

When adding a protected WMS, enter its username and password in Add Resource.
The viewer uses these credentials for capabilities and assigns them to operations
of that newly added service on the same origin (scheme, host and port).
Advertised endpoints on other origins require a separate, explicit assignment.
Authenticated requests do not follow redirects; configure the final endpoint directly.
The remote service must permit browser access through CORS, including the configured headers.

Use Manage authentications in the viewer toolbar or a layer's context menu to add
Basic or custom header credentials, update header values, and assign or remove
credentials for each operation. The layer menu limits the operation list to that
layer and its descendants. Removing an assignment permits an unauthenticated
request; deleting a credential retains its assignments and blocks those requests
with a missing-credentials message until they are configured or removed.
GetMap and GetFeatureInfo activation remain independent.

Click a layer's name to open Layer settings in the bottom drawer. Its opacity, style, legend
and dimension controls stay outside the tree, keeping layer rows compact and visible.
Selecting another layer updates the same panel. The context menu's Style and Dimensions
actions open the same settings tab. On wider screens the bottom settings drawer sits
beside the right-hand tree so the tree retains its full height. Visibility and query
activation remain independent.

Every layer the viewer can draw offers an opacity slider in this panel, blending it between
invisible and fully drawn in five percent steps. The value belongs to the viewer session and not
to the composed map: exporting, sharing or saving a document does not carry it, while panning,
zooming and reloading the content keep it. A layer blended to another value than its neighbour is
requested and drawn separately, so one layer never dims another: a raster layer gets its own map
image, and a feature layer dims its outlines, fills and point symbols together. A layer which
advertises neither styles nor dimensions still offers this control.

Dimensions are initialized from the WMS capabilities. Lists and numeric ranges use the
advertised values and resolution. A discrete time slider represents advertised time
steps, including calendar intervals and irregular timestamp lists, in UTC. Dragging
previews a time; releasing applies it to both map and identify requests. Previous/next
buttons move one advertised step. The exact date/time field applies when you leave it.
Continuous time ranges retain the exact date field without an invented slider step.
Choose Server default to reset a time selection.

Use Pin timeline to keep a compact time slider over the map while the layer panel is
closed. Pinning does not pan or resize the map. The timeline follows its layer when
layers are reordered and disappears if that layer is removed. Unpin timeline hides it.

Resources asking for different dimension values are requested separately, and the
selections survive in the context document. A dimension icon beside the layer identifies
non-default values; its tooltip lists the selected values.

Select Identify and click a location, or right-click the map, to fetch GetFeatureInfo
results. The viewer shows results in an overlay inspector without moving or resizing
the map, using a side panel on larger screens and a bottom sheet on smaller screens.
Every queryable layer is asked with its own request, because a service may spend the
FEATURE_COUNT of a combined query on its first layers and leave the rest of them empty;
the layers of one service still share one map request.
Protected requests use their assigned headers; unprotected requests are fetched directly.
The inspector shows loading, empty and error states per layer, with retry for failed
requests.
JSON feature collections support feature navigation. HTML tables are extracted as text
and table structure; remote scripts and other active markup are never executed.
The raw response can be expanded and downloaded. Collapse the inspector to uncover
the map while keeping results, or clear the selection to cancel pending requests.

The viewer keeps a local draft of the composed map, so a browser reload restores it, and offers
three transfer actions: "export map as file" downloads the composed map as a GeoJSON document,
"open map from file" loads such a document back through the same import validation as any URL
import, and "share map link" puts the document into the link fragment for a shareable URL.
Exports and share links never carry credentials - protected services ask for them again - and a
shared link wins over the local draft when both are present. Saved server side map contexts
(`MapContext`) describe their layers by references to registry resources and cannot yet represent
a composed viewer document with its own service URLs, drawings, styles and dimensions; a
server-side document storage API would be required to offer named, permissioned saved maps and
is reported as follow-up work.

Credentials remain in the viewer session. The JSON context editor omits secret values from
copyable documents, retaining assignments so a recipient can enter their own
credentials. Saving local JSON edits preserves existing session secrets only for
unchanged credential identities, headers and origins.

Supported offerings in the map viewer
=====================================

The map viewer renders exactly one encoding combination of the
`OWS Context GeoJSON profile <https://docs.ogc.org/is/14-055r2/14-055r2.html>`_:
a WMS offering (``http://www.opengis.net/spec/owc-geojson/1.0/req/wms``, accepted
also in its legacy ``owc/1.0`` and ``owc-atom/1.0`` spellings) whose ``GetMap``
and ``GetFeatureInfo`` operations are offered as HTTP ``GET`` with an ``href``.

Everything else in an imported document is kept but not executed:

* offerings of other codes (e.g. WMTS, WFS, WCS) and inline or referenced
  contents (e.g. GeoTIFF, GML) are preserved unchanged through import, editing
  and export, so the document round-trips losslessly;
* operations offered with other methods (e.g. ``POST`` with a request body) are
  not executed;
* the layer tree marks each resource that cannot be rendered with a warning
  indicator naming the unsupported offering code, operation method or content
  type, and the status bar names the resources the document asks to render while
  the supported resources keep rendering.

Adding renderers or executors for further offerings, methods or content types
are separate increments; supporting every OWS offering is not a conformance
requirement of the viewer.
