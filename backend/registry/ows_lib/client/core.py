from abc import ABC

from lxml import etree
from registry.enums.service import HttpMethodEnum, OGCOperationEnum
from registry.ows_lib.client.exceptions import InitialError
from registry.ows_lib.request.utils import update_queryparams
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
        # WFS / CSW / WMS >= 1.3.0 (OWS Common OperationsMetadata)
        # ------------------------------------------------------------------
        if (
            service_type in {"WFS", "CSW"}
            or (service_type == "WMS" and service_version != "1.1.1")
        ):
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
        # WMS 1.1.1 (pre-OWS Common)
        # ------------------------------------------------------------------
        if service_type == "WMS" and service_version == "1.1.1":
            operation_xpath = (
                ".//*[local-name()='Request']"
                "/*[local-name()='%s']"
                % operation_name.label
            )

            operations = root.xpath(operation_xpath)
            if not operations:
                raise InitialError(
                    f"Operation '{operation_name.label}' not found in "
                    "WMS 1.1.1 capabilities"
                )

            operation = operations[0]

            hrefs = operation.xpath(
                f".//*[local-name()='{method_name}']"
                "/*[local-name()='OnlineResource']/@*[local-name()='href']"
            )

            if not hrefs:
                raise InitialError(
                    f"Operation '{operation_name.label}' does not support "
                    f"HTTP {method_name} in WMS 1.1.1"
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
                OGCOperationEnum.GET_CAPABILITIES,
                HttpMethodEnum.GET
            ),
            params=params)

        return Request(method=method.label.upper(), url=url)

    def send_request(self, request: Request, timeout: int = 10, *args, **kwargs) -> Response:
        """Sends a given request with internal session object.

        :param request: A request object that shall be sended
        :type request: requests.Request

        :param timeout: The time value for maximium waiting time of the response.
        :type int:

        :return: Returns the response of the given request
        :rtype: requests.Response

        """
        return self.session.send(request=request.prepare(), timeout=timeout, *args, **kwargs)
