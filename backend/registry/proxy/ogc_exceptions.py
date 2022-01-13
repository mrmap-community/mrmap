from django.http import HttpResponse


class OGCServiceException(HttpResponse):
    status_code = 200
    locator = None
    message = None

    def __init__(self, *args, **kwargs):
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
            f'<ServiceExceptionReport version="1.3.0" xmlns="http://www.opengis.net/ogc" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.opengis.net/ogc">'\
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
