from io import BytesIO
from django.http import HttpResponse, StreamingHttpResponse
from django.views.generic.base import View
from MrMap.messages import SERVICE_NOT_FOUND, SECURITY_PROXY_ERROR_MISSING_REQUEST_TYPE, SERVICE_DISABLED
from resourceNew.enums.service import AuthTypeEnum, OGCServiceEnum
from resourceNew.models import Service
from resourceNew.ows_client.request_builder import OgcService
from service.helper.enums import OGCOperationEnum
from django.db.models import Q
from requests.auth import HTTPDigestAuth
from requests import Session, Response


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
        if not self.query_parameters.get("request"):
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
                .values_list("allowed_area", flat=True)
            i=0

        elif self.service.service_type_name == OGCServiceEnum.WFS.value:
            pass

    def get_response(self):
        request = self.remote_service.construct_request_with_get_dict(query_params=self.request.GET)
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
