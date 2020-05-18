from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _

from service.helper import service_helper
from service.helper.enums import OGCServiceEnum

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


def _get_request_uri_has_no_request_parameter(value):
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
    url_dict = service_helper.split_service_uri(value)
    # currently supported version for wms 1.3.0, 1.1.1, 1.1.0, 1.0.0
    # currently supported version for wfs 2.0.2, 2.0.0, 1.1.0, 1.0.0
    supported_wms_versions = ['1.3.0', '1.1.1', '1.1.0', '1.0.0']
    supported_wfs_versions = ['2.0.2', '2.0.0', '1.1.0', '1.0.0']

    if "version" in url_dict and url_dict["version"] is not None:
        if "service" in url_dict or url_dict["service"] is not None:
            if url_dict["service"] == OGCServiceEnum.WMS:
                service_type = OGCServiceEnum.WMS.value
                supported_versions = supported_wms_versions
            elif url_dict["service"] == OGCServiceEnum.WFS:
                service_type = OGCServiceEnum.WFS.value
                supported_versions = supported_wfs_versions
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
    url_dict = service_helper.split_service_uri(value)

    if "service" not in url_dict or url_dict["service"] is None:
        return ValidationError(
            _('The given uri is not valid cause there is no service parameter.')
        )


def validate_get_request_uri(value):

    validation_errors = []

    return_value = _get_request_uri_has_no_request_parameter(value)
    if isinstance(return_value, ValidationError):
        validation_errors.append(return_value)

    return_value = _get_request_uri_has_no_service_parameter(value)
    if isinstance(return_value, ValidationError):
        validation_errors.append(return_value)

    return_value = _get_request_uri_has_no_version_parameter(value)
    if isinstance(return_value, ValidationError):
        validation_errors.append(return_value)

    if len(validation_errors) > 0:
        raise ValidationError(validation_errors)
