import io
import logging
import platform
from functools import partial
from pathlib import Path

from django.conf import settings
from django.contrib.gis.geos import GeometryCollection, GEOSGeometry, Polygon
from django.core.exceptions import BadRequest, PermissionDenied
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from epsg_cache.utils import adjust_axis_order
from lxml import etree
from lxml.etree import XMLSyntaxError
from PIL import Image, ImageDraw, ImageFont
from registry.enums.service import HttpMethodEnum, OGCOperationEnum
from registry.helper.xml import parse_untrusted
from registry.models.service import WebMapService
from registry.ows_lib.request.utils import update_queryparams
from registry.ows_lib.response.exceptions import LayerNotDefined
from registry.ows_lib.wms.wms import WebMapServiceClient as WebMapServiceClient
from registry.proxy.mixins import Http423, OgcServiceProxyView
from requests import Request

# the answer this proxy reads the features of a GetFeatureInfo out of; any other
# INFO_FORMAT is forwarded unchanged once the request passed the checks
XML_INFO_FORMAT = "text/xml"

# the roots of the reports a remote OGC service answers a refused request with:
# the ServiceExceptionReport of OGC 05-008, 7.4.2 and the ExceptionReport of OWS
# Common 1.2.1, 10.3.3; matched by local name, since the report of a service is
# whatever namespace it happens to spell it in
UPSTREAM_REFUSAL_ROOTS = ("ServiceExceptionReport", "ExceptionReport")


def _world_to_pixel(coord, minx, miny, width, height, dx, dy):
    """
    Convert a GEOS coordinate into image coordinates.

    coord may be:
        (x, y)
        (x, y, z)
    """
    x, y = coord[:2]

    px = (x - minx) / dx * width
    py = height - (
        (y - miny) / dy * height
    )

    return px, py


def _ring_to_pixels(ring, to_pixel):
    return [
        to_pixel(coord)
        for coord in ring.coords
    ]


def _draw_polygon(draw, polygon, to_pixel):
    """
    Draw one polygon.

    Exterior:
        allowed -> black

    Interior rings / holes:
        restricted -> white
    """

    # polygon[0] is the exterior ring
    exterior = _ring_to_pixels(polygon[0], to_pixel)

    if len(exterior) >= 3:
        draw.polygon(
            exterior,
            fill=0,
        )

    # polygon[1:] are interior rings / holes
    for interior_ring in polygon[1:]:
        hole = _ring_to_pixels(interior_ring, to_pixel)

        if len(hole) >= 3:
            draw.polygon(
                hole,
                fill=255,
            )


def _draw_geometry(draw, geometry, to_pixel):
    """
    Recursively draw all polygonal components.

    intersection() may return:
        Polygon
        MultiPolygon
        GeometryCollection

    Points and lines are ignored because they have no area
    in the resulting mask.
    """

    if geometry is None or geometry.empty:
        return

    if geometry.geom_type == "Polygon":
        _draw_polygon(draw, geometry, to_pixel)

    elif geometry.geom_type in (
        "MultiPolygon",
        "GeometryCollection",
    ):
        for child in geometry:
            _draw_geometry(draw, child, to_pixel)


