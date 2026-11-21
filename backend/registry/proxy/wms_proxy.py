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
from PIL import Image, ImageDraw, ImageFont
from registry.enums.service import HttpMethodEnum, OGCOperationEnum
from registry.models.service import WebMapService
from registry.ows_lib.request.utils import update_queryparams
from registry.ows_lib.response.exceptions import LayerNotDefined
from registry.ows_lib.wms.wms import WebMapServiceClient as WebMapServiceClient
from registry.ows_lib.xml.consts import NAMESPACE_LOOKUP
from registry.proxy.mixins import Http423, OgcServiceProxyView
from requests import Request


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

    # The INFO_FORMAT the spatial check of a GetFeatureInfo answer reads geometries from.
    INFO_FORMAT_XML = "text/xml"

    def _layer_names(self, param: str) -> list[str]:
        """The layer names one comma separated WMS layer parameter of the request names.

        :param param: the parameter name as WMS spells it, e.g. ``QUERY_LAYERS``
        :type param: str
        :return: the non empty names, in the order of the request
        :rtype: list[str]
        """
        value = self.ogc_request.ogc_query_params.get(param, "") or ""
        if not isinstance(value, str):
            value = ",".join(str(entry) for entry in value)
        return [name.strip() for name in value.split(",") if name.strip()]

    def _permitted_layer_names(self) -> list[str]:
        """The active layers the requesting user is entitled to ask answers from.

        The allowed operations attached to the service answer which layers the
        request may name at all, so a name outside this list is unknown to the
        service, deactivated, or not the caller's.

        :return: the distinct active layer identifiers of the allowed operations
        :rtype: list[str]
        """
        return list(dict.fromkeys(
            allowed_operation.layer.identifier
            for allowed_operation in self.service.relevant_allowed_operations
            if allowed_operation.layer and allowed_operation.layer.is_active
        ))

    def _layers_are_allowed(self, layers: list[str], permitted: list[str]) -> bool:
        """Check named layers against the layers the user may ask.

        :param layers: the layer names the request names
        :type layers: list[str]
        :param permitted: the layer names of the user's allowed operations
        :type permitted: list[str]
        :return: True if the list names layers and every one of them is entitled
        :rtype: bool
        """
        return bool(layers) and set(layers) <= set(permitted)

    def _refused_layers(self, param: str) -> dict:
        """Refuse a GetFeatureInfo which names layers the caller may not ask.

        The whole request is refused before anything is asked upstream, so a request
        which mixes an entitled layer with an unentitled one cannot answer the
        entitled part. The shape is the one :meth:`get_remote_response` answers for a
        failed exchange, which :meth:`return_http_response` renders as a service
        exception report.

        :param param: the parameter which carried the disallowed names
        :type param: str
        :return: the response to answer the request with
        :rtype: dict
        """
        logger.info(
            "the GetFeatureInfo of service %s was refused: %s names a layer which is "
            "unknown to the service, deactivated or not allowed for the requesting user",
            self.service.pk, param
        )
        return {
            "status_code": 400,
            "code": "LayerNotDefined",
            "content": f"the layers of the request parameter {param} are unknown to the "
                       f"service, deactivated or not allowed for the requesting user",
        }

    def _feature_info_request(self, layers: list[str], info_format: str) -> Request:
        """Build the upstream GetFeatureInfo with the validated layer names.

        The request is rebuilt from the parameters the proxy parsed rather than
        deep-copied from the incoming one: a parameter upstream is asked with is then
        always a parameter whose layers have been checked. LAYERS carries the same
        layers as QUERY_LAYERS, which is what the point of the request is drawn from.
        The identity of the caller is never forwarded, as in :meth:`get_remote_response`.

        :param layers: the validated layers to ask answers from
        :type layers: list[str]
        :param info_format: the INFO_FORMAT the upstream answer shall be served in
        :type info_format: str
        :return: the request to send to the remote service
        :rtype: :class:`requests.models.Request`
        """
        operation_url = self.service.operation_urls.values("url").get(
            operation=OGCOperationEnum.GET_FEATURE_INFO.value,
            method=HttpMethodEnum.GET.value
        )
        params = dict(self.ogc_request.ogc_query_params)
        params.update({
            "SERVICE": "WMS",
            "REQUEST": self.remote_service.get_feature_info_operation_name,
            "VERSION": self.remote_service.service_version,
            "LAYERS": ",".join(layers),
            "QUERY_LAYERS": ",".join(layers),
            "INFO_FORMAT": info_format,
        })
        headers = {
            key: value for key, value in (self.ogc_request.headers or {}).items()
            if key.lower() not in {"authorization", "cookie", "host"}
        }
        return Request(
            method="GET",
            url=update_queryparams(url=operation_url["url"], params=params),
            headers=headers,
        )

    def _response_features_are_within_allowed_area(self, request: Request) -> bool:
        """Check every feature of a text/xml GetFeatureInfo answer against the allowed area.

        The previous version used the boundedBy of the first feature only and answered
        the complete response as soon as that one passed, so a second feature outside
        the allowed area leaked with it. Here every answered feature must be within the
        allowed area, and an answer which cannot be checked does not authorize itself:
        an unparseable document, a remote exception report, a feature without a geometry
        or a failed area comparison all keep the features of the response private.

        :param request: the request asking the text/xml answer of the validated layers
        :type request: :class:`requests.models.Request`
        :return: True if the answer has features and all of them are within the allowed area
        :rtype: bool
        """
        try:
            xml_response = self.get_remote_response(request=request)
            xml = etree.fromstring(xml_response.content)
            # a ServiceExceptionReport of the remote service carries no feature
            if xml.tag.endswith("ServiceExceptionReport"):
                return False
            # FUTURE: depends on xml wms version not on the registered service version
            axis_order_correction = self.service.major_service_version >= 2
            features = xml.xpath(
                "//gml:featureMember/* | //gml:featureMembers/*",
                namespaces={"gml": NAMESPACE_LOOKUP["gml_3_1_1"]}
            )
            if not features:
                # no answered feature, no feature to leak. The answer of the requested
                # format is returned for a point where nothing answers.
                return True
            for feature in features:
                geometries = feature.xpath(
                    ".//gml:boundedBy/gml:* | .//gml:geometry/gml:* | .//gml:geom/gml:*",
                    namespaces={"gml": NAMESPACE_LOOKUP["gml_3_1_1"]}
                )
                if not geometries:
                    # a feature without a geometry can not be localized and stays private
                    return False
                for geometry_element in geometries:
                    geometry = GEOSGeometry.from_gml(etree.tostring(geometry_element))
                    if axis_order_correction:
                        geometry = adjust_axis_order(geometry)
                    if not self.geom.contains(geometry.convex_hull):
                        return False
            return True
        except Exception:
            logger.warning(
                "the GetFeatureInfo response of service %s could not be checked against the "
                "allowed area and was refused", self.service.pk, exc_info=True
            )
            return False

    def handle_secured_get_feature_info(self):
        """Return the GetFeatureInfo response if the bbox is covered by any allowed area or the response features are contained in any allowed area.

        IF not we response with a owsExceptionReport in xml format.

        .. note:: excerpt from ogc specs
            **ogc wms 1.3.0**: The server shall return a response according to the requested INFO_FORMAT if the
            request is valid, or issue a service  exception  otherwise. The nature of the response is at the
            discretion of the service provider, but it shall pertain to the feature(s) nearest to (I,J).
            (see section 7.4.4)

        LAYERS and QUERY_LAYERS are validated against the layers of the requesting user
        before anything is asked upstream: a name which the service does not know, which
        is deactivated or which the user is not entitled to refuses the whole request with
        LayerNotDefined -- the answer the GetMap of an unknown layer already gives. A
        request which omits both asks the layers of the caller, instead of drawing the
        point from every layer of the service and 403ing an entitled user over the empty
        layer list of :attr:`OGCRequest.requested_entities`.

        :return: the GetFeatureInfo response
        :rtype: :class:`request.models.Response` or dict if the request is not allowed.
        """
        permitted = self._permitted_layer_names()
        layers = self._layer_names("QUERY_LAYERS") or self._layer_names("LAYERS")
        if not layers:
            layers = permitted
        elif not self._layers_are_allowed(layers, permitted):
            return self._refused_layers("QUERY_LAYERS")

        is_spatial_secured_and_covers = len(list(filter(
            lambda ao: ao.allowed_area.covers(self.ogc_request.bbox),
            self.service.relevant_allowed_operations
        ))) > 0
        info_format = self.ogc_request.ogc_query_params.get("INFO_FORMAT") or self.INFO_FORMAT_XML

        if is_spatial_secured_and_covers:
            # every feature upstream may answer within this bbox is within the
            # allowed area, so the answer of the requested format can be returned
            return self.return_http_response(
                response=self.get_remote_response(
                    request=self._feature_info_request(layers, info_format)))

        # FUTURE: this uses the permission model of the service and not the
        # allowed operation of the requesting user (#1442)
        if self._response_features_are_within_allowed_area(
                request=self._feature_info_request(layers, self.INFO_FORMAT_XML)):
            # the answer of the requested format must be asked separately, since the
            # check above used a request for the xml answer
            return self.return_http_response(
                response=self.get_remote_response(
                    request=self._feature_info_request(layers, info_format)))
        raise PermissionDenied

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
