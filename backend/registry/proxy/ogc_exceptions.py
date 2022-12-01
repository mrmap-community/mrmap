from django.http import HttpResponse
from ows_lib.models.ogc_request import OGCRequest


class OGCServiceException(HttpResponse):
    status_code = 200
    message = None
    locator = None

    def __init__(self, ogc_request: OGCRequest, message: str = None, locator: str = None, *args, **kwargs):
        if message:
            self.message = message
        if locator:
            self.locator = locator
        self.ogc_request = ogc_request
        super().__init__(content_type="application/xml",
                         content=self.get_exception_string(), *args, **kwargs)

    def get_locator(self):
        return self.locator

    def get_locator_string(self):
        return f'locator="{self.get_locator()}"'

    def get_message(self):
        return self.message

    def get_exception_string(self):
        # TODO: dynamic version
        return \
            '<?xml version="1.0" encoding="UTF-8"?>'\
            f'<ServiceExceptionReport version="{self.ogc_request.service_version}" xmlns="http://www.opengis.net/ogc" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.opengis.net/ogc">'\
            f'<ServiceException code="{self.code}" {self.get_locator_string() if self.get_locator() else ""}>'\
            f'{self.get_message()}'\
            '</ServiceException>'\
            '</ServiceExceptionReport>'


class DisabledException(OGCServiceException):
    code = "Disabled"
    message = "The requested service is temporaly disabled."


class ForbiddenException(OGCServiceException):
    code = "Forbidden"
    message = "The requesting user has no permissions to access the service."


class MissingParameterException(OGCServiceException):
    code = "MissingParameter"


class MissingRequestParameterException(MissingParameterException):
    locator = "request"
    message = "Could not determine request method from http request."


class MissingVersionParameterException(MissingParameterException):
    locator = "version"
    message = "Could not determine version for the requested service."


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
