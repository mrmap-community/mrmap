

from registry.ows_lib.response.exceptions import OGCServiceException


class InvalidQuery(OGCServiceException):
    code = "InvalidQuery"


class NotImplemented(OGCServiceException):
    code = "NotImplemented"


class NotSupported(OGCServiceException):
    code = "NotSupported"
