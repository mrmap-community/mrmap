from io import BytesIO
from django.http import HttpResponse, StreamingHttpResponse
from django.views.generic.base import View
from MrMap.messages import SERVICE_NOT_FOUND, SECURITY_PROXY_ERROR_MISSING_REQUEST_TYPE, SERVICE_DISABLED
from resourceNew.enums.service import AuthTypeEnum, OGCServiceEnum
from resourceNew.models import Service
from resourceNew.ows_client.request_builder import OgcService
from service.helper.enums import OGCOperationEnum
from django.db.models import Q, QuerySet
from requests.auth import HTTPDigestAuth
from requests import Session, Response, Request

import time
import urllib
import io
from collections import OrderedDict
from copy import copy

from queue import Queue
from threading import Thread

from PIL import Image, ImageFont, ImageDraw
from cryptography.fernet import InvalidToken
from django.contrib.gis.gdal import SpatialReference
from django.core.exceptions import ObjectDoesNotExist
from django.db import connection
from django.db.models import Q
from lxml import etree

from django.contrib.gis.geos import Polygon, GEOSGeometry, Point, GeometryCollection, MultiLineString
from django.http import HttpRequest, HttpResponse, QueryDict
from lxml.etree import QName, _Element

from MrMap import utils
from MrMap.messages import PARAMETER_ERROR, TD_POINT_HAS_NOT_ENOUGH_VALUES, \
    SECURITY_PROXY_ERROR_MISSING_EXT_AUTH_KEY, SECURITY_PROXY_ERROR_WRONG_EXT_AUTH_KEY, \
    OPERATION_HANDLER_MULTIPLE_QUERIES_NOT_ALLOWED
from MrMap.settings import GENERIC_NAMESPACE_TEMPLATE, XML_NAMESPACES
from MrMap.utils import execute_threads
from service.helper import xml_helper
from service.helper.common_connector import CommonConnector
from service.helper.crypto_handler import CryptoHandler
from service.helper.enums import OGCOperationEnum, OGCServiceEnum, OGCServiceVersionEnum
from service.helper.epsg_api import EpsgApi
from service.serializer.ogc.request_builder import OGCRequestPOSTBuilder
from service.models import Metadata, FeatureType, Layer, ProxyLog, AllowedOperation
from service.settings import ALLLOWED_FEATURE_TYPE_ELEMENT_GEOMETRY_IDENTIFIERS, DEFAULT_SRS, DEFAULT_SRS_STRING, \
    MAPSERVER_SECURITY_MASK_FILE_PATH, MAPSERVER_SECURITY_MASK_TABLE, MAPSERVER_SECURITY_MASK_KEY_COLUMN, \
    MAPSERVER_SECURITY_MASK_GEOMETRY_COLUMN, MAPSERVER_LOCAL_PATH, DEFAULT_SRS_FAMILY, MIN_FONT_SIZE, FONT_IMG_RATIO, \
    RENDER_TEXT_ON_IMG, MAX_FONT_SIZE, ERROR_MASK_VAL, ERROR_MASK_TXT, service_logger



