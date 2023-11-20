

from ows_lib.xml_mapper.exceptions import OGCServiceException


class InvalidQuery(OGCServiceException):
    code = "InvalidQuery"
