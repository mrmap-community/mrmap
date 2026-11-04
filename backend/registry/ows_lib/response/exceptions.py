from django.http import HttpResponse
from lxml import etree
from lxml.etree import _Element
from registry.ows_lib.xml.builder import XSDSkeletonBuilder
from registry.ows_lib.xml.consts import NAMESPACE_LOOKUP, XSD_LOOKUP

# The services which profile themselves against OWS Common (OGC 05-008) answer an
# error with its ExceptionReport, which is what OGC 07-006r1, 10.3.7 obliges a CSW
# to do; the version attribute of the report names the OWS Common specification
# the report follows.
OWS_COMMON_SERVICE_TYPES = frozenset({"csw"})
OWS_COMMON_EXCEPTION_REPORT_VERSION = "1.2.0"
# An error which refuses the request is refused with the 4xx of the request; the
# WMS style reports of the security proxy keep their class' code (see below).
OWS_COMMON_EXCEPTION_STATUS_CODE = 400


class OGCServiceException(HttpResponse):
    """Exception report of an OGC request, answered as an HttpResponse.

    The report is answered in the shape the answered service profiles: a service
    which profiles against OWS Common (see :meth:`uses_ows_exception_report`) is
    answered with an ``<ows:ExceptionReport version="1.2.0">`` whose
    ``<ows:Exception>`` carries ``exceptionCode``, ``locator`` and an
    ``<ows:ExceptionText>``; the security proxy keeps the ``ServiceExceptionReport``
    skeleton which ``XSD_LOOKUP`` registers for the service type and version it
    answers. A service which registers no skeleton -- a request which names no or
    an unknown service -- is still answered with the OWS Common report: a refused
    request never answers HTML or an empty report (OGC 07-006r1, 10.3.7).
    """

    # the status code the report is answered with; the report profiles choose it
    # (get_status_code), a subclass which carries its own one -- an error which is
    # not a request error -- says so, and a caller which passes ``status`` decides
    # it for a single exception
    status_code = 200
    # the exceptionCode of the report; the subclasses name the code of their error
    # and a subclass which names none is answered with NoApplicableCode, the code
    # OGC 07-006r1, Table 8 leaves for an error which codes itself none
    code = "NoApplicableCode"
    message = None
    locator = None

    def __init__(
        self,
        service_type: str = None,
        service_version: str = None,
        message: str = None,
        locator: str = None,
        ogc_request=None,
        *args,
        **kwargs
    ):
        if message:
            self.message = message
        if locator:
            self.locator = locator
        self.ogc_request = ogc_request
        if ogc_request is not None:
            # the service which answers the request identifies the report which is
            # answered for it; a caller which hands over the request lets the
            # exception read the identity out of it instead of repeating it
            service_type = service_type or ogc_request.service_type
            service_version = service_version or ogc_request.service_version
        self.service_type = service_type
        self.service_version = service_version
        root = self.exception_xml.getroottree().getroot()
        content = etree.tostring(
            root,
            encoding="UTF-8",
            xml_declaration=True,
            pretty_print=True).decode()
        kwargs.setdefault("status", self.get_status_code())
        super().__init__(content_type="application/xml",
                         content=content,
                         *args,
                         **kwargs
                         )

    def __eq__(self, other) -> bool:
        if isinstance(other, OGCServiceException):
            return self.status_code == other.status_code and self.message == other.message and self.locator == other.locator
        return NotImplemented

    def get_locator(self):
        return self.locator

    def get_message(self):
        return self.message

    def get_status_code(self) -> int:
        """The HTTP status code the report is answered with.

        The OWS Common profile refuses a faulty request with 400; the WMS style
        report of the security proxy keeps the code of the class, which is 200
        there. A subclass carries its own code to answer another one.
        """
        if type(self).status_code != OGCServiceException.status_code:
            return type(self).status_code
        if self.uses_ows_exception_report():
            return OWS_COMMON_EXCEPTION_STATUS_CODE
        return self.status_code

    def uses_ows_exception_report(self) -> bool:
        """Whether the OWS Common ExceptionReport answers this exception.

        True for the service types which profile against OWS Common and for every
        service which ``XSD_LOOKUP`` registers no report skeleton for: that
        fallback is what keeps a request which names no service, or one nobody
        serves, from answering a bare HTTP error while its report is built.

        True as well for a registered skeleton which declares no
        ``ServiceExceptionReport`` (#866): the key of a report of the OWS shape
        -- ``ExceptionReport`` with ``Exception`` children, which is what the CSW
        2.0.2 and WFS profiles register -- asked the skeleton builder for an
        element the schema does not declare, and the client was answered the
        childless root the skeleton cannot fill. A service is answered from its
        skeleton only where the skeleton can carry the exception; every other
        refusal is answered by :meth:`build_ows_exception_report`, the one
        report of this machinery which is never empty.
        """
        service_type = (self.service_type or "").lower()
        if service_type in OWS_COMMON_SERVICE_TYPES:
            return True
        key = (service_type, "Exception", self.service_version)
        if key not in XSD_LOOKUP:
            return True
        return not XSDSkeletonBuilder(key).declares_element(
            "ServiceExceptionReport")

    @property
    def exception_xml(self) -> _Element:
        if self.uses_ows_exception_report():
            return self.build_ows_exception_report()
        return self.build_service_exception_report()

    def build_ows_exception_report(self) -> _Element:
        """Build the ExceptionReport of OWS Common (OGC 05-008, clause 8).

        The schema of this report is static -- the ExceptionReport element and the
        Exception type carry everything they reference themselves -- so the report
        is built directly instead of out of the skeleton of a loaded schema.
        """
        ows = NAMESPACE_LOOKUP["ows"]

        report = etree.Element(
            etree.QName(ows, "ExceptionReport"),
            nsmap={"ows": ows},
        )
        report.set("version", OWS_COMMON_EXCEPTION_REPORT_VERSION)

        exception = etree.SubElement(report, etree.QName(ows, "Exception"))
        exception.set("exceptionCode", self.code)
        locator = self.get_locator()
        if locator and locator != "":
            exception.set("locator", locator)

        message = self.get_message()
        if message:
            exception_text = etree.SubElement(
                exception, etree.QName(ows, "ExceptionText"))
            exception_text.text = str(message)

        return report

    def build_service_exception_report(self) -> _Element:
        """Build the ServiceExceptionReport skeleton XSD_LOOKUP registers.

        Only reached for a skeleton which declares the WMS style
        ``ServiceExceptionReport`` root (see :meth:`uses_ows_exception_report`);
        the element name is what that skeleton is keyed by, so the strict
        :meth:`XSDSkeletonBuilder.build_element` can only answer empty for a
        service registered without a report of this shape -- and that shape
        check is what this method's caller consults before asking it.
        """
        builder = XSDSkeletonBuilder(
            (self.service_type.lower(), "Exception", self.service_version)
        )

        report_attributes = {
            "version": self.service_version,
        }

        # Build attributes dict only with non-empty values
        child_attributes = {
            "_text": self.get_message(),
            "_attributes": {}
        }

        if self.code and self.code != "":
            child_attributes["_attributes"].update({"code": self.code})

        locator = self.get_locator()
        if locator and locator != "":
            child_attributes["_attributes"].update({"locator": locator})

        # Remove keys with None or empty values
        child_attributes = {k: v for k, v in child_attributes.items() if v}

        report = builder.build_element(
            element_name="ServiceExceptionReport",
            # nsmap=
            attributes=report_attributes,
            children_attributes={
                "ServiceException": child_attributes
            }
        )
        return report


