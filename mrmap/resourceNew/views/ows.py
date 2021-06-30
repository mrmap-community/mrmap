import traceback
from io import BytesIO
from django.http import StreamingHttpResponse, JsonResponse
from django.shortcuts import render
from django.template import Template
from django.template.loader import render_to_string
from django.views.generic.base import View
from eulxml import xmlmap

from MrMap.messages import SERVICE_NOT_FOUND, SECURITY_PROXY_ERROR_MISSING_REQUEST_TYPE, SERVICE_DISABLED
from MrMap.settings import PROXIES
from resourceNew.enums.service import AuthTypeEnum, OGCServiceEnum
from resourceNew.models import Service
from resourceNew.models.security import ProxyLog
from resourceNew.ows_client.request_builder import OgcService, WebService
from django.db.models import Q, QuerySet
from requests.auth import HTTPDigestAuth
from requests import Session, Response, Request
from requests.exceptions import ConnectTimeout as ConnectTimeoutException, ConnectionError as ConnectionErrorException
import io
from queue import Queue
from threading import Thread
from PIL import Image, ImageFont, ImageDraw
from django.db import connection
from django.db.models import Q
from django.http import HttpResponse
from MrMap.utils import execute_threads
from resourceNew.parsers.ogc.feature_collection import FeatureCollection
from service.helper.enums import OGCOperationEnum, OGCServiceEnum
from service.settings import MAPSERVER_SECURITY_MASK_TABLE, MAPSERVER_SECURITY_MASK_KEY_COLUMN, \
    MAPSERVER_SECURITY_MASK_GEOMETRY_COLUMN, FONT_IMG_RATIO, ERROR_MASK_VAL, ERROR_MASK_TXT, service_logger
from django.conf import settings


