"""Bounded, transient service previews. No mapper persistence or background jobs."""
import base64
import json
import math
import time
from functools import cached_property
from io import BytesIO
from urllib.parse import parse_qsl, urlencode, urlsplit

from django.contrib.gis.geos import GeometryCollection, Polygon
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory
from django.urls import reverse
from django.utils.timezone import now
from epsg_cache.utils import adjust_axis_order
from guardian.core import ObjectPermissionChecker
from lxml import etree
from PIL import Image, UnidentifiedImageError
from registry.enums.service import HttpMethodEnum, OGCOperationEnum, OGCServiceVersionEnum
from registry.mappers.factory import MDMetadataXmlMapper
from registry.managers.security import GEOMETRY_DATA_TYPES
from registry.models.harvest import HarvestedMetadataRelation
from registry.models.metadata import MetadataRelation
from registry.models.service import FeatureType, Layer
from registry.ows_lib.client.core import OgcClient
from registry.ows_lib.request.ogc_request import OGCRequest
from registry.ows_lib.request.utils import update_queryparams
from registry.ows_lib.wfs.xml_builder import WFSBuilder
from registry.ows_lib.wfs.wfs import WebFeatureServiceClient
from registry.helper.preview_image import render_feature_collection
from registry.proxy.mixins import Http423, OgcServiceProxyView
from registry.proxy.wfs_proxy import WebFeatureServiceProxy
from registry.proxy.wms_proxy import WebMapServiceProxy
from requests import Request, Session
from requests.exceptions import RequestException

FEATURE_LIMIT = 500
PAGE_SIZE = 25
RESPONSE_LIMIT = 8 * 1024 * 1024
TIME_LIMIT = 15
GMD = "http://www.isotc211.org/2005/gmd"
INFO_FEATURE_COUNT = 10
# Identify results are rendered by the browser, so only self contained machine readable
# formats are negotiated for them. An upstream `text/html` body would be answered by the
# security proxy on the MrMap origin and could read the credentials stored there.
INFO_FORMATS = ("application/json", "application/geo+json", "application/gml+xml",
                "application/vnd.ogc.gml", "application/xml", "text/xml", "text/plain")


class PreviewError(Exception):
    def __init__(self, code, status=422):
        self.code = code
        self.status = status


class PreviewSession(Session):
    """Apply limits to every upstream read, including spatially secured POSTs."""
    def prepare_request(self, request):
        prepared = super().prepare_request(request)
        if prepared.hooks.get("response"):
            # Digest authentication consumes a 401 body inside its response
            # hook, before Session.send returns. Bound that body first too.
            prepared.hooks["response"].insert(0, self.buffer_auth_response)
        return prepared

    def buffer_auth_response(self, response, **kwargs):
        with response:
            return self.buffer_response(response)

    def buffer_response(self, response):
        chunks = []
        size = 0
        for chunk in response.iter_content(64 * 1024):
            size += len(chunk)
            if size > RESPONSE_LIMIT or time.monotonic() - self.started_at > TIME_LIMIT:
                raise PreviewError("limit", 502)
            chunks.append(chunk)
        response._content = b"".join(chunks)
        response._content_consumed = True
        return response

    def send(self, request, **kwargs):
        self.started_at = time.monotonic()
        kwargs.update(timeout=(3, 3), stream=True, allow_redirects=False)
        with super().send(request, **kwargs) as response:
            if 300 <= response.status_code < 400:
                raise PreviewError("unavailable", 502)
            if response.status_code in (401, 403):
                raise PreviewError("denied", 403)
            if response.status_code >= 400:
                raise PreviewError("unavailable", 502)
            return self.buffer_response(response)


def stored_client(service):
    # A missing backup must not trigger the model's unbounded remote fallback.
    try:
        capabilities = service.xml_backup
    except (FileNotFoundError, ValueError):
        raise PreviewError("discovery")
    session = PreviewSession()
    session.auth = service.get_session_for_request().auth
    client = OgcClient(capabilities=etree.tostring(parse_xml(capabilities)), session=session)
    if client.service_version != OGCServiceVersionEnum(service.version).label:
        raise PreviewError("discovery")
    return client


