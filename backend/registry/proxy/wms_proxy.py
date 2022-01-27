import copy
import io
import re
from io import BytesIO
from queue import Queue
from threading import Thread
from urllib.parse import parse_qsl, urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.gis.geos import GEOSGeometry
from django.core.files.base import ContentFile
from django.db import connection, transaction
from django.db.models.functions import datetime
from django.http import HttpResponse, StreamingHttpResponse
from django.http.response import Http404
from django.template.loader import render_to_string
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic.base import View
from eulxml import xmlmap
from extras.utils import execute_threads
from MrMap.settings import PROXIES
from ows_client.exceptions import (MissingBboxParam, MissingServiceParam,
                                   MissingVersionParam)
from ows_client.request_builder import WebService, WmsService
from PIL import Image, ImageDraw, ImageFont
from registry.enums.service import OGCOperationEnum
from registry.models.security import HttpRequestLog, HttpResponseLog
from registry.models.service import WebMapService
from registry.proxy.ogc_exceptions import (DisabledException,
                                           ForbiddenException, LayerNotDefined,
                                           MissingRequestParameterException,
                                           MissingVersionParameterException)
from registry.settings import SECURE_ABLE_OPERATIONS_LOWER
from registry.xmlmapper.ogc.feature_collection import FeatureCollection
from requests import Request, Session
from requests.exceptions import ConnectionError as ConnectionErrorException
from requests.exceptions import ConnectTimeout as ConnectTimeoutException


