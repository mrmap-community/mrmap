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
from resourceNew.enums.service import AuthTypeEnum
from resourceNew.models import Service
from resourceNew.ows_client.request_builder import OgcService
from service.helper.crypto_handler import CryptoHandler
from service.helper.enums import OGCOperationEnum, HttpMethodEnum
from service.serializer.ogc.operation_request_handler import OGCOperationRequestHandler
from service.models import Metadata, ProxyLog
from service.tasks import async_log_response
from django.db.models import Max, Count, F, Exists, OuterRef, Q, ExpressionWrapper, BooleanField
from requests.auth import HTTPDigestAuth
from requests import Session, Response


class GenericOwsServiceOperationFacade(View):
    service = None

    def get(self, request, *args, **kwargs):
        try:
            self.service = Service.objects\
                .select_related("document",
                                "service_type",
                                "external_authentication")\
                .annotate(is_secured=Count("allowed_operations"),
                          log_response=F("proxy_setting__log_response"))\
                .get(pk=self.kwargs.get("pk"))
            # todo: maybe prefetch related layers and feature_types
        except Service.DoesNotExist:
            return HttpResponse(status=404, content=SERVICE_NOT_FOUND)
        if not request.GET.get("request"):
            return HttpResponse(status=400, content=SECURITY_PROXY_ERROR_MISSING_REQUEST_TYPE)
        elif not self.service.is_active:
            return HttpResponse(status=423, content=SERVICE_DISABLED)
        elif request.GET.get("request") == OGCOperationEnum.GET_CAPABILITIES.value.upper():
            return self.get_capabilities()
        elif self.service.is_secured:
            return self.get_secured_response()
        else:
            return self.get_response()

    def get_capabilities(self):
        # todo: handle different service versions
        return HttpResponse(status=200,
                            content=self.service.document.xml,
                            content_type="application/xml")

    def get_secured_response(self):
        # todo
        pass

    def get_response(self):
        base_url = self.service.operation_urls.get(method=HttpMethodEnum.GET.value,
                                                   operation__iexact=self.request.GET.get("request"))

        remote_service = OgcService(base_url=base_url,
                                    service_type=self.service.service_type_name,
                                    version=self.service.service_version)
        request = remote_service.construct_request_with_get_dict(get_dict=self.request.GET)
        if self.service.external_authenticaion:
            crypto_handler = CryptoHandler()
            key = crypto_handler.get_key_from_file(self.service.id)
            self.service.external_authenticaion.decrypt(key)
            if self.service.external_authenticaion.auth_type == AuthTypeEnum.BASIC.value:
                request.auth = (self.service.external_authenticaion.username,
                                self.service.external_authenticaion.password)
            elif self.service.external_authenticaion.auth_type == AuthTypeEnum.DIGEST.value:
                request.auth = HTTPDigestAuth(username=self.service.external_authenticaion.username,
                                              password=self.service.external_authenticaion.password)

        s = Session()
        response = s.send(request)
        self.log_response(response=response)

        return HttpResponse(status=response.status_code,
                            content=response.content,
                            content_type=response.headers.get("content-type"))

    def log_response(self, response: Response):
        if self.service.log_response:
            # todo
            pass
