from abc import ABC
from urllib.parse import urlparse

from lxml import etree
from registry.enums.service import HttpMethodEnum, OGCOperationEnum
from registry.ows_lib.client.exceptions import (InitialError,
                                                RedirectChainError)
from registry.ows_lib.request.utils import update_queryparams
from requests import Request, Response, Session
# the answers requests itself treats as redirects, so the client stops where the session would
# have stopped following as well
from requests.models import REDIRECT_STATI

# The redirect hops this client follows for one request. The session answers 30 of them by
# default, so an endpoint which redirects back at itself walks all 30 before it raises - and
# walks them again on every retry of a harvest (#1100). An endpoint which needs more hops than
# these to answer its document does not answer it.
MAX_REDIRECTS = 5
# The ports a URL does not name but uses; only a port which is named tells two services apart.
DEFAULT_PORTS = {"http": 80, "https": 443}


def _host_of(url: str):
    """The host a URL is served from, or None when its port names no host at all

    The scheme is not part of the answer on purpose: an endpoint registered as http is served
    over https the same way, so a redirect may change it - and with it the default port of the
    scheme, which says nothing more about the service. A port beyond that default does, and so
    does another host. Every other scheme names another host or no host at all, so the same
    comparison refuses a hop to a scheme this client has no adapter for.
    """
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError:
        # a port which is no number is no host a redirect may land on
        return None
    if port == DEFAULT_PORTS.get(parsed.scheme):
        port = None
    return (parsed.hostname, port)


