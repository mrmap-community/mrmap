

from registry.ows_lib.response.exceptions import OGCServiceException


class InvalidQuery(OGCServiceException):
    code = "InvalidQuery"


class NotImplemented(OGCServiceException):
    code = "NotImplemented"


class NotSupported(OGCServiceException):
    code = "NotSupported"


class DocumentUnavailable(OGCServiceException):
    """The stored document of a matched record cannot be served.

    NoApplicableCode is the code OGC 07-006r1, Table 10 leaves for a failure
    the request itself is not to blame for: the xml backup file of a record is
    gone from the media storage, or its content cannot be read as the document
    it is (lost files of a storage incident, quota, a failing disk). The report
    names the record so the client and the operator know which one it is about
    (#912); before, the FileNotFoundError of such a record killed the whole
    response with a raw HTTP 500.
    """
    code = "NoApplicableCode"
    message = "The stored document of a matched record cannot be served."


class MissingIdParameterException(OGCServiceException):
    """A ``GetRecordById`` which names no record identifier.

    Table 67 of OGC 07-006r1 makes the ``Id`` parameter of the operation One
    (Mandatory), and unlike the paging parameters of a ``GetRecords`` it
    carries no default this endpoint could fall back to -- a request which
    names no identifier asks for nothing and is refused with the
    ``MissingParameterValue`` of OWS Common (Table 8), locating the parameter
    it misses (#909; the request used to be answered with an empty response
    document).

    The code is the one Table 8 names for a missing mandatory parameter. The
    refusals dispatch answers for the parameters it reads itself
    (``request``, ``service``) carry the established ``MissingParameter`` code
    of :mod:`registry.ows_lib.response.exceptions`; the audit of #909
    prescribes the normative code for the parameter of the operation, and this
    is where the two meet: a refusal of a parameter only a handler reads.
    """
    code = "MissingParameterValue"
    locator = "Id"
    message = "The Id parameter is mandatory for GetRecordById."