class GenericOwsServiceOperationFacade(View):
    service = None
    remote_service = None
    content_type = None
    query_parameters = None
    access_denied_img = None  # if sub elements are not accessible for the user, this PIL.Image object represents an
    # overlay with information about the resources, which can not be accessed

    def setup(self, request, *args, **kwargs):
        super().setup(request=request, *args, **kwargs)
        self.query_parameters = {k.lower(): v for k, v in self.request.GET.items()}
        try:
            bbox = WebService.construct_polygon_from_bbox_query_param(get_dict=self.query_parameters)
            self.service = Service.security.for_security_facade(query_parameters=self.query_parameters,
                                                                user=self.request.user,
                                                                bbox=bbox) \
                .get(pk=self.kwargs.get("pk"))
            self.remote_service = OgcService(base_url=self.service.base_operation_url or self.service.unknown_operation_url,
                                             service_type=self.service.service_type_name,
                                             version=self.service.service_version)
        except Service.DoesNotExist:
            self.service = None

    def get(self, request, *args, **kwargs):
        if not self.service:
            return self.return_http_response({"status_code": 404, "content": SERVICE_NOT_FOUND})
        if not self.query_parameters.get("request", None):
            return self.return_http_response({"status_code": 400, "content": SECURITY_PROXY_ERROR_MISSING_REQUEST_TYPE})
        elif not self.service.is_active:
            return self.return_http_response({"status_code": 423, "content": SERVICE_DISABLED})
        elif self.query_parameters.get("request").lower() == OGCOperationEnum.GET_CAPABILITIES.value.lower():
            return self.get_capabilities()
        elif not self.service.is_secured or \
                (not self.service.is_spatial_secured and self.service.user_is_principle_entitled) or\
                not self.query_parameters.get("request").lower() in [OGCOperationEnum.GET_MAP.value.lower(),
                                                                     OGCOperationEnum.GET_FEATURE_INFO.value.lower()]:
            return self.return_http_response(response=self.get_remote_response())
        elif self.service.is_spatial_secured and self.service.user_is_principle_entitled:
            return self.get_secured_response()
        else:
            return self.return_http_response({"status_code": 403,
                                              "content": "User has no permissions to request this service."})

    def get_capabilities(self):
        # todo: handle different service versions
        capabilities = self.service.document.xml
        if self.service.camouflage:
            capabilities = self.service.document.camouflaged(request=self.request)
        return HttpResponse(status=200,
                            content=capabilities,
                            content_type="application/xml")

    def _create_secured_service_mask(self):
        """ Creates call to local mapserver and returns the response

        Gets a mask image, which can be used to remove restricted areas from another image

        Returns:
             secured_image (Image)
        """
        masks = []
        get_params = self.remote_service.get_get_params(query_params=self.query_parameters)
        width = int(get_params.get(self.remote_service.WIDTH_QP))
        height = int(get_params.get(self.remote_service.HEIGHT_QP))
        try:
            # todo: maybe it is possible to do this without a for loop in a single request...
            for pk, allowed_area in self.service.allowed_areas:
                if allowed_area is None or allowed_area.empty:
                    return None
                query_parameters = {
                    self.remote_service.VERSION_QP: get_params.get(self.remote_service.VERSION_QP),
                    self.remote_service.REQUEST_QP: "GetMap",
                    self.remote_service.SERVICE_QP: "WMS",
                    self.remote_service.FORMAT_QP: "image/png",
                    self.remote_service.LAYERS_QP: "mask",
                    self.remote_service.CRS_QP: get_params.get(self.remote_service.CRS_QP),
                    self.remote_service.BBOX_QP: get_params.get(self.remote_service.BBOX_QP),
                    self.remote_service.WIDTH_QP: width,
                    self.remote_service.HEIGHT_QP: height,
                    self.remote_service.TRANSPARENT_QP: "TRUE",
                    "map": settings.MAPSERVER_SECURITY_MASK_FILE_PATH,
                    "keys": f"'{pk}'",
                    "table": MAPSERVER_SECURITY_MASK_TABLE,
                    "key_column": MAPSERVER_SECURITY_MASK_KEY_COLUMN,
                    "geom_column": MAPSERVER_SECURITY_MASK_GEOMETRY_COLUMN,
                }
                request = Request(method="GET",
                                  url=settings.MAPSERVER_LOCAL_PATH,
                                  params=query_parameters)
                session = Session()
                response = session.send(request.prepare())

                mask = Image.open(io.BytesIO(response.content))
                masks.append(mask)

            # Create empty final mask object
            mask = Image.new("RGBA", (width, height), (255, 0, 0, 0))

            # Combine all single masks into one!
            for m in masks:
                mask = Image.alpha_composite(m, mask)

            # Put combined mask on white background
            background = Image.new("RGB", (width, height), (255, 255, 255))
            background.paste(mask, mask=mask)
        except Exception as e:
            service_logger.exception(e)
            # If anything occurs during the mask creation, we have to make sure the response won't contain any
            # information at all.
            # So create an error mask
            background = Image.new("RGB", (width, height), (ERROR_MASK_VAL, ERROR_MASK_VAL, ERROR_MASK_VAL))

        return background

    def _create_image_with_text(self, w: int, h: int, txt: str):
        """ Renders text on an empty image

        Args:
            w (int): The image width
            h (int): The image height
            txt (str): text to be rendered
        Returns:
             text_img (Image): The image containing text
        """
        get_params = self.remote_service.get_get_params(query_params=self.query_parameters)
        width = int(get_params.get(self.remote_service.WIDTH_QP))
        text_img = Image.new("RGBA", (width, int(h)), (255, 255, 255, 0))
        draw = ImageDraw.Draw(text_img)
        font_size = int(h * FONT_IMG_RATIO)

        font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", font_size)
        draw.text((0, 0), txt, (0, 0, 0), font=font)

        return text_img

    def _create_masked_image(self, img: bytes, mask: bytes):
        """ Creates a masked image from two image byte object

        Args:
            img (byte): The bytes of the image
            mask (byte): The bytes of the mask
        Returns:
             img (Image): The masked image
        """
        try:
            # Transform byte-image to PIL-image object
            img = Image.open(io.BytesIO(img))
        except OSError:
            raise Exception("Could not create image! Content was:\n {}".format(img))
        try:
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
                is_error_mask = mask.getpixel((0, 0))[0] == ERROR_MASK_VAL
                if is_error_mask:
                    # Create full-masking mask and create an access_denied_img
                    mask = Image.new("RGB", img.size, (255, 255, 255))
                    self.access_denied_img = self._create_image_with_text(img.width, img.height, ERROR_MASK_TXT)

        except OSError:
            raise Exception("Could not create image! Content was:\n {}".format(mask))

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

    def image_to_bytes(self, image):
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
        if not self.service.is_spatial_secured_and_intersects:
            return self.return_http_response({"status_code": 403,
                                              "content": "User has no permissions to access the requested area."})
        # We don't check any kind of is-allowed or not here.
        # Instead, we simply fetch the map image as it is and mask it, using our secured operations geometry.
        # To improve the performance here, we use a multithreaded approach, where the original map image and the
        # mask are generated at the same time. This speed up the process by ~30%!
        thread_list = []
        results = Queue()
        # to differ the results we return a dict for the remote response
        thread_list.append(
            Thread(target=lambda r: r.put({"response": self.get_remote_response()}, connection.close()),
                   args=(results,))
        )
        thread_list.append(
            Thread(target=lambda r: r.put(self._create_secured_service_mask(), connection.close()),
                   args=(results,))
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

        secured_image = self._create_masked_image(remote_response.content, mask)
        return self.return_http_response(response={"status_code": 200,
                                                   "content": self.image_to_bytes(secured_image),
                                                   "content_type": remote_response.headers.get("content-type")})

    def handle_secured_get_feature_info(self):
        """ Return the GetFeatureInfo response if the bbox is covered by any allowed area or the response features are
            contained in any allowed area.
            IF not we response with a owsExceptionReport in xml format.

            .. note:: excerpt from ogc specs
                **ogc wms 1.3.0**: The server shall return a response according to the requested INFO_FORMAT if the
                                   request is valid, or issue a service  exception  otherwise. The nature of the
                                   response is at the discretion of the service provider, but it shall pertain to the
                                   feature(s) nearest to (I,J). (see section 7.4.4)

            Returns:
                the GetFeatureInfo response as requested OR an owsExceptionReport in xml if the request is not allowed.
        """
        if self.service.is_spatial_secured_and_covers:
            return self.return_http_response(response=self.get_remote_response())
        else:
            try:
                request = self.remote_service.construct_request_with_get_dict(query_params=self.request.GET)
                info_format_old = request.params.get(self.remote_service.INFO_FORMAT_QP, "unknown")
                request.params[self.remote_service.INFO_FORMAT_QP] = "text/xml"
                remote_response = self.get_remote_response(request=request)
                feature_collection = xmlmap.load_xmlobject_from_string(remote_response.content, xmlclass=FeatureCollection)
                polygon = feature_collection.bounded_by.get_polygon()
                self.get_allowed_areas_by_layers()
                for pk, allowed_area in self.service.allowed_areas:
                    if allowed_area.contains(polygon.convex_hull):
                        # is allowed
                        if info_format_old == "text/xml":
                            return self.return_http_response(response=remote_response)
                        else:
                            # todo: we can get both responses in parallel mode by using threads.
                            return self.return_http_response(response=self.get_remote_response())
            except Exception as e:
                response = Response()
                response.status_code = 403
                response._content = "user has no permissions to access the requested area."
                return self.return_http_response(response=response)

    def get_allowed_areas_by_layers(self):
        layer_identifiers = self.remote_service.get_requested_layers(query_params=self.request.GET)
        # FIXME: mapserver processes case insensitive layer identifiers... This query won't work then..
        is_layer_secured = Q(secured_layers__identifier__in=layer_identifiers)

        self.service.allowed_areas = self.service.allowed_operations \
            .filter(is_layer_secured) \
            .distinct("pk") \
            .values_list("pk", "allowed_area")

    def handle_secured_wms(self):
        if self.query_parameters.get("request").lower() == OGCOperationEnum.GET_MAP.value.lower():
            self.get_allowed_areas_by_layers()
            return self.handle_secured_get_map()
        elif self.query_parameters.get("request").lower() == OGCOperationEnum.GET_FEATURE_INFO.value.lower():
            return self.handle_secured_get_feature_info()

    def get_secured_response(self):
        """ Return a filtered response based on the requested bbox

            This function will only be called, if the service is spatial secured and the user is in principle
            entitled! If so we filter the allowed_operations again by with the bbox param.
        """

        if self.service.service_type_name == OGCServiceEnum.WMS.value:
            return self.handle_secured_wms()

        elif self.service.service_type_name == OGCServiceEnum.WFS.value:
            return self.return_http_response(response={"status_code": 501,
                                                       "content": "Not implemented"})

    def get_remote_response(self, request=None):
        if not request:
            request = self.remote_service.construct_request_with_get_dict(query_params=self.request.GET)
        if hasattr(self.service, "external_authenticaion"):
            username, password = self.service.external_authenticaion.decrypt()
            if self.service.external_authenticaion.auth_type == AuthTypeEnum.BASIC.value:
                request.auth = (username, password)
            elif self.service.external_authenticaion.auth_type == AuthTypeEnum.DIGEST.value:
                request.auth = HTTPDigestAuth(username=username,
                                              password=password)
        s = Session()
        s.proxies = PROXIES
        r = {}
        try:
            r = s.send(request.prepare())
        except ConnectTimeoutException:
            # response with GatewayTimeout; the remote service response not in timeout
            r.update({"status_code": 504,
                      "code": "MaxResponseTimeExceeded",
                      "content": "remote service didn't response in time."})
        except ConnectionErrorException:
            # response with Bad Gateway; we can't connect to the remote service
            r.update({"status_code": 502,
                      "code": "MaxRetriesExceeded",
                      "content": "can't reach remote service."})
        except Exception as e:
            # todo: log exception
            r.update({"status_code": 500,
                      "code": "InternalServerError",
                      "content": f"{type(e).__name__} raised in function get_remote_response()"})
        return r

    def log_response(self, response: Response):
        """ Check if response logging is active. If so, the response will be logged.

        """
        if self.service.log_response:
            return
            ProxyLog.response_logging.create(user=self.request.user,
                                             service=self.service,
                                             # todo:
                                             operation=self.query_parameters.get("request"),
                                             # todo:
                                             uri=self.request.url,
                                             post_body=self.request.POST,
                                             response_content=response.content)
            # todo
            pass

    def return_http_response(self, response):
        """ Check if response is greater than ~5 MB.

            Returns:
                if response >= ~ 5MB: StreamingHttpResponse
                else: HttpResponse

        """
        if isinstance(response, dict):
            content = response.get("content", "unknown")
            status_code = response.get("status_code", 200)
            content_type = response.get("content_type", None)
        else:
            content = response.content
            status_code = response.status_code
            content_type = response.headers.get("content-type")

        if isinstance(response, dict):
            if status_code > 399:
                # todo: response with owsExceptionReport: http://schemas.opengis.net/ows/1.1.0/owsExceptionReport.xsd
                content = render_to_string(template_name="resourceNew/xml/ows/exception.xml",
                                           context=response)
                content_type = "text/xml"
        else:
            self.log_response(response=response)

        if len(content) >= 5000000:
            # data too big - we should stream it!
            return StreamingHttpResponse(status=status_code,
                                         streaming_content=BytesIO(content),
                                         content_type=content_type)
        else:
            return HttpResponse(status=status_code,
                                content=content,
                                content_type=content_type)
