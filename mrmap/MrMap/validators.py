import uuid
from requests import Request, Session

from urllib.parse import urlparse
from urllib.parse import parse_qs
from django.contrib.gis.geos import GEOSGeometry
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _

from resourceNew.enums.document import DocumentEnum
from resourceNew.enums.service import OGCServiceEnum


def check_uri_is_reachable(value):
    """ Performs a check on the URL.

    Returns whether it's reachable or not

    Args:
        value: The url to be checked
    Returns:
         reachable (bool)
         needs_authentication (bool)
         status_code (int)
    """
    request = Request(method="GET",
                      url=value)
    session = Session()
    response = session.send(request.prepare())
    if not response.ok:
        if response.status_code < 0:
            # Not even callable!
            msg_suffix = "URL could not be resolved to a server. Please check your input!"
        else:
            msg_suffix = "Status code was {}".format(response.status_code)
        return ValidationError(message="URL not valid! {}".format(msg_suffix))
    needs_authentication = response.status_code == 401
    return response.ok, needs_authentication, response.status_code


def _get_request_uri_has_no_request_parameter(value):
    parsed_url = urlparse(value)
    query_params = parse_qs(parsed_url.query)
    if "request" in query_params and query_params["request"][0] is not None:
        if query_params["request"][0].lower() != "getcapabilities":
            # not allowed!
            return ValidationError(
                _('The given requested method is not GetCapabilities.'),
            )
    else:
        return ValidationError(
            _('The given uri is not valid cause there is no request parameter.')
        )


def _get_request_uri_has_no_version_parameter(value):
    parsed_url = urlparse(value)
    query_params = parse_qs(parsed_url.query)
    # currently supported version for wms 1.3.0, 1.1.1, 1.1.0, 1.0.0
    # currently supported version for wfs 2.0.2, 2.0.0, 1.1.0, 1.0.0
    supported_wms_versions = ['1.3.0', '1.1.1', '1.1.0', '1.0.0']
    supported_wfs_versions = ['2.0.2', '2.0.0', '1.1.0', '1.0.0']
    # Todo: append all versions
    supported_csw_versions = ['2.0.2', ]

    if "version" in query_params and query_params["version"][0] is not None:
        if "service" in query_params or query_params["service"][0] is not None:
            if query_params["service"][0] == OGCServiceEnum.WMS:
                service_type = OGCServiceEnum.WMS.value
                supported_versions = supported_wms_versions
            elif query_params["service"][0] == OGCServiceEnum.WFS:
                service_type = OGCServiceEnum.WFS.value
                supported_versions = supported_wfs_versions
            elif query_params["service"][0] == OGCServiceEnum.CSW:
                service_type = OGCServiceEnum.CSW.value
                supported_versions = supported_csw_versions
            else:
                return ValidationError(
                    _('The given service typ is not supported from Mr. Map.'),
                )

            is_supported = False
            for version in supported_versions:
                if query_params["version"][0] == version:
                    is_supported = True

            if not is_supported:
                return ValidationError(
                    _('The given {} version {} is not supported from Mr. Map.'.format(service_type, query_params["version"][0])),
                )

    else:
        return ValidationError(
            _('The given uri is not valid cause there is no version parameter.')
        )


def _get_request_uri_has_no_service_parameter(value):
    parsed_url = urlparse(value)
    query_params = parse_qs(parsed_url.query)
    if "service" not in query_params or query_params["service"][0] is None:
        return ValidationError(
            _('The given uri is not valid cause there is no service parameter.')
        )


def validate_get_capablities_uri(value):
    """ Validates a GetRequest URI

    Args:
        value: The given value (an URL)
    Returns:

    """
    validation_errors = []

    validate_funcs = [
        _get_request_uri_has_no_request_parameter,
        _get_request_uri_has_no_service_parameter,
        _get_request_uri_has_no_version_parameter,
        check_uri_is_reachable,
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
