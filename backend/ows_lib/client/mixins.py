from abc import ABC

from ows_lib.client.exceptions import InitialError
from ows_lib.client.utils import update_queryparams
from ows_lib.models.ogc_request import OGCRequest
from ows_lib.xml_mapper.capabilities.mixins import OGCServiceMixin
from ows_lib.xml_mapper.utils import get_parsed_service
from requests import Request, Session


class OgcClient(ABC):
    capabilities: OGCServiceMixin = None

    def __init__(
            self,
            capabilities,
            session: Session = Session(),
            *args,
            **kwargs):
        super().__init__(*args, **kwargs)

        self.session = session

        if isinstance(capabilities, OGCServiceMixin):
            self.capabilities = capabilities
        elif capabilities is str and "?" in capabilities:
            # client was initialized with an url
            response = self.send_request(
                request=Request(method="GET", url=capabilities))
            if response.status_code <= 202 and "xml" in response.headers["content-type"]:
                self.capabilities = get_parsed_service(response.content)
            else:
                raise InitialError(
                    f"client could not be initialized by the given url: {capabilities}. Response status code: {response.status_code}")

    def send_request(self, request: Request, timeout: int = 10):
        return self.session.send(request=request.prepare(), timeout=timeout)

    def bypass_request(self, request: OGCRequest) -> Request:
        if request.is_get:
            return Request(
                method="GET",
                url=self.capabilities.get_operation_url_by_name_and_method(
                    name=request.operation, method="Get"),
                params=request.request.GET,
                headers=request.request.headers)
        if request.is_post:
            return Request(
                method="POST",
                url=self.capabilities.get_operation_url_by_name_and_method(
                    name=request.operation, method="Post"),
                data=request.request.body,
                headers=request.request.headers)

    def prepare_get_capabilitites_request(
            self,) -> Request:

        params = {
            "VERSION": self.capabilities.service_type.version,
            "REQUEST": "GetCapabilities",
            "SERVICE": self.capabilities.service_type.name
        }

        url = update_queryparams(
            url=self.capabilities.get_operation_url_by_name_and_method(
                "GetCapabilities", "Get").url,
            params=params)

        return Request(method="GET", url=url)