@method_decorator(csrf_exempt, name="dispatch")
class WebMapServiceProxy(View):
    """Security proxy facade to secure registered services spatial by there operations and for sets of users.
    :attr service:  :class:`registry.models.service.Service` the requested service which was found by the pk.
    :attr remote_service: :class:`registry.ows_client.request_builder.WebService` the request builder to get
                          prepared :class:`requests.models.Request` objects with the correct uri and query params.
    :attr query_parameters: all query parameters in lower case.
    :attr access_denied_img: if sub elements are not accessible for the user, this PIL.Image object represents an
                             overlay with information about the resources, which can not be accessed
    :attr bbox: :class:`django.contrib.gis.geos.polygon.Polygon` the parsed bbox from query params.
    """

    service = None
    remote_service = None
    query_parameters = None
    access_denied_img = None
    bbox = None
    start_time = None

    def dispatch(self, request, *args, **kwargs):
        self.start_time = datetime.datetime.now()
        self.adjust_query_params()

        exception = self.check_request()
        if exception:
            return exception

        self.get_bbox_from_request()
        self.get_service()
        self.setup_remote_service()
        return self.get_and_post(request=request, *args, **kwargs)

    def check_request(self):
        request_operation = self.request.query_parameters.get("request", None)
        if not request_operation:
            return MissingRequestParameterException()

    def adjust_query_params(self):
        self.request.query_parameters = {
            k.lower(): v for k, v in self.request.GET.items()}

    def get_bbox_from_request(self):
        try:
            self.request.bbox = WmsService.construct_polygon_from_bbox_query_param(
                get_dict=self.request.query_parameters
            )
        except (MissingBboxParam, MissingServiceParam):
            # only to avoid error while handling sql in get_service()
            self.request.bbox = GEOSGeometry("POLYGON EMPTY")

    def get_service(self):
        try:
            self.service = WebMapService.security.get_with_security_info(
                pk=self.kwargs.get("pk"), request=self.request
            )
        except WebMapService.DoesNotExist:
            raise Http404

    def setup_remote_service(self):
        try:
            requested_url_parts = urlparse(self.request.get_full_path())

            service_url_parts = urlparse(
                self.service.base_operation_url
                if self.service.base_operation_url
                else self.service.unknown_operation_url
            )

            service_url_parts._replace(
                query=parse_qsl(qs=requested_url_parts.query))

            self.remote_service = WebService.manufacture_service(
                url=service_url_parts._replace(
                    query=requested_url_parts.query).geturl()
            )
        except (MissingServiceParam, MissingVersionParam):
            # exception handling in self.get()
            pass

    def post(self, request, *args, **kwargs):
        return self.get_and_post(request=request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        return self.get_and_post(request=request, *args, **kwargs)

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
        if (
            self.request.query_parameters.get("request").lower()
            == OGCOperationEnum.GET_CAPABILITIES.value.lower()
        ):
            return self.get_capabilities()
        elif not self.request.query_parameters.get("version", None):
            return MissingVersionParameterException()
        elif not self.service.is_active:
            return DisabledException()
        elif self.service.is_unknown_layer:
            return LayerNotDefined()
        elif (
            not self.request.query_parameters.get("request").lower()
            in SECURE_ABLE_OPERATIONS_LOWER
        ):
            # seperated from elif below, cause security.for_security_facade does not fill the fields like is_secured,
            # is_spatial_secured, is_user_principle_entitled...
            return self.return_http_response(response=self.get_remote_response())
        elif (
            not self.service.is_secured
            or not self.service.is_spatial_secured
            and self.service.is_user_principle_entitled
        ):
            return self.return_http_response(response=self.get_remote_response())
        elif (
            self.service.is_spatial_secured and self.service.is_user_principle_entitled
        ):
            return self.handle_secured_wms()
        else:
            return ForbiddenException()

    def get_capabilities(self):
        """Return the camouflaged capabilities document of the founded service.
        .. note::
           See :meth:`registry.models.document.DocumentModelMixin.xml_secured` for details of xml_secured function.
        :return: the camouflaged capabilities document.
        :rtype: :class:`django.http.response.HttpResponse`
        """
        # todo: handle different service versions
        return HttpResponse(
            status=200, content=self.service.get_xml(self.request), content_type="application/xml"
        )

    def _create_secured_service_mask(self):
        """Creates call to local mapserver and returns the response
        Gets a mask image, which can be used to remove restricted areas from another image
        Returns:
             secured_image (Image)
        """
        get_params = self.remote_service.get_get_params(
            query_params=self.request.query_parameters
        )
        width = int(get_params.get(self.remote_service.WIDTH_QP))
        height = int(get_params.get(self.remote_service.HEIGHT_QP))
        try:
            from django.db import connection

            db_name = connection.settings_dict["NAME"]
            query_parameters = {
                self.remote_service.VERSION_QP: get_params.get(
                    self.remote_service.VERSION_QP
                ),
                self.remote_service.REQUEST_QP: "GetMap",
                self.remote_service.SERVICE_QP: "WMS",
                self.remote_service.FORMAT_QP: "image/png",
                self.remote_service.LAYERS_QP: "mask",
                self.remote_service.CRS_QP: get_params.get(self.remote_service.CRS_QP),
                self.remote_service.BBOX_QP: get_params.get(
                    self.remote_service.BBOX_QP
                ),
                self.remote_service.WIDTH_QP: width,
                self.remote_service.HEIGHT_QP: height,
                self.remote_service.TRANSPARENT_QP: "TRUE",
                # "map": settings.MAPSERVER_SECURITY_MASK_FILE_PATH,
                "table": settings.MAPSERVER_SECURITY_MASK_TABLE,
                "key_column": settings.MAPSERVER_SECURITY_MASK_KEY_COLUMN,
                "geom_column": settings.MAPSERVER_SECURITY_MASK_GEOMETRY_COLUMN,
                "map": f"/etc/mapserver/security_mask{'_test_db' if 'test' in db_name else ''}.map",
                "keys": ",".join(str(pk) for pk in self.service.allowed_area_pks)
            }

            request = Request(
                method="GET", url=settings.MAPSERVER_URL, params=query_parameters
            )
            session = Session()
            response = session.send(request.prepare())

            mask = Image.open(io.BytesIO(response.content))

            # Put combined mask on white background
            background = Image.new("RGB", (width, height), (255, 255, 255))
            background.paste(mask, mask=mask)
        except Exception as e:
            settings.ROOT_LOGGER.exception(e)
            # If anything occurs during the mask creation, we have to make sure the response won't contain any
            # information at all.
            # So create an error mask
            background = Image.new(
                "RGB",
                (width, height),
                (
                    settings.ERROR_MASK_VAL,
                    settings.ERROR_MASK_VAL,
                    settings.ERROR_MASK_VAL,
                ),
            )

        return background

    def _create_image_with_text(self, w: int, h: int, txt: str):
        """Renders text on an empty image
        Args:
            w (int): The image width
            h (int): The image height
            txt (str): text to be rendered
        Returns:
             text_img (Image): The image containing text
        """
        get_params = self.remote_service.get_get_params(
            query_params=self.request.query_parameters
        )
        width = int(get_params.get(self.remote_service.WIDTH_QP))
        text_img = Image.new("RGBA", (width, int(h)), (255, 255, 255, 0))
        draw = ImageDraw.Draw(text_img)
        font_size = int(h * settings.FONT_IMG_RATIO)

        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size
        )
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
        request = self.remote_service.construct_request(
            query_params=self.request.GET)
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
        """Return the GetFeatureInfo response if the bbox is covered by any allowed area or the response features are
        contained in any allowed area.
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
                request = self.remote_service.construct_request(
                    query_params=self.request.GET
                )
                if request.params[self.remote_service.INFO_FORMAT_QP] != "text/xml":
                    (
                        xml_response,
                        requested_response,
                    ) = self.handle_get_feature_info_with_multithreading()
                else:
                    xml_response = self.get_remote_response(request=request)
                    requested_response = xml_response
                feature_collection = xmlmap.load_xmlobject_from_string(
                    xml_response.content, xmlclass=FeatureCollection
                )
                # FIXME: depends on xml wfs version not on the registered service version
                axis_order_correction = (
                    True if self.service.major_service_version >= 2 else False
                )
                polygon = feature_collection.bounded_by.get_geometry(
                    axis_order_correction
                )
                if self.service.allowed_area_union.contains(polygon.convex_hull):
                    return self.return_http_response(response=requested_response)
            except Exception:
                pass
        return ForbiddenException()

    def handle_secured_wms(self):
        """Handler to decide which subroutine for the given request param shall run.
        :return: the correct handler function for the given request param.
        :rtype: function
        """
        if (
            self.request.query_parameters.get("request").lower()
            == OGCOperationEnum.GET_MAP.value.lower()
        ):
            return self.handle_secured_get_map()
        elif (
            self.request.query_parameters.get("request").lower()
            == OGCOperationEnum.GET_FEATURE_INFO.value.lower()
        ):
            return self.handle_secured_get_feature_info()

    def get_secured_response(self):
        """Return a filtered response based on the requested bbox
        .. note::
            This function will only be called, if the service is spatial secured and the user is in principle
            entitled! If so we filter the allowed_operations again by with the bbox param.
        :return: the correct handler function for the given service type.
        :rtype: function
        """
        return self.handle_secured_wms()

    def get_remote_response(self, request: Request = None):
        """Perform a request to the :attr:`~GenericOwsServiceOperationFacade.remote_service` with the given
        query parameters or if ``request`` is provided this request is performed.
        :param request: a prepared request which shall used instead of the constructed request from the remote
                        service.
        :type request: :class:`requests.models.Request`, optional
        :return: the response of the remote service
        :rtype: :class:`requests.models.Response` or dict with ``status_code``, ``content`` and ``code`` if any
                error occurs.
        """
        if not request:
            request = self.remote_service.construct_request(
                query_params=self.request.GET
            )
        if hasattr(self.service, "external_authentication"):
            request.auth = self.service.external_authentication.get_auth_for_request()
        s = Session()
        s.proxies = PROXIES
        r = {}
        try:
            r = s.send(request.prepare())
        except ConnectTimeoutException:
            # response with GatewayTimeout; the remote service response not in timeout
            r.update(
                {
                    "status_code": 504,
                    "code": "MaxResponseTimeExceeded",
                    "content": "remote service didn't response in time.",
                }
            )
        except ConnectionErrorException:
            # response with Bad Gateway; we can't connect to the remote service
            r.update(
                {
                    "status_code": 502,
                    "code": "MaxRetriesExceeded",
                    "content": "can't reach remote service.",
                }
            )
        except Exception as e:
            # todo: log exception
            r.update(
                {
                    "status_code": 500,
                    "code": "InternalServerError",
                    "content": f"{type(e).__name__} raised in function get_remote_response()",
                }
            )
        return r

    def log_response(self, response):
        """Check if response logging is active. If so, the request and response will be logged."""
        if self.service.log_response:
            with transaction.atomic():
                if self.request.user.username == "":
                    user = get_user_model().objects.get(username="AnonymousUser")
                else:
                    user = self.request.user
                regex = re.compile("^HTTP_")
                headers = dict(
                    (regex.sub("", header), value)
                    for (header, value) in self.request.META.items()
                    if header.startswith("HTTP_")
                )
                request_log = HttpRequestLog(
                    timestamp=self.start_time,
                    elapsed=datetime.datetime.now() - self.start_time,
                    method=self.request.method,
                    url=self.request.get_full_path(),
                    headers=headers,
                    service=self.service,
                    user=user,
                )
                if self.request.body:
                    content_type = self.request.content_type
                    if "/" in content_type:
                        content_type = content_type.split("/")[-1]
                    request_log.body.save(
                        name=f'{self.start_time.strftime("%Y_%m_%d-%I_%M_%S_%p")}.{content_type}',
                        content=ContentFile(self.request.body),
                    )
                else:
                    request_log.save()
                if isinstance(response, dict):
                    response_log = HttpResponseLog(
                        status_code=response.get("status_code"),
                        reason=response.get("reason"),
                        elapsed=response.get("elapsed"),
                        headers=response.get("headers"),
                        url=response.get("url"),
                        request=request_log,
                    )
                    if response.get("content", None):
                        content_type = response.get("content_type")
                        if "/" in content_type:
                            content_type = content_type.split("/")[-1]
                        response_log.content.save(
                            name=f'{self.start_time.strftime("%Y_%m_%d-%I_%M_%S_%p")}.{content_type}',
                            content=ContentFile(response.get("content")),
                        )
                    else:
                        response_log.save()
                else:
                    response_log = HttpResponseLog(
                        status_code=response.status_code,
                        reason=response.reason,
                        elapsed=response.elapsed,
                        headers=dict(response.headers),
                        url=response.url,
                        request=request_log,
                    )
                    if response.content:
                        content_type = response.headers.get("content-type")
                        if "/" in content_type:
                            content_type = content_type.split("/")[-1]
                        response_log.content.save(
                            name=f'{self.start_time.strftime("%Y_%m_%d-%I_%M_%S_%p")}.{content_type}',
                            content=ContentFile(response.content),
                        )
                    else:
                        response_log.save()

    def return_http_response(self, response):
        """Return the http response for the client.
        :param response: the response with status code, content and content type
        :type response: :class:`requests.models.Response` or dict
        :return: The secured response or an ows exception report if ``status_code >399`` and
                 ``isinstance(response, dict) == True``.
        :rtype: :class:`django.http.response.StreamingHttpResponse` if response >= 500000 else
                :class:`django.http.response.HttpResponse`
        """
        headers = {}
        if isinstance(response, dict):
            content = response.get("content", "unknown")
            status_code = response.get("status_code", 200)
            content_type = response.get("content_type", None)
        else:
            content = response.content
            status_code = response.status_code
            content_type = response.headers.get("content-type")
            content_disposition = response.headers.get(
                "content-disposition", None)
            content_encoding = response.headers.get("content-encoding", None)
            if content_disposition:
                headers.update({"Content-Disposition": content_disposition})
            if content_encoding:
                headers.update({"Content-Encoding": content_encoding})

        if isinstance(response, dict) and status_code > 399:
            # todo: response with owsExceptionReport: http://schemas.opengis.net/ows/1.1.0/owsExceptionReport.xsd
            content = render_to_string(
                template_name="registry/xml/ows/exception.xml", context=response
            )
            content_type = "text/xml"

        if len(content) >= 5000000:
            # data too big - we should stream it!
            computed_response = StreamingHttpResponse(
                status=status_code,
                streaming_content=BytesIO(content),
                content_type=content_type,
                headers=headers,
            )
        else:
            computed_response = HttpResponse(
                status=status_code,
                content=content,
                content_type=content_type,
                headers=headers,
            )

        self.log_response(response=response)
        return computed_response