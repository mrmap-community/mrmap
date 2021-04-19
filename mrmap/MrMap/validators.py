import uuid

from django.contrib.gis.geos import GEOSGeometry
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _

from service.helper import xml_helper
from service.helper.common_connector import CommonConnector
from service.helper.enums import OGCServiceEnum, DocumentEnum, MetadataEnum

password_has_lower_case_letter = RegexValidator(
    regex='[a-z]',
    message=_('Password must have at least one lowercase letter'),
    code='invalid_password'
)

password_has_upper_case_letter = RegexValidator(
    regex='[A-Z]',
    message=_('Password must have at least one Uppercase letter'),
    code='invalid_password'
)

password_has_digit = RegexValidator(
    regex='\d',
    message=_('Password must have at least one digit'),
    code='invalid_password'
)


def password_validate_has_lower_case_letter(value):
    return password_has_lower_case_letter(value)


def password_validate_has_upper_case_letter(value):
    return password_has_upper_case_letter(value)


def password_validate_has_digit(value):
    return password_has_digit(value)


PASSWORD_VALIDATORS = [password_validate_has_lower_case_letter,
                       password_validate_has_upper_case_letter,
                       password_validate_has_digit]

username_has_special_characters = RegexValidator(
    regex='[^A-Za-z0-9]',
    message=_('Special or non printable characters are not allowed'),
    code='invalid_username',
    inverse_match=True
)


def validate_username_has_special_characters(value):
    return username_has_special_characters(value)


USERNAME_VALIDATORS = [validate_username_has_special_characters]


def check_uri_is_reachable(value) -> (bool, bool, int):
    """ Performs a check on the URL.

    Returns whether it's reachable or not

    Args:
        value: The url to be checked
    Returns:
         reachable (bool)
         needs_authentication (bool)
         status_code (int)
    """
    connector = CommonConnector(
        url=value
    )
    is_reachable, status_code = connector.url_is_reachable()
    if not is_reachable:
        if status_code < 0:
            # Not even callable!
            msg_suffix = "URL could not be resolved to a server. Please check your input!"
        else:
            msg_suffix = "Status code was {}".format(status_code)
        return ValidationError(message="URL not valid! {}".format(msg_suffix))
    needs_authentication = status_code == 401
    return is_reachable, needs_authentication, status_code


def check_uri_provides_ogc_capabilities(value) -> ValidationError:
    """ Checks whether a proper XML OGC Capabilities document can be found at the given url.

    Args:
        value: The url parameter
    Returns:
         None|ValidationError: None if the checks are valid, ValidationError else
    """
    connector = CommonConnector(url=value)
    connector.load()
    if connector.status_code == 401:
        # This means the resource needs authentication to be called. At this point we can not check whether this is
        # a proper OGC capabilities or not. Skip this check.
        return None
    try:
        xml_response = xml_helper.parse_xml(connector.content)
        root_elem = xml_response.getroot()
        tag_text = root_elem.tag
        if "Capabilities" not in tag_text:
            return ValidationError(_("This is no capabilities document."))
    except AttributeError:
        # No xml found!
        return ValidationError(_("No XML found."))


def _get_request_uri_has_no_request_parameter(value):
    from service.helper import service_helper
    url_dict = service_helper.split_service_uri(value)

    if "request" in url_dict and url_dict["request"] is not None:
        if url_dict["request"].lower() != "getcapabilities":
            # not allowed!
            return ValidationError(
                _('The given requested method is not GetCapabilities.'),
            )
    else:
        return ValidationError(
            _('The given uri is not valid cause there is no request parameter.')
        )


def _get_request_uri_has_no_version_parameter(value):
    from service.helper import service_helper
    url_dict = service_helper.split_service_uri(value)
    # currently supported version for wms 1.3.0, 1.1.1, 1.1.0, 1.0.0
    # currently supported version for wfs 2.0.2, 2.0.0, 1.1.0, 1.0.0
    supported_wms_versions = ['1.3.0', '1.1.1', '1.1.0', '1.0.0']
    supported_wfs_versions = ['2.0.2', '2.0.0', '1.1.0', '1.0.0']
    # Todo: append all versions
    supported_csw_versions = ['2.0.2', ]

    if "version" in url_dict and url_dict["version"] is not None:
        if "service" in url_dict or url_dict["service"] is not None:
            if url_dict["service"] == OGCServiceEnum.WMS:
                service_type = OGCServiceEnum.WMS.value
                supported_versions = supported_wms_versions
            elif url_dict["service"] == OGCServiceEnum.WFS:
                service_type = OGCServiceEnum.WFS.value
                supported_versions = supported_wfs_versions
            elif url_dict["service"] == OGCServiceEnum.CSW:
                service_type = OGCServiceEnum.CSW.value
                supported_versions = supported_csw_versions
            else:
                return ValidationError(
                    _('The given service typ is not supported from Mr. Map.'),
                )

            is_supported = False
            for version in supported_versions:
                if url_dict["version"] == version:
                    is_supported = True

            if not is_supported:
                return ValidationError(
                    _('The given {} version {} is not supported from Mr. Map.'.format(service_type, url_dict["version"])),
                )

    else:
        return ValidationError(
            _('The given uri is not valid cause there is no version parameter.')
        )


def _get_request_uri_has_no_service_parameter(value):
    from service.helper import service_helper
    url_dict = service_helper.split_service_uri(value)

    if "service" not in url_dict or url_dict["service"] is None:
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
        check_uri_provides_ogc_capabilities,
        _get_request_uri_has_no_request_parameter,
        _get_request_uri_has_no_service_parameter,
        _get_request_uri_has_no_version_parameter,
        check_uri_is_reachable,
    ]

    skip_check_uri_provides_ogc_capabilities = False
    for func in validate_funcs:
        if skip_check_uri_provides_ogc_capabilities and func == check_uri_provides_ogc_capabilities:
            continue
        val = func(value)
        if isinstance(val, ValidationError):
            validation_errors.append(val)
            if func == check_uri_is_reachable:
                skip_check_uri_provides_ogc_capabilities = True

    if len(validation_errors) > 0:
        raise ValidationError(validation_errors)


def validate_document_enum_choices(value):
    return validate_choice(value, DocumentEnum.as_choices())


def validate_metadata_enum_choices(value):
    return validate_choice(value, MetadataEnum.as_choices())


def validate_choice(value, choices: list):
    """ Validates a given value against a choices list of tuples

    Args:
        value:
        choices:
    Returns:

    """
    choice_values = [choice[0] for choice in choices]
    if value not in choice_values:
        raise ValidationError(
            "Given value '{}' is not matching possible choices!".format(value)
        )


def not_uuid(value):
    """ Validates a given value to not be a uuid

    Args:
        value: The value
    Returns:

    """
    try:
        uuid.UUID(value)
        raise ValidationError("UUID not allowed!")
    except ValueError:
        # Could not create a uuid from string - all good!
        pass


def geometry_is_empty(geometry: GEOSGeometry):
    """Raise ValidationError on empty GEOSGeometry objects"""
    if geometry.empty:
        raise ValidationError(_("Empty geometry collections are not allowed."))
