from abc import ABC

from lxml import etree
from registry.client.exceptions import InitialError
from registry.enums.service import HttpMethodEnum, OGCOperationEnum
from requests import Request, Response, Session


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
                "capabilities has to be GetCapabilities URL or parsed capabilites of type OGCServiceMixin")

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

    def get_operation_url_by_name_and_method(self, operation_name: OGCOperationEnum, method: HttpMethodEnum) -> str:
        """Returns the operation url by the given operation name and method

        :param operation_name: The name of the operation
        :type operation_name: str

        :param method: The method of the operation
        :type method: str

        :return: The operation url
        :rtype: str
        """

        root = self._capabilities_etree
        nsmap = root.nsmap.copy()

        # Normalize default namespace
        if None in nsmap:
            nsmap["ows"] = nsmap.pop(None)

        # OWS OperationsMetadata path (WFS / CSW / newer WMS)
        operation_xpath = (
            ".//ows:OperationsMetadata/"
            "ows:Operation[@name=$op_name]"
        )

        operations = root.xpath(
            operation_xpath,
            namespaces=nsmap,
            op_name=operation_name.label,
        )

        # Older WMS (1.1.1) fallback
        if not operations:
            operation_xpath = (
                ".//Request/*[local-name()=$op_name]"
            )
            operations = root.xpath(
                operation_xpath,
                op_name=operation_name.label,
            )

        if not operations:
            raise InitialError(
                f"Operation '{operation_name.label}' not found in capabilities"
            )

        operation = operations[0]

        method_name = method.label.capitalize()  # GET / POST

        # OWS-style DCP
        hrefs = operation.xpath(
            f".//ows:DCP/ows:HTTP/ows:{method_name}/@xlink:href",
            namespaces={
                **nsmap,
                "xlink": "http://www.w3.org/1999/xlink",
            },
        )

        # WMS 1.1.1-style fallback
        if not hrefs:
            hrefs = operation.xpath(
                f".//{method_name}/OnlineResource/@xlink:href",
                namespaces={
                    "xlink": "http://www.w3.org/1999/xlink",
                },
            )

        if not hrefs:
            raise InitialError(
                f"Operation '{operation_name.value}' "
                f"does not support HTTP method '{method.value}'"
            )

        return hrefs[0]

    def send_request(self, request: Request, timeout: int = 10) -> Response:
        """Sends a given request with internal session object.

        :param request: A request object that shall be sended
        :type request: requests.Request

        :param timeout: The time value for maximium waiting time of the response.
        :type int:

        :return: Returns the response of the given request
        :rtype: requests.Response

        """
        return self.session.send(request=request.prepare(), timeout=timeout)