def operation_request(service, params, method="GET", data=None):
    operation = OGCOperationEnum(params["REQUEST"])
    url = service.operation_urls.get(operation=operation.value, method=HttpMethodEnum(method).value).url
    # No incoming headers/cookies are copied to the registered endpoint.
    return Request(method=method, url=update_queryparams(url, params), data=data,
                   headers={"Content-Type": "application/xml"} if data else {})


def parse_xml(content):
    try:
        root = etree.fromstring(content, etree.XMLParser(resolve_entities=False, no_network=True))
    except etree.XMLSyntaxError:
        raise PreviewError("malformed")
    if root.xpath("//*[local-name()='ExceptionReport' or local-name()='ServiceExceptionReport']"):
        raise PreviewError("ogc")
    return root


def validate_image(content):
    if content.lstrip().startswith(b"<"):
        parse_xml(content)
        raise PreviewError("format")
    try:
        with Image.open(BytesIO(content)) as image:
            if image.width > 2048 or image.height > 2048:
                raise PreviewError("limit", 502)
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, EOFError, Image.DecompressionBombError):
        raise PreviewError("malformed")


def checked_bbox(value):
    try:
        bounds = [float(number) for number in value.split(",")]
    except (ValueError, AttributeError):
        raise PreviewError("extent", 400)
    if (len(bounds) != 4 or not all(math.isfinite(number) for number in bounds)
            or not -180 <= bounds[0] < bounds[2] <= 180
            or not -90 <= bounds[1] < bounds[3] <= 90):
        raise PreviewError("extent", 400)
    return bounds


def integer(value, default, maximum):
    try:
        number = int(value if value is not None else default)
    except (TypeError, ValueError):
        raise PreviewError("malformed", 400)
    if number < 1 or number > maximum:
        raise PreviewError("limit", 400)
    return number


def negotiate_info_format(formats):
    """Return the most structured advertised identify format, never a markup format.

    Formats may carry parameters (``text/plain; charset=utf-8``), so only the media type
    before the first ``;`` decides. Returns ``None`` if nothing renderable by the browser
    is advertised.
    """
    advertised = {item.split(";")[0].strip().lower() for item in formats}
    return next((name for name in INFO_FORMATS if name in advertised), None)


def identify_request(service, selection, version, info_format):
    """Build the same-origin security proxy URL for an identify done in the browser.

    Only the parameters the registry may decide from the stored capabilities are prefilled;
    the caller adds the viewport (``BBOX``, ``WIDTH``, ``HEIGHT``) and the pixel. The proxy
    resolves the registered operation url, applies the stored service credentials and the
    spatial security of the caller itself, therefore no upstream address or credential
    leaves the backend.
    """
    params = {"SERVICE": "WMS", "VERSION": version, "REQUEST": "GetFeatureInfo",
              "LAYERS": selection, "QUERY_LAYERS": selection, "STYLES": "",
              "FEATURE_COUNT": INFO_FEATURE_COUNT, "INFO_FORMAT": info_format}
    params["CRS" if version == "1.3.0" else "SRS"] = "EPSG:4326"
    return f"{reverse('wms-operation', kwargs={'pk': service.pk})}?{urlencode(params)}"


