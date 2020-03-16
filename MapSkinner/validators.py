from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _

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
