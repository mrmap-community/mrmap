import re
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models.functions import datetime
from django.http import HttpResponse, StreamingHttpResponse
from django.http.response import Http404
from django.template.loader import render_to_string
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic.base import View
from ows_lib.client.utils import get_client
from ows_lib.models.ogc_request import OGCRequest
from registry.models.security import HttpRequestLog, HttpResponseLog
from registry.proxy.ogc_exceptions import (DisabledException,
                                           ForbiddenException,
                                           MissingRequestParameterException,
                                           MissingVersionParameterException)
from registry.proxy.ogc_exceptions import \
    NotImplementedError as MrMapNotImplementedError
from registry.settings import SECURE_ABLE_OPERATIONS_LOWER
from requests import Request
from requests.exceptions import ConnectionError as ConnectionErrorException
from requests.exceptions import ConnectTimeout as ConnectTimeoutException


@method_decorator(csrf_exempt, name="dispatch")
class OgcServiceProxyView(View):
    """Security proxy facade to secure registered services spatial by there operations and for sets of users.
    :attr service:  :class:`registry.models.service.Service` the requested service which was found by the pk.
    :attr remote_service: :class:`registry.ows_client.request_builder.WebService` the request builder to get
                          prepared :class:`requests.models.Request` objects with the correct uri and query params.

    :attr bbox: :class:`django.contrib.gis.geos.polygon.Polygon` the parsed bbox from query params.
    """
    bbox = None
    start_time = None
    _service = None
    _remote_service = None

    @property
    def is_get_request(self) -> bool:
        return self.request.method == "GET"

    @property
    def is_post_request(self) -> bool:
        return self.request.method == "POST"

    @property
    def service(self):
        if not self._service:
            try:
                self._service = self.service_cls.security.get_with_security_info(
                    pk=self.kwargs.get("pk"), request=self.ogc_request
                )
            except ObjectDoesNotExist:
                raise Http404
        return self._service

    @property
    def service_cls(self):
        raise ImproperlyConfigured(
            "you need to setup the proxy class with the corretc 'service_cls' property.")

    @property
    def remote_service(self):
        if not self._remote_service:
            self._remote_service = get_client(self.service.xml_backup)
        return self._remote_service

    def analyze_request(self):
        """hook method to do adittional stuff in child classes"""
        pass

    def dispatch(self, request, *args, **kwargs):
        self.start_time = datetime.datetime.now()
        self.ogc_request = OGCRequest(request=request)

        exception = self.check_request()
        if exception:
            return exception
        self.analyze_request()

        return self.get_and_post(request=request, *args, **kwargs)

    def check_request(self):
        if not self.ogc_request.operation:
            return MissingRequestParameterException(ogc_request=self.ogc_request)
        elif not self.ogc_request.service_version:
            return MissingVersionParameterException(ogc_request=self.ogc_request)

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
            :meth:`~GenericOwsServiceOperationFacade.secure_request`
        **Default behavior**:
            return ``403 (Forbidden) - User has no permissions to request this service.``
        .. note::
            all error messages will be send as an owsExceptionReport. See
            :meth:`~GenericOwsServiceOperationFacade.return_http_response` for details.
        :return: the computed response based on some principle decisions.
        :rtype: dict or :class:`requests.models.Request`
        """
        if self.ogc_request.is_get_capabilities_request:
            return self.get_capabilities()
        elif not self.service.is_active:
            return DisabledException(ogc_request=self.ogc_request)
        # elif self.service.is_unknown_layer:
        #     return LayerNotDefined()
        elif (
            self.ogc_request.operation.lower() not in SECURE_ABLE_OPERATIONS_LOWER
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
            try:
                return self.secure_request()
            except NotImplementedError:
                return MrMapNotImplementedError(ogc_request=self.ogc_request)
        else:
            return ForbiddenException(ogc_request=self.ogc_request)

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

    def secure_request(self):
        """Handler to decide which subroutine for the given request param shall run.
        :return: the correct handler function for the given request param.
        :rtype: function
        """
        raise NotImplementedError()

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
            request = self.remote_service.bypass_request(
                request=self.ogc_request
            )

        r = {}
        try:
            r = self.remote_service.send_request(request)
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