def selected_configuration(service, selection, client):
    """Negotiate only advertised formats/CRS using the stored capabilities."""
    root = client._capabilities_etree
    protocol = service.service_type
    if protocol == "WMS":
        element = service.layers.with_inherited_attributes_cte().filter(identifier=selection).first()
        nodes = root.xpath("//*[local-name()='Layer']/*[local-name()='Name' and text()=$name]/..", name=selection)
        if not element or not nodes:
            raise PreviewError("stale")
        node = nodes[0]
        crs = node.xpath("ancestor-or-self::*[local-name()='Layer']/*[local-name()='CRS' or local-name()='SRS']/text()")
        crs = {part.upper() for item in crs for part in item.split()}
        formats = root.xpath("//*[local-name()='Request']/*[local-name()='GetMap']/*[local-name()='Format']/text()")
        image_format = next((fmt for fmt in ("image/png", "image/jpeg") if fmt in formats), None)
        if not image_format:
            raise PreviewError("format")
        if "EPSG:4326" not in crs:
            raise PreviewError("crs")
        info_formats = root.xpath("//*[local-name()='Request']/*[local-name()='GetFeatureInfo']/*[local-name()='Format']/text()")
        info_format = negotiate_info_format(info_formats)
        queryable = bool(element.is_queryable_inherited and info_format)
        return element, image_format, queryable, info_format
    element = service.featuretypes.filter(identifier=selection).first()
    nodes = root.xpath("//*[local-name()='FeatureType']/*[local-name()='Name' and text()=$name]/..", name=selection)
    if not element or not nodes:
        raise PreviewError("stale")
    node = nodes[0]
    formats = node.xpath(".//*[local-name()='OutputFormats']/*/text()") or root.xpath(
        "//*[local-name()='Operation' and @name='GetFeature']/*[local-name()='Parameter' and @name='outputFormat']//*[local-name()='Value']/text()")
    output_format = next((fmt.strip() for fmt in formats if fmt.strip().lower() in
                          {"application/json", "application/geo+json", "json", "geojson"}), None)
    if not output_format:
        raise PreviewError("format")
    crs = node.xpath("./*[local-name()='DefaultCRS' or local-name()='OtherCRS' or local-name()='DefaultSRS' or local-name()='OtherSRS' or local-name()='SRS']/text()")
    if not any(item.strip().upper().endswith((":4326", "::4326", "/4326")) for item in crs):
        raise PreviewError("crs")
    return element, output_format, False, None


class PreviewProxyMixin:
    def log_response(self, response):
        # Live preview is transient even when general proxy response logging is enabled.
        pass

    @cached_property
    def remote_service(self):
        return self.preview_client

    def get_remote_response(self, request=None):
        response = self.remote_service.send_request(request or operation_request(self.service, self.ogc_request.ogc_query_params))
        if self.ogc_request.is_get_map_request:
            # Check dimensions before the spatial mask decodes the raster.
            validate_image(response.content)
        return response


class WmsPreviewProxy(PreviewProxyMixin, WebMapServiceProxy):
    def secure_request(self):
        if any(permission.allowed_area is None for permission in self.service.relevant_allowed_operations):
            return self.return_http_response(self.get_remote_response())
        return super().secure_request()


class WfsPreviewProxy(PreviewProxyMixin, WebFeatureServiceProxy):
    @cached_property
    def service(self):
        # The legacy WFS annotation unions areas across users. Use only the
        # proxy's caller-filtered relevant_allowed_operations for previews.
        return OgcServiceProxyView.service.func(self)

    def secure_request(self):
        if not self.ogc_request.service_version.startswith("2."):
            raise PreviewError("spatialVersion")
        permissions = self.service.relevant_allowed_operations
        if any(permission.allowed_area is None for permission in permissions):
            return self.return_http_response(self.get_remote_response())
        areas = [permission.allowed_area.transform(4326, clone=True) for permission in permissions]
        allowed = GeometryCollection(*areas, srid=4326).unary_union
        if allowed.empty:
            raise PermissionDenied
        self.preview_allowed = allowed
        builder = WFSBuilder(self.ogc_request.service_version)
        geom_property = self.preview_element.properties.filter(
            data_type__in=GEOMETRY_DATA_TYPES).values_list("name", flat=True).first()
        if not geom_property:
            raise PreviewError("spatialVersion")
        viewport = Polygon.from_bbox(self.preview_bbox)
        viewport.srid = 4326
        viewport_filter = builder.build_spatial_filter(
            geometry=adjust_axis_order(viewport).ogr, value_reference=geom_property)
        security_filter = builder.build_spatial_filter(
            geometry=adjust_axis_order(allowed).ogr, value_reference=geom_property, operator="Within")
        builder.and_filter(viewport_filter, security_filter)
        xml = builder.build_get_feature([self.preview_element.identifier], filter_xml=viewport_filter,
                                        srs_name="EPSG:4326", count=FEATURE_LIMIT)
        xml.set("outputFormat", self.ogc_request.ogc_query_params["OUTPUTFORMAT"])
        # Bind QName prefixes to their capabilities namespace, not arbitrary input.
        prefix = self.preview_element.identifier.split(":")[0]
        if ":" in self.preview_element.identifier:
            uri = self.preview_client._capabilities_etree.xpath(
                "//*[local-name()='FeatureType']/*[local-name()='Name' and text()=$name]", name=self.preview_element.identifier)[0].nsmap.get(prefix)
            if not uri:
                raise PreviewError("malformed")
            namespaced = etree.Element(xml.tag, xml.attrib, nsmap={**xml.nsmap, prefix: uri})
            namespaced.extend(xml)
            xml = namespaced
        request = operation_request(self.service, {"REQUEST": "GetFeature", "SERVICE": "WFS",
                                                   "VERSION": self.ogc_request.service_version}, "POST", etree.tostring(xml))
        return self.return_http_response(self.remote_service.send_request(request))