class GenericOwsServiceOperationFacade(View):
    service = None
    remote_service = None
    content_type = None
    query_parameters = None

    def setup(self, request, *args, **kwargs):
        super().setup(request=request, *args, **kwargs)
        self.query_parameters = {k.lower(): v for k, v in self.request.GET.items()}
        try:
            self.service = Service.security.for_security_facade(query_parameters=self.query_parameters,
                                                                user=self.request.user)\
                                           .get(pk=self.kwargs.get("pk"))
            self.remote_service = OgcService(base_url=self.service.base_operation_url,
                                             service_type=self.service.service_type_name,
                                             version=self.service.service_version)
        except Service.DoesNotExist:
            self.service = None

    def get(self, request, *args, **kwargs):
        if not self.service:
            return HttpResponse(status=404, content=SERVICE_NOT_FOUND)
        if not self.query_parameters.get("request", None):
            return HttpResponse(status=400, content=SECURITY_PROXY_ERROR_MISSING_REQUEST_TYPE)
        elif not self.service.is_active:
            return HttpResponse(status=423, content=SERVICE_DISABLED)
        elif self.query_parameters.get("request").lower() == OGCOperationEnum.GET_CAPABILITIES.value.lower():
            return self.get_capabilities()
        elif not self.service.is_secured or \
                (not self.service.is_spatial_secured and self.service.user_is_principle_entitled):
            return self.get_response()
        elif self.service.is_spatial_secured and self.service.user_is_principle_entitled:
            return self.get_secured_response()
        else:
            return HttpResponse(status=403, content="user has no permission to access the requested service.")

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

        Args:
            allowed_operations (QuerySet): AllowedOperations objects as tuples (pk, allowed_area)
        Returns:
             bytes
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
                    "map": MAPSERVER_SECURITY_MASK_FILE_PATH,
                    "version": get_params.get(self.remote_service.VERSION_QP),
                    "request": "GetMap",
                    "service": "WMS",
                    "format": "image/png",
                    "layers": "mask",
                    "srs": get_params.get(self.remote_service.CRS_QP),
                    "bbox": get_params.get(self.remote_service.BBOX_QP),
                    "width": width,
                    "height": height,
                    "keys": f"'{pk}'",
                    "table": MAPSERVER_SECURITY_MASK_TABLE,
                    "key_column": MAPSERVER_SECURITY_MASK_KEY_COLUMN,
                    "geom_column": MAPSERVER_SECURITY_MASK_GEOMETRY_COLUMN,
                }
                request = Request(method="GET",
                                  url=MAPSERVER_LOCAL_PATH,
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

    def _create_masked_image(self, img: bytes, mask: bytes, as_bytes: bool = False):
        """ Creates a masked image from two image byte object

        Args:
            img (byte): The bytes of the image
            mask (byte): The bytes of the mask
            as_bytes (bool): Whether the image should be returned as Image object or as bytes
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
            # todo: if img.mode != self.access_denied_img.mode --> img.convert() to self.access_denied_img.mode
            img = Image.alpha_composite(img, self.access_denied_img)
            img.format = old_format

        if as_bytes:
            out_bytes_stream = io.BytesIO()
            try:
                img.save(out_bytes_stream, img.format, quality=80)
                img = out_bytes_stream.getvalue()
            except IOError:
                # happens if a non-alpha channel format is requested, such as jpeg
                # replace alpha channel with white background
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                bg.save(out_bytes_stream, img.format, quality=80)
                img = out_bytes_stream.getvalue()
        return img

    def get_secured_response(self):
        """ Return a filtered response based on the requested bbox

            This function will only be called, if the service is spatial secured and the user is in principle
            entitled! If so we filter the allowed_operations again by with the bbox param.
        """

        if self.service.service_type_name == OGCServiceEnum.WMS.value:
            layer_identifiers = self.remote_service.get_requested_layers(query_params=self.request.GET)
            is_layer_secured = Q(secured_layers__identifier__in=layer_identifiers)

            self.service.allowed_areas = self.service.allowed_operations\
                .filter(is_layer_secured)\
                .distinct("pk")\
                .values_list("pk", "allowed_area")
            i=0

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

            secured_image = self._create_masked_image(remote_response.content, mask, as_bytes=True)
            self.content_type = secured_image.format
            _response = object()
            _response.content = secured_image
            _response.status_code = 200
            return self.return_http_response(response=_response)

        elif self.service.service_type_name == OGCServiceEnum.WFS.value:
            pass

    def get_remote_response(self) -> Response:
        request = self.remote_service.construct_request_with_get_dict(query_params=self.request.GET)
        if hasattr(self.service, "external_authenticaion"):
            username, password = self.service.external_authenticaion.decrypt()
            if self.service.external_authenticaion.auth_type == AuthTypeEnum.BASIC.value:
                request.auth = (username, password)
            elif self.service.external_authenticaion.auth_type == AuthTypeEnum.DIGEST.value:
                request.auth = HTTPDigestAuth(username=username,
                                              password=password)
        s = Session()
        return s.send(request.prepare())

    def get_response(self):
        response = self.get_remote_response()
        self.content_type = response.headers.get("content-type")
        self.log_response(response=response)
        return self.return_http_response(response=response)

    def log_response(self, response: Response):
        """ Check if response logging is active. If so, the response will be logged.

        """
        if self.service.log_response:
            # todo
            pass

    def return_http_response(self, response):
        """ Check if response is greater than ~5 MB.

            Returns:
                if response >= ~ 5MB: StreamingHttpResponse
                else: HttpResponse

        """
        if len(response.content) >= 5000000:
            # data too big - we should stream it!
            # make sure the response is in bytes
            if not isinstance(response, bytes):
                response = bytes(response)
            buffer = BytesIO(response)
            return StreamingHttpResponse(streaming_content=buffer,
                                         content_type=self.content_type)
        else:
            return HttpResponse(status=response.status_code,
                                content=response.content,
                                content_type=self.content_type)
