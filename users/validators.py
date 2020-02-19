from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _


class HasLowerCaseLetter(RegexValidator):
    regex = '[a-z]',
    message = 'Password must have at least one lowercase letter',
    code = 'invalid_password'