def data_preview(service, caller, query, client=None, request_params=None):
    client = client or stored_client(service)
    selection = query.get("selection", "")
    element, output_format, queryable, info_format = selected_configuration(service, selection, client)
    if not element.is_active:
        raise PreviewError("disabled", 423)
    geometry = element.bbox_lat_lon_inherited if service.service_type == "WMS" else element.bbox_lat_lon
    configuration = {"queryable": queryable, "extent": list(geometry.extent)
                     if geometry and not geometry.empty else None}
    protocol = service.service_type
    version = client.service_version
    # Identify is fetched and rendered by the browser through the security proxy, so only
    # the negotiation and the prefilled url happen here. WFS has no GetFeatureInfo.
    identify = ({"url": identify_request(service, selection, version, info_format),
                 "infoFormat": info_format} if protocol == "WMS" and queryable else None)
    if not query.get("bbox"):
        return {"configuration": configuration, "identify": identify, "discovery": "stored"}
    bbox = checked_bbox(query["bbox"])
    ordered = [bbox[1], bbox[0], bbox[3], bbox[2]] if (protocol == "WMS" and version == "1.3.0") or (protocol == "WFS" and version != "1.0.0") else bbox
    params = {"SERVICE": protocol, "VERSION": version, "BBOX": ",".join(map(str, ordered))}
    if protocol == "WMS":
        params.update(REQUEST="GetMap", LAYERS=selection, STYLES="", FORMAT=output_format,
                      WIDTH=integer(query.get("width"), 800, 2048), HEIGHT=integer(query.get("height"), 400, 2048), TRANSPARENT="TRUE")
        params["CRS" if version == "1.3.0" else "SRS"] = "EPSG:4326"
        proxy = WmsPreviewProxy()
    else:
        params.update(REQUEST="GetFeature", SRSNAME="EPSG:4326", OUTPUTFORMAT=output_format)
        params["TYPENAMES" if version.startswith("2.") else "TYPENAME"] = selection
        params["COUNT" if version.startswith("2.") else "MAXFEATURES"] = FEATURE_LIMIT
        params["BBOX"] += ",EPSG:4326" if version != "1.0.0" else ""
        proxy = WfsPreviewProxy()
    if request_params is not None:
        params = request_params
    raw = RequestFactory().get("/", data=params)
    raw.user = caller.user
    proxy.request = raw
    proxy.kwargs = {"pk": service.pk}
    proxy.ogc_request = OGCRequest.from_django_request(raw)
    proxy.ogc_request._ogc_query_params = params
    proxy.ogc_request._bbox = Polygon.from_bbox(bbox)
    proxy.ogc_request._bbox.srid = 4326
    proxy.preview_client = client
    proxy.preview_element = element
    proxy.preview_bbox = bbox
    response = proxy.get_and_post(raw)
    content = b"".join(response.streaming_content) if response.streaming else response.content
    if response.status_code in (401, 403):
        raise PreviewError("denied", 403)
    if response.status_code >= 400:
        raise PreviewError("unavailable", 502)
    if content.lstrip().startswith(b"<"):
        parse_xml(content)
        raise PreviewError("format")
    result = {"configuration": configuration, "identify": identify, "fetchedAt": now().isoformat()}
    if protocol == "WMS":
        validate_image(content)
        result["image"] = f"data:{output_format};base64,{base64.b64encode(content).decode()}"
    else:
        try:
            features = json.loads(content)
        except (ValueError, UnicodeDecodeError, RecursionError):
            raise PreviewError("malformed")
        validate_features(features, getattr(proxy, "preview_allowed", None))
        result.update(features=features, limit=FEATURE_LIMIT, limited=True)
    return result