class MissingParameterException(OGCServiceException):
    code = "MissingParameter"


class MissingRequestParameterException(MissingParameterException):
    locator = "request"
    message = "Could not determine request method from http request."


class MissingVersionParameterException(MissingParameterException):
    locator = "version"
    message = "Could not determine version for the requested service."


class MissingServiceParameterException(MissingParameterException):
    locator = "service"
    message = "Could not determine service for the requested service."


class MissingConstraintLanguageParameterException(MissingParameterException):
    locator = "CONSTRAINTLANGUAGE"
    message = "CONSTRAINTLANGUAGE parameter is missing."


class InvalidParameterValueException(OGCServiceException):
    code = "InvalidParameterValue"


class VersionNegotiationFailedException(OGCServiceException):
    """Refusal of a version negotiation which found nothing common to both sides.

    The code OGC 05-008, Table 4 defines for the `acceptVersions` and
    `updateSequence` negotiation of an OWS GetCapabilities, which OGC 07-006r1
    keeps for a CSW (`VersionNegotiationFailed`); a caller which names another
    parameter as the failed one passes its own ``locator``.
    """

    code = "VersionNegotiationFailed"
    locator = "acceptVersions"
    message = "None of the requested versions is supported by this service."


class ParsingErrorException(OGCServiceException):
    """The request document itself is no parsable document.

    A request which arrives as XML -- the POST binding of OGC 07-006r1, 10.3.2
    -- which is not well-formed XML names its failure nowhere in its parameters,
    so the report locates it at the request document as a whole.
    """
    code = "ParsingError"
    locator = "request"
    message = "The request document could not be parsed."


class OperationNotSupportedException(OGCServiceException):
    code = "OperationNotSupported"
    message = "No such operation"

    def get_locator(self):
        if self.ogc_request is not None:
            return (self.ogc_request.ogc_query_params.get("REQUEST")
                    or self.ogc_request.operation
                    or self.locator)
        return self.locator

    def get_message(self):
        locator = self.get_locator()
        if locator:
            return f"No such operation: {locator}"
        return self.message


class LayerNotDefined(OGCServiceException):
    code = "LayerNotDefined"
    message = "unknown layer"
    locator = "LAYERS"


class RuntimeError(OGCServiceException):
    code = "RuntimeError"
    message = "Something unexpected did occur. Please contact the service provider."


class NotImplementedError(OGCServiceException):
    code = "NotImplementedError"
    message = "MrMap has not implemented the functionality you need."


class DisabledException(OGCServiceException):
    code = "Disabled"
    message = "The requested service is temporaly disabled."


class ForbiddenException(OGCServiceException):
    code = "Forbidden"
    locator = None
    message = "The requesting user has no permissions to access the service."
