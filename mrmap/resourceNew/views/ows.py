import base64
from io import BytesIO
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.generic.base import View
from requests.exceptions import ReadTimeout
from MrMap.decorators import log_proxy
from MrMap.messages import SERVICE_NOT_FOUND, SECURITY_PROXY_ERROR_MISSING_REQUEST_TYPE, SERVICE_DISABLED,\
    SERVICE_LAYER_NOT_FOUND, SECURITY_PROXY_NOT_ALLOWED, CONNECTION_TIMEOUT
from resourceNew.enums.service import AuthTypeEnum, OGCServiceEnum
from resourceNew.models import Service
from resourceNew.models.security import AllowedOperation
from resourceNew.ows_client.request_builder import OgcService
from service.helper.crypto_handler import CryptoHandler
from service.helper.enums import OGCOperationEnum, HttpMethodEnum
from service.serializer.ogc.operation_request_handler import OGCOperationRequestHandler
from service.models import Metadata, ProxyLog
from service.tasks import async_log_response
from django.db.models import Max, Count, F, Exists, OuterRef, Q, ExpressionWrapper, BooleanField
from requests.auth import HTTPDigestAuth
from requests import Session, Response
from queue import Queue
from threading import Thread
from MrMap.utils import execute_threads
from django.db import connection


class GenericOwsServiceOperationFacade(View):
    service = None
    remote_service = None
    content_type = None
    query_parameters = None

    def setup(self, request, *args, **kwargs):
        super().setup(request=request, *args, **kwargs)
        self.query_parameters = {k.lower(): v for k, v in self.request.GET.items()}
        try:
            self.service = Service.objects \
                .select_related("document",
                                "service_type",
                                "external_authentication",
                                ) \
                .prefetch_related("operation_urls",
                                  "allowed_operations",
                                  "allowed_operations__secured_layers",
                                  "allowed_operations__secured_feature_types", ) \
                .get(pk=self.kwargs.get("pk"))
            base_url = self.service.operation_urls.values_list('url', flat=True) \
                .get(method=HttpMethodEnum.GET.value,
                     operation__iexact=self.query_parameters.get("request"))
            self.remote_service = OgcService(base_url=base_url,
                                             service_type=self.service.service_type_name,
                                             version=self.service.service_version)
        except Service.DoesNotExist:
            return HttpResponse(status=404, content=SERVICE_NOT_FOUND)

    def get(self, request, *args, **kwargs):
        if not self.query_parameters.get("request"):
            return HttpResponse(status=400, content=SECURITY_PROXY_ERROR_MISSING_REQUEST_TYPE)
        elif not self.service.is_active:
            return HttpResponse(status=423, content=SERVICE_DISABLED)
        elif self.query_parameters.get("request").lower() == OGCOperationEnum.GET_CAPABILITIES.value.lower():
            return self.get_capabilities()
        elif self.service.allowed_operations.exists():
            # this service is basically secured! we need to check some things...
            # 1. requesting user has principle access?
            # 2. requesting user has access for the requested area?
            return self.get_secured_response()
        else:
            return self.get_response()

    def get_capabilities(self):
        # todo: handle different service versions
        return HttpResponse(status=200,
                            content=self.service.document.xml,
                            content_type="application/xml")

    def get_secured_response(self):
        is_user_entitled_filter = Q(allowed_groups__pk__in=self.request.user.groups.values_list("pk", flat=True),
                                    operations__operation__iexact=self.query_parameters.get("request"))
        if self.service.allowed_operations.filter(is_user_entitled_filter).exists():
            return HttpResponse(status=403, content="user has no permission to access the requested service.")
        if self.service.service_type_name == OGCServiceEnum.WMS.value:

            layer_identifiers = self.remote_service.get_requested_layers(query_params=self.request.GET)
            is_layer_secured = Q(secured_layers__identifier__in=layer_identifiers)
            self.service.allowed_areas = self.service.allowed_operations.filter(is_layer_secured).values_list(
                "allowed_area", flat=True)

        elif self.service.service_type_name == OGCServiceEnum.WFS.value:
            pass

    def get_response(self):
        request = self.remote_service.construct_request_with_get_dict(get_dict=self.request.GET)
        if hasattr(self.service, "external_authenticaion"):
            username, password = self.service.external_authenticaion.decrypt()
            if self.service.external_authenticaion.auth_type == AuthTypeEnum.BASIC.value:
                request.auth = (username, password)
            elif self.service.external_authenticaion.auth_type == AuthTypeEnum.DIGEST.value:
                request.auth = HTTPDigestAuth(username=username,
                                              password=password)
        s = Session()
        response = s.send(request.prepare())
        self.content_type = response.headers.get("content-type")
        self.log_response(response=response)
        return self.get_http_response(response=response)

    def log_response(self, response: Response):
        if self.service.log_response:
            # todo
            pass

    def get_http_response(self, response):
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