def feature_preview_image(service, caller, query):
    """Render an automatically selected WFS sample through the existing proxy."""
    if not service.is_active:
        raise PreviewError("disabled", 423)
    width = integer(query.get("width"), 512, 2048)
    height = integer(query.get("height"), 256, 2048)
    try:
        stored = stored_client(service)
        client = WebFeatureServiceClient(capabilities=stored._capabilities, session=stored.session)
        candidates = service.featuretypes.filter(is_active=True)
        rules = service.__class__.security.get_allowed_operation_qs().for_service(service.pk)
        if rules.exists():
            raw = RequestFactory().get("/", data={
                "SERVICE": "WFS", "VERSION": client.service_version, "REQUEST": "GetFeature"})
            raw.user = caller.user
            allowed = rules.filter_by_request(
                request=OGCRequest.from_django_request(raw), filter_entities=False)
            candidates = candidates.filter(identifier__in=allowed.values_list(
                "secured_feature_types__identifier", flat=True))
            if not candidates.exists():
                raise PermissionDenied
        try:
            request = client.get_preview_request(
                max_features=FEATURE_LIMIT,
                type_names=candidates.values_list("identifier", flat=True))
        except ValueError as error:
            raise PreviewError("unavailable") from error
        generated = dict(parse_qsl(urlsplit(request.url).query))
        # Only the generated canonical OGC parameters may select the proxy
        # operation. Provider-specific parameters remain on the registered URL.
        params = {name: generated[name] for name in (
            "SERVICE", "VERSION", "REQUEST", client.type_name_qp,
            client.max_features_qp, "SRSNAME", "OUTPUTFORMAT", "BBOX")}
        south, west, north, east = params["BBOX"].split(",")[:4]
        result = data_preview(service, caller, {
            "selection": params[client.type_name_qp],
            "bbox": ",".join((west, south, east, north)),
        }, client=client, request_params=params)
        try:
            return render_feature_collection(result["features"], width=width, height=height)
        except ValueError as error:
            raise PreviewError("unavailable") from error
    except RequestException as error:
        raise PreviewError("unavailable", 502) from error
    except Http423 as error:
        raise PreviewError("disabled", 423) from error
    except (etree.XMLSyntaxError, ValueError, KeyError, TypeError) as error:
        raise PreviewError("malformed") from error
    except service.operation_urls.model.DoesNotExist as error:
        raise PreviewError("operation") from error


def validate_features(collection, allowed=None):
    if (not isinstance(collection, dict) or collection.get("type") != "FeatureCollection"
            or not isinstance(collection.get("features"), list) or len(collection["features"]) > FEATURE_LIMIT):
        raise PreviewError("malformed")
    crs = collection.get("crs")
    if crs and (not isinstance(crs, dict) or not isinstance(crs.get("properties"), dict)):
        raise PreviewError("malformed")
    if crs and not str(crs.get("properties", {}).get("name", "")).upper().endswith((":4326", "::4326", "/4326", ":CRS84")):
        raise PreviewError("crs")
    # GeoJSON positions are longitude/latitude regardless of request axis order.
    from django.contrib.gis.geos import GEOSGeometry
    for feature in collection["features"]:
        if not isinstance(feature, dict) or feature.get("type") != "Feature" or not isinstance(feature.get("properties", {}), (dict, type(None))):
            raise PreviewError("malformed")
        geometry = feature.get("geometry")
        if geometry is None:
            continue
        try:
            geom = GEOSGeometry(json.dumps(geometry))
            if geom.empty or not geom.valid:
                raise ValueError
            xmin, ymin, xmax, ymax = geom.extent
            if not all(math.isfinite(value) for value in geom.extent) or not (-180 <= xmin <= xmax <= 180 and -90 <= ymin <= ymax <= 90):
                raise ValueError
        except Exception:
            raise PreviewError("malformed")
        if allowed is not None and not allowed.covers(geom):
            raise PreviewError("denied", 403)


