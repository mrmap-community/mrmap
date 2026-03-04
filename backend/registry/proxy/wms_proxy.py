import copy
import io
import logging
import platform
from pathlib import Path
from queue import Queue
from threading import Thread

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry, Polygon
from django.db import connection
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from epsg_cache.utils import adjust_axis_order
from extras.utils import execute_threads
from lxml import etree
from PIL import Image, ImageDraw, ImageFont
from registry.models.service import WebMapService
from registry.ows_lib.response.exceptions import (ForbiddenException,
                                                  LayerNotDefined)
from registry.ows_lib.wms.wms import WebMapServiceClient as WebMapServiceClient
from registry.ows_lib.xml.consts import NAMESPACE_LOOKUP
from registry.proxy.mixins import OgcServiceProxyView


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

    @property
    def service(self) -> WebMapService:
        return super().service

    @property
    def remote_service(self) -> WebMapServiceClient:
        return super().remote_service

    def get_and_post(self, request, *args, **kwargs):
        """Http get/post method with security case decisioning.

        **Principle constraints**:
            * service is found by the given primary key. If not return ``404 - Service not found.``
            * service is active. If not return ``423 - Service is disabled.``
            * request query parameter is provided. If not return ``400 - Request param is missing``

        **Service is not secured condition**:
            * service.is_secured == False ``OR``
            * service.is_spatial_secured == False and service.is_user_principle_entitled == True ``OR``
            * request query parameter not in ['GetMap', 'GetFeatureType', 'GetFeature']

            If one condition matches, return the response from the remote service.

        **Service is secured condition**:
            * service.is_spatial_secured ==True and service.is_user_principle_entitled == True

            If the condition matches, return the result from
            :meth:`~GenericOwsServiceOperationFacade.get_secured_response`

        **Default behavior**:
            return ``403 (Forbidden) - User has no permissions to request this service.``

        .. note::
            all error messages will be send as an owsExceptionReport. See
            :meth:`~GenericOwsServiceOperationFacade.return_http_response` for details.

        :return: the computed response based on some principle decisions.
        :rtype: dict or :class:`requests.models.Request`
        """

        if self.service.is_unknown_layer:
            return LayerNotDefined(service_type=self.ogc_request.service_type.lower(), service_version=self.ogc_request.service_version)
        else:
            return super().get_and_post(request, *args, **kwargs)

    def _create_secured_service_mask(self):
        """
        Create a security mask for WMS GetMap using PIL.
        White (255) = masked/restricted
        Black (0) = allowed
        Assumes self.service.allowed_area_union is always a Polygon.
        Uses ogc_request.bbox as the clipping polygon (correct axis order).
        """

        width = int(self.ogc_request.ogc_query_params["WIDTH"])
        height = int(self.ogc_request.ogc_query_params["HEIGHT"])

        # Get the requested bbox polygon (already a GEOSGeometry)
        request_bbox: GEOSGeometry = self.ogc_request.bbox

        if request_bbox.empty:
            # fallback to fully masked if bbox is missing
            return Image.new("RGB", (width, height), (255, 255, 255))

        # Get bounds for world->pixel conversion
        # (xmin, ymin, xmax, ymax)
        minx, miny, maxx, maxy = request_bbox.extent

        # Fully masked by default
        mask = Image.new("L", (width, height), 255)
        draw = ImageDraw.Draw(mask)

        try:
            geom: Polygon = self.service.allowed_area_union
            if geom is None or geom.empty:
                return mask.convert("RGB")

            # Transform geometry to bbox SRID if needed
            if geom.srid != request_bbox.srid:
                geom = geom.transform(request_bbox.srid, clone=True)

            # Clip allowed area to request bbox
            geom = geom.intersection(request_bbox)
            if geom.empty:
                return mask.convert("RGB")

            # Convert world coordinates to pixel coordinates
            def world_to_pixel(x, y):
                px = (x - minx) / (maxx - minx) * width
                py = height - (y - miny) / (maxy - miny) * height  # flip Y
                return (px, py)

            # Draw exterior (allowed area = black)
            exterior_coords = [world_to_pixel(x, y) for x, y in geom[0].coords]
            draw.polygon(exterior_coords, fill=0)

            # Draw interiors (holes) as white
            for interior_ring in geom[1:]:
                hole_coords = [world_to_pixel(x, y)
                               for x, y in interior_ring.coords]
                draw.polygon(hole_coords, fill=255)

        except Exception as e:
            logging.exception("Error creating secured mask: %s", e)
            mask = Image.new("L", (width, height), 255)

        return mask.convert("RGB")

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
            # FIXME: for alpha_composite both images needs to be RGBA!
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

        # if not self.service.is_spatial_secured_and_intersects:
        #     # TODO: return transparent image
        #     get_params = self.remote_service.get_get_params(
        #         query_params=self.request.query_parameters
        #     )
        #     width = int(get_params.get(self.remote_service.WIDTH_QP))
        #     height = int(get_params.get(self.remote_service.HEIGHT_QP))
        #     image = Image.new("RGBA", (width, height), (0, 0, 0))
        #     image.format = 'png'
        #     return self.return_http_response(
        #         {
        #             "status_code": 200,
        #             "content": self._image_to_bytes(image=image),
        #             "content-type": "image/png"
        #         }
        #     )

        # we fetch the map image as it is and mask it, using our secured operations geometry.
        # To improve the performance here, we use a multithreaded approach, where the original map image and the
        # mask are generated at the same time. This speed up the process by ~30%!
        # TODO: secured_service_mask is now generated with PIL. Check if multithreading is still needed.
        thread_list = []
        results = Queue()
        # to differ the results we return a dict for the remote response
        thread_list.append(
            Thread(
                target=lambda r: r.put(
                    {"response": self.get_remote_response()}, connection.close()
                ),
                args=(results,),
            )
        )
        thread_list.append(
            Thread(
                target=lambda r: r.put(
                    self._create_secured_service_mask(), connection.close()
                ),
                args=(results,),
            )
        )
        execute_threads(thread_list)

        # Since we have no idea which result will be on which position in the query
        remote_response = None
        mask = None
        while not results.empty():
            result = results.get()
            if isinstance(result, dict):
                # the img response!
                remote_response = result.get("response")
            else:
                mask = result
        if isinstance(remote_response, dict):
            return self.return_http_response(response=remote_response)
        try:
            secured_image = self._create_masked_image(
                remote_response.content, mask)
        except OSError:
            return RuntimeError()
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

    def handle_get_feature_info_with_multithreading(self):
        """We use multithreading to send two requests at the same time to speed up the response time."""
        request = self.remote_service.bypass_request(request=self.ogc_request)
        thread_list = []
        results = Queue()
        xml_request = copy.deepcopy(request)
        xml_request.params[self.remote_service.INFO_FORMAT_QP] = "text/xml"
        # to differ the results we return a dict for the remote response
        thread_list.append(
            Thread(
                target=lambda r: r.put(
                    {"xml_response": self.get_remote_response(
                        request=xml_request)},
                    connection.close(),
                ),
                args=(results,),
            )
        )
        thread_list.append(
            Thread(
                target=lambda r: r.put(
                    {"requested_response": self.get_remote_response(
                        request=request)},
                    connection.close(),
                ),
                args=(results,),
            )
        )
        execute_threads(thread_list)
        # Since we have no idea which result will be on which position in the query
        xml_response = None
        requested_response = None
        while not results.empty():
            result = results.get()
            if result.get("xml_response", None):
                xml_response = result["xml_response"]
            elif result.get("requested_response", None):
                requested_response = result["requested_response"]
        return xml_response, requested_response

    def handle_secured_get_feature_info(self):
        """Return the GetFeatureInfo response if the bbox is covered by any allowed area or the response features are contained in any allowed area.

        IF not we response with a owsExceptionReport in xml format.

        .. note:: excerpt from ogc specs
            **ogc wms 1.3.0**: The server shall return a response according to the requested INFO_FORMAT if the
            request is valid, or issue a service  exception  otherwise. The nature of the response is at the
            discretion of the service provider, but it shall pertain to the feature(s) nearest to (I,J).
            (see section 7.4.4)

        :return: the GetFeatureInfo response
        :rtype: :class:`request.models.Response` or dict if the request is not allowed.
        """

        if self.service.is_spatial_secured_and_covers:
            return self.return_http_response(response=self.get_remote_response())
        else:
            try:
                request = self.remote_service.bypass_request(
                    request=self.ogc_request)
                if request.params[self.remote_service.INFO_FORMAT_QP] != "text/xml":
                    (
                        xml_response,
                        requested_response,
                    ) = self.handle_get_feature_info_with_multithreading()
                else:
                    xml_response = self.get_remote_response(request=request)
                    requested_response = xml_response

                xml = etree.fromstring(xml_response.content)
                gml = xml.xpath(
                    "//gml:boundedBy/gml:*",
                    namespaces={"gml": NAMESPACE_LOOKUP["gml_3_1_1"]}
                )
                geometry = GEOSGeometry.from_gml(etree.tostring(gml[0]))
                # FIXME: depends on xml wms version not on the registered service version
                axis_order_correction = (
                    True if self.service.major_service_version >= 2 else False
                )
                if axis_order_correction:
                    geometry = adjust_axis_order(geometry)

                if self.service.allowed_area_union.contains(geometry.convex_hull):
                    return self.return_http_response(response=requested_response)
            except Exception:
                pass
        return ForbiddenException(service_type=self.ogc_request.service_type.lower(), service_version=self.ogc_request.service_version)

    def secure_request(self):
        """Handler to decide which subroutine for the given request param shall run.
        :return: the correct handler function for the given request param.
        :rtype: function
        """
        if self.ogc_request.is_get_map_request:
            return self.handle_secured_get_map()
        elif self.ogc_request.is_get_feature_info_request:
            return self.handle_secured_get_feature_info()
