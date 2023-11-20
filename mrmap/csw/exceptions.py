

from ows_lib.xml_mapper.exceptions import OGCServiceException


class InvalidQuery(OGCServiceException):
    code = "InvalidQuery"


class NotImplemented(OGCServiceException):
    code = "NotImplemented"


class NotSupported(OGCServiceException):
    code = "NotSupported"