class OgcClient(ABC):
    """Abstract OgcClient class which implements some basic functionality for all ogc client applications

    :param capabilities: The capabilities document to initialize the client
    :type capabilities: OGCServiceMixin | str

    :param session: The session object that shall be used
    :type session: requests.Session, optional
    """

    _capabilities = None
    _capabilities_etree = None

    def __init__(
            self,
            capabilities,
            session: Session = Session(),
            *args,
            **kwargs):
        super().__init__(*args, **kwargs)

        self.session = session

        if isinstance(capabilities, str) and "?" in capabilities:
            # client was initialized with an url
            response = self.send_request(
                request=Request(method="GET", url=capabilities))
            if response.status_code <= 202 and "xml" in response.headers["content-type"]:
                self._capabilities = response.content
            else:
                raise InitialError(
                    f"client could not be initialized by the given url: {capabilities}. Response status code: {response.status_code}")
        elif isinstance(capabilities, bytes):
            self._capabilities = capabilities
        else:
            raise TypeError(
                f"capabilities has to be GetCapabilities URL or parsed capabilites of type str or bytes not {type(capabilities)}")

        self._capabilities_etree = etree.fromstring(self._capabilities)

    @property
    def service_type(self):
        """Returns the service type of this client

        :return: The service type of this client
        :rtype: OGCServiceEnum
        """

        # Service-Typ anhand des Root-Tags
        tag = etree.QName(self._capabilities_etree).localname.lower()
        if any(s in tag for s in ["wms", "wmt"]):
            service_type = "WMS"
        elif "wfs" in tag:
            service_type = "WFS"
        elif "capabilities" in tag and "csw" in self._capabilities_etree.nsmap.keys():
            service_type = "CSW"
        else:
            raise ValueError("Unknown Service-Typ")

        return service_type

    @property
    def service_version(self):
        """Returns the service version of this client

        :return: The service version of this client
        :rtype: OGCServiceVersionEnum
        """
        # Version aus Attribut
        version = self._capabilities_etree.attrib.get("version")
        if not version:
            raise ValueError("Version could not be detected")
        return version

    def get_operation_url_by_name_and_method(
        self,
        operation_name: OGCOperationEnum,
        method: HttpMethodEnum,
    ) -> str:
        """
        Returns the operation URL by the given operation name and HTTP method,
        using service type and version specific parsing logic.
        """

        root = self._capabilities_etree
        service_type = self.service_type
        service_version = self.service_version
        method_name = method.label.capitalize()  # GET / POST

        nsmap = root.nsmap.copy()
        if None in nsmap:
            nsmap["ows"] = nsmap.pop(None)

        # ------------------------------------------------------------------
        # WFS / CSW (OWS Common OperationsMetadata)
        # ------------------------------------------------------------------
        if service_type in {"WFS", "CSW"}:
            operation_xpath = (
                ".//*[local-name()='OperationsMetadata']"
                "/*[local-name()='Operation' and @name='%s']"
                % operation_name.label
            )

            operations = root.xpath(operation_xpath)
            if not operations:
                raise InitialError(
                    f"Operation '{operation_name.label}' not found in "
                    f"{service_type} {service_version} capabilities"
                )

            operation = operations[0]

            hrefs = operation.xpath(
                ".//*[local-name()='DCP']"
                "/*[local-name()='HTTP']"
                f"/*[local-name()='{method_name}']/@*[local-name()='href']"
            )

            if not hrefs:
                raise InitialError(
                    f"Operation '{operation_name.label}' does not support "
                    f"HTTP {method_name} in {service_type} {service_version}"
                )

            return hrefs[0]

        # ------------------------------------------------------------------
        # WMS uses Capability/Request in both 1.1.1 and 1.3.0
        # ------------------------------------------------------------------
        if service_type == "WMS":
            operation_xpath = (
                ".//*[local-name()='Request']"
                "/*[local-name()='%s']"
                % operation_name.label
            )

            operations = root.xpath(operation_xpath)
            if not operations:
                raise InitialError(
                    f"Operation '{operation_name.label}' not found in "
                    f"WMS {service_version} capabilities"
                )

            operation = operations[0]

            hrefs = operation.xpath(
                f".//*[local-name()='{method_name}']"
                "/*[local-name()='OnlineResource']/@*[local-name()='href']"
            )

            if not hrefs:
                raise InitialError(
                    f"Operation '{operation_name.label}' does not support "
                    f"HTTP {method_name} in WMS {service_version}"
                )

            return hrefs[0]

        # ------------------------------------------------------------------
        # Unsupported service/version
        # ------------------------------------------------------------------
        raise InitialError(
            f"Unsupported service/version combination: "
            f"{service_type} {service_version}"
        )

    def get_capabilities_request(self) -> Request:
        """Constructs a GetCapabilities request object

        :return: the constructed get capabilities request object
        :rtype: Request
        """
        method = HttpMethodEnum.GET

        params = {
            "VERSION": self.service_version,
            "REQUEST": OGCOperationEnum.GET_CAPABILITIES.label,
            "SERVICE": self.service_type
        }
        url = update_queryparams(
            url=self.get_operation_url_by_name_and_method(
                OGCOperationEnum.GET_CAPABILITIES, method),
            params=params
        )
        return Request(method=method.label.upper(), url=url)

    def send_request(self, request: Request, timeout: int = 10, *args, **kwargs) -> Response:
        """Sends a given request with internal session object.

        Redirects are followed with the budget of ``MAX_REDIRECTS`` hops and never beyond the
        host of the requested URL. An endpoint which redirects back at itself, or away to a
        login page of whoever serves it, is not the endpoint - and the walk to it is the same
        on every retry, so the error which ends such a chain names the requested URL and the
        target of the last redirect instead of a bare redirect count (#1100).

        :param request: A request object that shall be sended
        :type request: requests.Request

        :param timeout: The time value for maximium waiting time of the response.
        :type int:

        :return: Returns the response of the given request
        :rtype: requests.Response

        :raises RedirectChainError: if the redirects of the remote service do not lead to an
            answer within the budget of the client or leave its host
        """
        # the redirect policy belongs to the client, not to the caller or to the session it
        # shares with other clients of the same service
        kwargs.pop("allow_redirects", None)
        origin = _host_of(request.url)

        # The client asks for every hop itself, so the budget is its own and the walk stops at
        # the hop which does not lead on. The target of a hop is resolved by requests itself:
        # `next` of a response which answers with a redirect is the prepared request of that
        # target, with a relative Location resolved, the cookies of the hop merged and the
        # method of a 303 applied. An answer which is no redirect status - a refusal which
        # names a page all the same - is the answer of the endpoint and is asked nothing more.
        prepared = self.session.prepare_request(request)
        # one request for the endpoint itself, then one per hop the client follows
        for _ in range(MAX_REDIRECTS + 1):
            response = self.session.send(
                request=prepared, timeout=timeout, allow_redirects=False, *args, **kwargs)
            if response.status_code not in REDIRECT_STATI:
                return response
            prepared = response.next
            if prepared is None:
                # an answer which redirects names no target to ask
                return response
            target = _host_of(prepared.url)
            if target is None or target != origin:
                raise RedirectChainError(
                    f"the endpoint {request.url} redirects to {prepared.url}, which is not "
                    f"served by the host of the endpoint")
        raise RedirectChainError(
            f"the endpoint {request.url} answered {MAX_REDIRECTS + 1} redirects in a row; "
            f"the last of them names {prepared.url}")
