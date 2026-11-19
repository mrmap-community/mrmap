from urllib.parse import parse_qs, urlparse

from django.contrib.gis.geos import GEOSGeometry
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from registry.enums.service import OGCServiceEnum


def _get_request_uri_has_no_request_parameter(value):
    parsed_url = urlparse(value)
    query_params = parse_qs(parsed_url.query)
    query_params = {k.lower(): v for k, v in query_params.items()}
    if "request" in query_params and query_params["request"][0] is not None:
        if query_params["request"][0].lower() != "getcapabilities":
            # not allowed!
            return ValidationError(
                _("The given requested method is not GetCapabilities."),
            )
    else:
        return ValidationError(
            _("The given uri is not valid cause there is no request parameter.")
        )


# currently supported version for wms 1.3.0, 1.1.1, 1.1.0, 1.0.0
# supported versions for wfs are only 2.0.2 and 2.0.0: the mapper ships a
# capabilities config for 2.0.0 (#1210), which also maps a 2.0.2 document
# because both share the /wfs/2.0 namespace. A 1.x document carries the
# older namespace, maps to nothing and must be refused here, not as a
# crashed registration task.
# FUTURE: append all versions
SUPPORTED_WMS_VERSIONS = ["1.3.0", "1.1.1", "1.1.0", "1.0.0"]
SUPPORTED_WFS_VERSIONS = ["2.0.2", "2.0.0"]
SUPPORTED_CSW_VERSIONS = [
    "2.0.2",
]

#: the SERVICE spellings the validator answers for, each with the service
#: name and the versions Mr.Map ships a capabilities mapping for
_SUPPORTED_SERVICE_VERSIONS = {
    spelling: (service, versions)
    for service, versions in (
        (OGCServiceEnum.WMS.value, SUPPORTED_WMS_VERSIONS),
        (OGCServiceEnum.WFS.value, SUPPORTED_WFS_VERSIONS),
        (OGCServiceEnum.CSW.value, SUPPORTED_CSW_VERSIONS),
    )
    for spelling in (service.lower(), service.upper())
}


def _get_request_uri_has_no_version_parameter(value):
    parsed_url = urlparse(value)
    query_params = parse_qs(parsed_url.query)
    query_params = {k.lower(): v for k, v in query_params.items()}
    if "version" not in query_params or query_params["version"][0] is None:
        return ValidationError(
            _("The given uri is not valid cause there is no version parameter.")
        )

    if "service" in query_params or query_params["service"][0] is not None:
        supported = _SUPPORTED_SERVICE_VERSIONS.get(
            query_params["service"][0])
        if supported is None:
            return ValidationError(
                _("The given service typ is not supported from Mr. Map."),
            )

        service_type, supported_versions = supported
        version = query_params["version"][0]
        if version not in supported_versions:
            return ValidationError(
                _(
                    "The given {} version {} is not supported from Mr. Map.".format(
                        service_type, version
                    )
                ),
            )


def _get_request_uri_has_no_service_parameter(value):
    parsed_url = urlparse(value)
    query_params = parse_qs(parsed_url.query)
    query_params = {k.lower(): v for k, v in query_params.items()}
    if "service" not in query_params or query_params["service"][0] is None:
        return ValidationError(
            _("The given uri is not valid cause there is no service parameter.")
        )


def validate_get_capablities_uri(value):
    """Validates a GetRequest URI

    Args:
        value: The given value (an URL)
    Returns:

    """
    validation_errors = []

    validate_funcs = [
        _get_request_uri_has_no_request_parameter,
        _get_request_uri_has_no_service_parameter,
        _get_request_uri_has_no_version_parameter,
    ]

    for func in validate_funcs:
        val = func(value)
        if isinstance(val, ValidationError):
            validation_errors.append(val)

    if len(validation_errors) > 0:
        raise ValidationError(validation_errors)


def geometry_is_empty(geometry: GEOSGeometry):
    """Raise ValidationError on empty GEOSGeometry objects"""
    if geometry.empty:
        raise ValidationError(_("Empty geometry collections are not allowed."))


def geometry_type_is(*geometry_types: str):
    """Return a validator rejecting geometries of any other type.

    Args:
        geometry_types: the accepted geometry types, e.g. ``"MultiPolygon"``.
                        Compared like :attr:`GEOSGeometry.geom_type` answers it.

    A geometry column typed ``MULTIPOLYGON`` refuses every other type when the row is
    written. That refusal is a database error, so a client sending a ``Polygon`` would
    get a 500 for something the serializer can answer with a 400.
    """
    def validate_geometry_type(geometry: GEOSGeometry):
        if geometry.geom_type.upper() not in (t.upper() for t in geometry_types):
            raise ValidationError(
                _("The geometry must be of type %(expected)s, but is of type %(actual)s."),
                code="invalid_geometry_type",
                params={
                    "expected": " or ".join(geometry_types),
                    "actual": geometry.geom_type,
                },
            )

    return validate_geometry_type
