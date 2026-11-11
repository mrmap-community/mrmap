class InitialError(Exception):
    """Raised when a ogc client can't be initialized by a given capabilities document"""
    pass


class RedirectChainError(Exception):
    """Raised when the redirects of the remote service do not lead to an answer of the endpoint

    The message names the requested URL and the target of the last redirect, so an operator
    can tell a provider which refuses MrMap from an endpoint which redirects back at itself
    (#1100).

    Deliberately no ``requests`` RequestException: a redirect chain is decided by the endpoint
    and answers identically on every retry, so it must not be listed in the
    ``autoretry_for`` of a harvest and walk its hops again for each of them.
    """
    pass


class MissingQueryParam(Exception):
    """ Base class for missing query parameter errors. """
    pass


class MissingServiceParam(MissingQueryParam):
    """Raised when the "SERVICE" query param is missed"""

    def __init__(self, msg="'SERVICE' query parameter was missed", *args, **kwargs):
        super().__init__(msg, *args, **kwargs)


class MissingBboxParam(MissingQueryParam):
    """Raised when the "BBOX" query param is missed"""

    def __init__(self, msg="'BBOX' query parameter was missed", *args, **kwargs):
        super().__init__(msg, *args, **kwargs)


class MissingCrsParam(MissingQueryParam):
    """Raised when the coordinate reference system (SRS, CRS, srsName) query param is missed"""

    def __init__(self, msg="'SRS', 'CRS' or 'srsName' query parameter was missed", *args, **kwargs):
        super().__init__(msg, *args, **kwargs)


class InvalidQueryParam(Exception):
    """ Base class for query parameters which are there but carry no readable value.

    The ``param`` names the parameter the exception report of the endpoint has to
    point at.
    """

    param = ""


class InvalidFilterParam(InvalidQueryParam):
    """Raised when the "FILTER" query param carries no parsable filter document

    The KVP encoding hands a filter over as escaped XML within a query parameter
    (OGC 10-166r4, Table 11). A parameter which is not a document is a faulty
    parameter of the request and says so, instead of raising the parser's
    XMLSyntaxError up to the endpoint's catch-all (#1155).
    """

    param = "FILTER"

    def __init__(self, msg="'FILTER' query parameter is no parsable document", *args, **kwargs):
        super().__init__(msg, *args, **kwargs)


class InvalidPagingParam(InvalidQueryParam):
    """Raised when a paging query param (COUNT, MAXFEATURES, startIndex) is no integer

    The parameters of the KVP binding arrive as text, so a value which is no
    number is a faulty parameter of the request and not a failure of the proxy.
    """

    def __init__(self, param, msg=None, *args, **kwargs):
        self.param = param
        super().__init__(
            msg or f"'{param}' query parameter is no integer", *args, **kwargs)
