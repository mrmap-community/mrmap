

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
    it is. #912 read this as the trace of a one-time storage incident; #1150
    measured the losses spread uniformly over the whole corpus, so the
    ``check_xml_backups`` management command is the operator's standing answer
    to the damage itself, while this report stays the client-facing refusal of
    the page which cannot be served.

    The report names the record so the client and the operator know which one
    it is about (#912) -- and names nothing else: the detail of the failed
    read, which carries the absolute path of the media storage, is logged
    server-side and never reaches this anonymous-facing document (#1150).

    The status is 500, not the 400 of the request-refusing reports: the
    request is well-formed and the storage owes the answer (#1150). A client
    which treats 4xx as "do not retry this request again" is pointed at a
    refusal that may well be transient; 5xx tells it the truth.
    """
    code = "NoApplicableCode"
    status_code = 500
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