@method_decorator(csrf_exempt, name="dispatch")
class WebMapServiceProxy(OgcServiceProxyView):
    """Security proxy facade to secure registered services spatial by there operations and for sets of users.

    :attr service:  :class:`registry.models.service.Service` the requested service which was found by the pk.
    :attr remote_service: :class:`registry.ows_client.request_builder.WebService` the request builder to get
                          prepared :class:`requests.models.Request` objects with the correct uri and query params.
    :attr access_denied_img: if sub elements are not accessible for the user, this PIL.Image object represents an
                             overlay with information about the resources, which can not be accessed
    :attr bbox: :class:`django.contrib.gis.geos.polygon.Polygon` the parsed bbox from query params.
    """

    service_cls = WebMapService
    access_denied_img = None
    service_type = "WMS"
    service_version = "1.3.0"

    @property
    def remote_service(self) -> WebMapServiceClient:
        return super().remote_service

    def _create_secured_service_mask(self):
        """
        Create a security mask for WMS GetMap using PIL.

        White (255) = masked / restricted
        Black (0) = allowed

        The requested bbox is used as clipping geometry and for
        world-to-pixel transformation.

        Supports Polygon, MultiPolygon and GeometryCollection results
        after clipping. Non-area geometries are ignored.
        """

        width = int(self.ogc_request.ogc_query_params["WIDTH"])
        height = int(self.ogc_request.ogc_query_params["HEIGHT"])

        request_bbox: GEOSGeometry = self.ogc_request.bbox

        # Fail closed: everything is restricted by default.
        mask = Image.new("L", (width, height), 255)

        if request_bbox is None or request_bbox.empty:
            return mask.convert("RGB")

        minx, miny, maxx, maxy = request_bbox.extent

        # Prevent division by zero for degenerate bboxes.
        if maxx == minx or maxy == miny:
            return mask.convert("RGB")

        try:
            geom = self._clipped_mask_geometry(request_bbox)

            if geom is None or geom.empty:
                return mask.convert("RGB")

            draw = ImageDraw.Draw(mask)
            to_pixel = partial(
                _world_to_pixel,
                minx=minx,
                miny=miny,
                width=width,
                height=height,
                dx=maxx - minx,
                dy=maxy - miny,
            )

            _draw_geometry(draw, geom, to_pixel)

        except Exception:
            logging.exception(
                "Error creating secured service mask"
            )

            # Fail closed in case anything goes wrong.
            mask = Image.new(
                "L",
                (width, height),
                255,
            )

        return mask.convert("RGB")

    def _clipped_mask_geometry(self, request_bbox):
        """The allowed geometry, transformed into the CRS of the request
        bbox and clipped to the requested extent."""
        geom = self.geom

        if geom is None or geom.empty:
            return None

        # Transform allowed geometry into the CRS of the request bbox.
        if geom.srid != request_bbox.srid:
            geom = geom.transform(
                request_bbox.srid,
                clone=True,
            )

        # Clip the allowed geometry to the requested extent.
        return geom.intersection(request_bbox)

    def _get_default_ttf(self, font_size: int) -> ImageFont.FreeTypeFont:
        system = platform.system()

        candidates = []

        if system == "Linux":
            candidates = [
                # Alpine
                Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
                # Debian / Ubuntu
                Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            ]
        elif system == "Darwin":  # macOS
            candidates = [
                Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
                Path("/Library/Fonts/Arial.ttf"),
            ]
        elif system == "Windows":
            candidates = [
                Path(r"C:\Windows\Fonts\arial.ttf"),
            ]

        for path in candidates:
            if path.exists():
                return ImageFont.truetype(str(path), font_size)

        # Absolute last-resort fallback
        return ImageFont.load_default(font_size)

    def _create_image_with_text(self, w: int, h: int, txt: str):
        """Renders text on an empty image
        Args:
            w (int): The image width
            h (int): The image height
            txt (str): text to be rendered
        Returns:
             text_img (Image): The image containing text
        """
        width = int(self.ogc_request.ogc_query_params.get("WIDTH"))
        text_img = Image.new("RGBA", (width, int(h)), (255, 255, 255, 0))
        draw = ImageDraw.Draw(text_img)
        font_size = int(h * settings.FONT_IMG_RATIO)
        font = self._get_default_ttf(font_size)
        draw.text((0, 0), txt, (0, 0, 0), font=font)

        return text_img

    def _create_masked_image(self, img: bytes, mask: bytes):
        """Creates a masked image from two image byte object
        Args:
            img (byte): The bytes of the image
            mask (byte): The bytes of the mask
        Returns:
             img (Image): The masked image
        """
        # Transform byte-image to PIL-image object
        img = Image.open(io.BytesIO(img))

        # Create an alpha layer, which is needed for the compositing of image and mask
        alpha_layer = Image.new("RGBA", img.size, (255, 0, 0, 0))

        # Make sure we have any kind of mask
        if mask is None:
            # No bounding geometry for masking exist, so we just create a mask that does not mask anything
            mask = Image.new("RGB", img.size, (0, 0, 0))
        else:
            # There is a mask ...
            if isinstance(mask, bytes):
                # ... but it is in bytes, so we need to transform it to a PIL-image object as well
                mask = Image.open(io.BytesIO(mask))

            # Check if the mask is fine or indicates an error
            is_error_mask = mask.getpixel(
                (0, 0))[0] == settings.ERROR_MASK_VAL
            if is_error_mask:
                # Create full-masking mask and create an access_denied_img
                mask = Image.new("RGB", img.size, (255, 255, 255))
                self.access_denied_img = self._create_image_with_text(
                    img.width, img.height, settings.ERROR_MASK_TXT
                )

        # Make sure mask is in grayscale and has the exact same size as the requested image
        mask = mask.convert("L").resize(img.size)

        # save image format for restoring a few steps later
        img_format = img.format
        img = Image.composite(alpha_layer, img, mask)
        img.format = img_format

        # Add access_denied_img image
        # (contains info about which layers are restricted or if there was an error during mask creation)
        if self.access_denied_img is not None:
            old_format = img.format
            # FUTURE: for alpha_composite both images needs to be RGBA!
            # img = Image.alpha_composite(img, self.access_denied_img)
            img = Image.composite(img, img, self.access_denied_img)
            img.format = old_format

        return img

    def _image_to_bytes(self, image):
        out_bytes_stream = io.BytesIO()
        try:
            image.save(out_bytes_stream, image.format, quality=80)
            image = out_bytes_stream.getvalue()
        except IOError:
            # happens if a non-alpha channel format is requested, such as jpeg
            # replace alpha channel with white background
            bg = Image.new("RGB", image.size, (255, 255, 255))
            bg.paste(image, mask=image.split()[3])
            bg.save(out_bytes_stream, image.format, quality=80)
            image = out_bytes_stream.getvalue()
        return image

    def handle_secured_get_map(self):
        """Compute the secured get map response if the requested bbox intersects any allowed area.

        **Example 1: bbox covers allowed area**
            .. figure:: ../images/security/example_1_request.png
              :width: 50%
              :class: with-border
              :alt: Request: bbox covers allowed area

              Request: bbox covers allowed area

            .. figure:: ../images/security/example_1_result.png
              :width: 50%
              :alt: Result: bbox covers allowed area

              Result: bbox covers allowed area

        **Example 2: bbox intersects allowed area**
            .. figure:: ../images/security/example_2_request.png
              :width: 50%
              :alt: Request: bbox intersects allowed area

              Request: bbox intersects allowed area

            .. figure:: ../images/security/example_2_result.png
              :width: 50%
              :alt: Result: bbox intersects allowed area

              Result: bbox intersects allowed area

            :return: The cropped map image with status code 200 or an error message with status code 403 (Forbidden) if
                     the bbox doesn't intersects any allowed area.
            :rtype: dict
        """

        remote_response = self.get_remote_response()

        if "xml" in remote_response.headers.get("Content-Type", "") and "ServiceException" in remote_response.text:
            return self.return_http_response(
                response=remote_response
            )

        mask = self._create_secured_service_mask()

        if isinstance(remote_response, dict):
            return self.return_http_response(response=remote_response)
        try:
            secured_image = self._create_masked_image(
                remote_response.content, mask)
        except OSError as e:
            logging.exception(e)
            return self.return_http_response(
                response={
                    "status_code": 500,
                    "code": "ImageProcessingError",
                    "content": "Failed to process image mask.",
                }
            )
        return self.return_http_response(
            response={
                "status_code": 200,
                "reason": remote_response.reason,
                "elapsed": remote_response.elapsed,
                "headers": dict(remote_response.headers),
                "url": remote_response.url,
                "content": self._image_to_bytes(secured_image),
                "content_type": remote_response.headers.get("content-type"),
            }
        )

    def _query_key(self, name: str):
        """The name the request spells a query parameter with, or None.

        The parameters are collected under the canonical spelling but a caller
        may spell them any way, so they are read by their upper case name.
        """
        for key in self.ogc_request.ogc_query_params:
            if key.upper() == name:
                return key
        return None

    def _query_param(self, name: str, default: str = None):
        """The value of a query parameter of the request, read by upper case name."""
        key = self._query_key(name)
        if key is None:
            return default
        return self.ogc_request.ogc_query_params[key]

    def _feature_is_within_allowed_area(self, bounded_by) -> bool:
        """Whether one feature of the answer lies within the allowed area.

        A feature whose area can not be read, and an area which is not
        comparable with the allowed area, keep the answer private: what can not
        be proven to lie within the allowed area is not proven to be allowed,
        and the answer of a secured service is private until the check says
        otherwise.
        """
        try:
            geometry = GEOSGeometry.from_gml(etree.tostring(bounded_by))
            # FUTURE: depends on xml wms version not on the registered service version
            if self.service.major_version() >= 2:
                geometry = adjust_axis_order(geometry)
            return self.geom.contains(geometry.convex_hull)
        except Exception:
            logging.warning(
                "GetFeatureInfo answer of service %s carries a feature whose area "
                "can not be compared with the allowed area; the answer is kept "
                "private", self.service.pk)
            return False

    def _is_within_allowed_area(self, xml) -> bool:
        """Whether every feature of a GetFeatureInfo answer lies within the area.

        One answer carries the features of all queried layers and of all styles
        of them (OGC 05-008, 7.4.4), so the first of them says nothing about the
        rest: any feature outside the allowed area keeps the whole answer
        private, the same all-or-nothing the masked GetMap of a secured service
        applies (#1471). An answer which carries no feature at all is empty, so
        nothing private travels with it and it is allowed.

        The areas are read namespace-agnostically, like the presence of an area
        is proved. A selection bound to one GML namespace would have to spell
        the namespace the answer happens to use: a GML 3.2 answer proved its
        areas in the namespace-agnostic traversal and selected none of them in
        the bound one, and an empty selection compares as true -- #1471 answered
        as allowed what was never compared. The areas of the whole collection
        are compared, a superset of the ones the presence check of every member
        proved, so no area of the answer escapes the check.
        """
        collections = xml.xpath('//*[local-name()="FeatureCollection"]')
        if not collections:
            logging.warning(
                "GetFeatureInfo answer of service %s is no feature collection; "
                "the answer is kept private", self.service.pk)
            return False
        for feature in xml.xpath('//*[local-name()="FeatureCollection"]/*'):
            if not feature.xpath('.//*[local-name()="boundedBy"]/*'):
                logging.warning(
                    "GetFeatureInfo answer of service %s carries a feature "
                    "without an area; the answer is kept private",
                    self.service.pk)
                return False
        # an answer whose members all carry an area has an area to compare, so
        # an empty selection here means an answer without any feature at all
        areas = [area for collection in collections for area
                 in collection.xpath('.//*[local-name()="boundedBy"]/*')]
        return all(self._feature_is_within_allowed_area(area) for area in areas)

    def _answer_upstream_failure(self, remote_response):
        """Answer the way the upstream failed, when it never answered at all.

        The dict of get_remote_response carries its own status and message, and
        a failure of the proxy to reach the service is not a refusal of the
        permissions of the caller (#1153, #1471).
        """
        if isinstance(remote_response, dict):
            return self.return_http_response(response=remote_response)
        return None

    def _answer_upstream_refusal(self, remote_response, root=None):
        """Answer the way the remote service did, when it refused the request.

        A request which the remote service refuses is a faulty request of the
        caller, and its own report says what is faulty about it. Answering that
        refusal with the permissions report of this proxy tells the caller it
        lacks a permission it may well have, and the operator looks for a
        permission which was never the cause.

        The report is recognised by the root of the parsed document, not by a
        word of the serialised body: an answer which carries that word in an
        attribute of a feature is an answer, not a report, and has to reach the
        feature check (#1471).

        :param remote_response: the answer of the remote service
        :param root: the root of that answer, when the caller parsed it already
        """
        if "xml" not in (
                remote_response.headers.get("content-type") or "").lower():
            return None
        if root is None:
            try:
                root = parse_untrusted(remote_response.content)
            except (XMLSyntaxError, ValueError):
                # no document at all; whether its answer may travel is decided
                # by the feature check, not here
                return None
        if root.tag.rpartition("}")[2] not in UPSTREAM_REFUSAL_ROOTS:
            return None
        return self.return_http_response(response=remote_response)

    def handle_secured_get_feature_info(self):
        """Return the GetFeatureInfo response if it stays within the allowed area.

        Whether the caller may request the drawn layers *and* the queried ones is
        decided before this handler runs, by the operations the security manager
        matched against the request (registry/managers/security.py); a request
        which names a layer the caller may not request never reaches it.

        If the bbox of the request is covered by an allowed area, whatever the
        service answers within that extent is allowed; otherwise the features of
        the answer are checked and any one of them outside the allowed area keeps
        the whole answer private, the same all-or-nothing the GetMap of a secured
        service applies (#1471).

        .. note:: excerpt from ogc specs
            **ogc wms 1.3.0**: The server shall return a response according to the requested INFO_FORMAT if the
            request is valid, or issue a service  exception  otherwise. The nature of the response is at the
            discretion of the service provider, but it shall pertain to the feature(s) nearest to (I,J).
            (see section 7.4.4)

        :return: the GetFeatureInfo response
        :rtype: :class:`django.http.response.HttpResponse`
        """
        if any(allowed_operation.allowed_area.covers(self.ogc_request.bbox)
               for allowed_operation in self.service.relevant_allowed_operations):
            return self.return_http_response(response=self.get_remote_response())

        # the features can only be read out of an answer of text/xml, so an
        # answer of any other format is asked twice: once to check it and once
        # as the caller wants it
        requested_format = self._query_param("INFO_FORMAT") or "text/plain"
        if requested_format == XML_INFO_FORMAT:
            xml_response = self.get_remote_response()
            requested_response = xml_response
        else:
            if not self.ogc_request.is_get:
                # the format of a posted request is written inside its document,
                # which this proxy forwards as it is and can not rewrite; an
                # answer it can not read stays private
                raise PermissionDenied
            xml_response = self._answer_as_xml_info_format()
            requested_response = self.get_remote_response()

        refusal = (self._answer_upstream_failure(xml_response)
                   or self._answer_upstream_failure(requested_response))
        if refusal is not None:
            return refusal

        # the checked answer is parsed once and the parsed root answers both
        # questions about it: whether the remote service refused the request and
        # whether its features stay within the allowed area
        try:
            xml = parse_untrusted(xml_response.content)
        except (XMLSyntaxError, ValueError):
            logging.warning(
                "GetFeatureInfo answer of service %s is no well-formed XML; the "
                "answer is kept private", self.service.pk)
            raise PermissionDenied

        refusal = (self._answer_upstream_refusal(xml_response, root=xml)
                   or self._answer_upstream_refusal(requested_response))
        if refusal is not None:
            return refusal

        if self._is_within_allowed_area(xml):
            return self.return_http_response(response=requested_response)
        raise PermissionDenied

    def _answer_as_xml_info_format(self):
        """The answer of the request, asked with the INFO_FORMAT of text/xml.

        The forwarded request is rebuilt from the query parameters of the
        request, so the check asks the same url with the format it needs
        substituted; the request of the caller keeps the format it named.
        """
        params = dict(self.ogc_request.ogc_query_params)
        params["INFO_FORMAT"] = XML_INFO_FORMAT
        url = update_queryparams(
            url=self.service.operation_urls.values("url").get(
                operation=OGCOperationEnum.GET_FEATURE_INFO.value,
                method=HttpMethodEnum.GET.value)["url"],
            params=params)
        return self.get_remote_response(request=Request(
            method=self.ogc_request.method,
            url=url,
            headers={key: value for key, value in (self.ogc_request.headers or {}).items()
                     if key.lower() not in {"authorization", "cookie", "host"}}))

    def get_and_post(self, request, *args, **kwargs):
        if self.ogc_request.is_get_map_request and self.service.is_unknown_layer:
            exc = BadRequest()
            exc.response_cls = LayerNotDefined
            raise exc

        elif not self.ogc_request.is_get_capabilities_request and not self.service.are_all_layers_active:
            raise Http423
        return super().get_and_post(request, *args, **kwargs)

    def secure_request(self):
        """Handler to decide which subroutine for the given request param shall run.
        :return: the correct handler function for the given request param.
        :rtype: function
        """
        srid = self.service.relevant_allowed_operations[
            0].allowed_area.srid if self.service.relevant_allowed_operations and not self.service.relevant_allowed_operations[0].allowed_area.empty else 4326
        self.geom: Polygon = GeometryCollection(
            *[aop.allowed_area for aop in self.service.relevant_allowed_operations],
            srid=srid
        ).unary_union
        if self.ogc_request.is_get_map_request:
            return self.handle_secured_get_map()
        elif self.ogc_request.is_get_feature_info_request:
            return self.handle_secured_get_feature_info()
