from abc import ABC

from requests import Request, Response, Session


class OgcClient(ABC):
    REQUEST_QP = "REQUEST"
    SERVICE_QP = "SERVICE"
    VERSION_QP = "VERSION"
    GET_CAPABILITIES_QV = "GetCapabilities"

    # TODO: calculate service_type
    DEFAULT_QUERY_PARAMS = {SERVICE_QP: "service_type"}

    def __init__(
            self,
            capabilities: Capabilities,
            session: Session = Session(),
            *args,
            **kwargs):
        self.session = session
        self.capabilities = capabilities
        super().__init__(*args, **kwargs)

    def __init__(
        self,
        capabilities_url: URL
    ):
        super().__init__()

    def send_request(self, request: Request):
        return self.session.send(request=request.prepare())

    def get_operation_by_name(self, operation: str):
        """Returns the concrete ogc operation by name"""
        if hasattr(self, operation):
            return getattr(self, operation)

    def get_get_capabilities_request(self) -> Request:
        query_params = DEFAULT_QUERY_PARAMS
        query_params.update({self.REQUEST_QP: self.GET_CAPABILITIES_QV})
        return Request(method="GET", url=self.capabilities.get_capabilities_url, params=query_params)

    def retreive_capabilities(self) -> Response:
        return self.send_request(request=self.get_get_capabilities_request())

    def get_capabilities(self) -> Capabilities:
        if self.capabilities:
            return self.capabilities
        self.capabilities = Capabilities(self.retreive_capabilities())