def registered_previews(service, identifier, scope, user):
    field = "dataset_metadata_record" if scope == "dataset" else "service_metadata_record"
    harvested = HarvestedMetadataRelation.objects.filter(harvesting_job__service=service,
                                                         **{f"{field}__file_identifier": identifier})
    ids = harvested.values_list(f"{field}_id", flat=True)
    relation_field = "dataset_metadata" if scope == "dataset" else "service_metadata"
    relations = MetadataRelation.objects.filter(**{f"{relation_field}_id__in": ids})
    checker = ObjectPermissionChecker(user)
    links = []
    for model, relation, protocol in ((Layer, "layer", "WMS"), (FeatureType, "feature_type", "WFS")):
        elements = model.objects.filter(pk__in=relations.values_list(f"{relation}_id", flat=True)).select_related("service")
        for element in elements:
            if (element.is_active and element.service.is_active
                    and checker.has_perm(f"view_{model.__name__.lower()}", element)
                    and checker.has_perm(f"view_{element.service.__class__.__name__.lower()}", element.service)):
                links.append({"protocol": protocol, "serviceId": str(element.service_id),
                              "selection": element.identifier, "title": element.title})
    return links


def catalogue_preview(service, caller, query):
    client = stored_client(service)
    from registry.ows_lib.csw.csw import CatalogueServiceClient
    client = CatalogueServiceClient(capabilities=client._capabilities, session=client.session)
    start = integer(query.get("start"), 1, 1_000_000)
    request = client.get_records_request(result_type="results", max_records=PAGE_SIZE, start_position=start)
    # The registry operation URL, not a caller-supplied distribution URL.
    request.url = update_queryparams(service.operation_urls.get(
        operation=OGCOperationEnum.GET_RECORDS, method=HttpMethodEnum.GET).url,
        dict(parse_qsl(urlsplit(request.url).query)))
    root = parse_xml(client.send_request(request).content)
    searches = root.xpath("/*[local-name()='GetRecordsResponse']/*[local-name()='SearchResults']")
    if len(searches) != 1:
        raise PreviewError("schema")
    search = searches[0]
    if len(search) > PAGE_SIZE:
        raise PreviewError("limit", 502)
    records = []
    for node in search:
        if node.tag != f"{{{GMD}}}MD_Metadata":
            raise PreviewError("schema")
        try:
            mapper = MDMetadataXmlMapper.from_xml(etree.tostring(node))[0]
            scope = MDMetadataXmlMapper._detect_hierarchy_level(node)
            spec = mapper.mapping[scope]
            fields = spec["fields"]
            values = {name: mapper.parse_field(node, fields[name], mapper.mapping["_namespaces"])
                      for name in ("file_identifier", "title", "abstract", "bounding_geometry")}
        except (ValueError, KeyError, IndexError):
            raise PreviewError("schema")
        geometry = values["bounding_geometry"]
        extent = list(geometry.extent) if geometry and not geometry.empty else None
        if extent:
            try:
                checked_bbox(",".join(map(str, extent)))
            except PreviewError:
                extent = None
        identifier = values["file_identifier"]
        records.append({"identifier": identifier, "title": values["title"], "abstract": values["abstract"],
                        "extent": extent, "previews": registered_previews(service, identifier, scope, caller.user) if identifier else []})
    try:
        next_record = int(search.get("nextRecord", "0"))
        matched = int(search.get("numberOfRecordsMatched", "0"))
        returned = int(search.get("numberOfRecordsReturned", str(len(records))))
        if returned != len(records) or next_record < 0 or matched < returned or (next_record and next_record <= start):
            raise ValueError
    except ValueError:
        raise PreviewError("malformed")
    return {"records": records, "start": start, "next": next_record, "matched": matched,
            "pageSize": PAGE_SIZE, "fetchedAt": now().isoformat()}


def preview(service, caller, query):
    if not service.is_active:
        raise PreviewError("disabled", 423)
    try:
        return catalogue_preview(service, caller, query) if service.service_type == "CSW" else data_preview(service, caller, query)
    except RequestException:
        raise PreviewError("unavailable", 502)
    except Http423:
        raise PreviewError("disabled", 423)
    except (etree.XMLSyntaxError, ValueError, KeyError, TypeError):
        raise PreviewError("malformed")
    except service.operation_urls.model.DoesNotExist:
        raise PreviewError("operation")
