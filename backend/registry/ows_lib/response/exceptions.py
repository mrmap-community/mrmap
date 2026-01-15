from django.http import HttpResponse
from lxml import etree
from lxml.etree import _Element
from registry.ows_lib.xml.builder import XSDSkeletonBuilder


class OGCServiceException(HttpResponse):
    status_code = 200
    message = None
    locator = None

    def __init__(
        self,
        service_type: str,
        service_version: str,
        message: str = None,
        locator: str = None,
        *args,
        **kwargs
    ):
        if message:
            self.message = message
        if locator:
            self.locator = locator
        self.service_type = service_type
        self.service_version = service_version
        root = self.exception_xml.getroottree().getroot()
        content = etree.tostring(
            root,
            encoding="UTF-8",
            xml_declaration=True,
            pretty_print=True).decode()
        super().__init__(content_type="application/xml",
                         content=content,
                         *args,
                         **kwargs
                         )

    def __eq__(self, __value: object) -> bool:
        return self.status_code == __value.status_code and self.message == __value.message and self.locator == __value.locator

    def get_locator(self):
        return self.locator

    def get_message(self):
        return self.message

    @property
    def exception_xml(self) -> _Element:
        builder = XSDSkeletonBuilder(
            (self.service_type, "Exception", self.service_version)
        )

        report_attributes = {
            "version": self.service_version,
        }

        # Build attributes dict only with non-empty values
        child_attributes = {
            "code": self.code,
            "locator": self.get_locator(),
            "_text": self.get_message()
        }
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
    code = "IvalidParameterValue"


class OperationNotSupportedException(OGCServiceException):
    code = "OperationNotSupported"
    message = "No such operation"

    def get_locator(self):
        query_parameters = {
            k.lower(): v for k, v in self.request.GET.items()}
        return query_parameters.get('request', None)

    def get_message(self):
        return f"No such operation: {self.get_locator()}"


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
