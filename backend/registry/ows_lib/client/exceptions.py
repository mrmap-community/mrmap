class InitialError(Exception):
    """Raised when a ogc client can't be initialized by a given capabilities document"""
    pass


class MissingQueryParam(Exception):
    """ Base class for missing query parameter errors. """
    pass


class MissingRequestParam(MissingQueryParam):
    """Raised when the "REQUEST" query param is missed"""

    def __init__(self, msg="'REQUEST' query parameter was missed", *args, **kwargs):
        super().__init__(msg, *args, **kwargs)


class MissingVersionParam(MissingQueryParam):
    """Raised when the "VERSION" query param is missed"""

    def __init__(self, msg="'VERSION' query parameter was missed", *args, **kwargs):
        super().__init__(msg, *args, **kwargs)


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
