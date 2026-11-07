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
