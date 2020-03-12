import string
import random

from structure.models import Theme


def _random_to_long_password():
    some_lower = ''.join(random.choice(string.ascii_lowercase) for i in range(100))
    some_upper = ''.join(random.choice(string.ascii_uppercase) for i in range(100))
    some_digit = ''.join(random.choice(string.digits) for i in range(100))
    return some_lower + some_upper + some_digit


def _random_to_long_username():
    return ''.join(random.choice(string.ascii_lowercase) for i in range(256))


def get_password_data():
    # Password must have at least one lowercase letter
    # Password must have at least one Uppercase letter
    # Password must have at least one digit
    # Password must have at least nine characters
    # contains in following mismatching passwords:
    return {
        'valid': "MySuperStrongPassword!123.",
        'invalid_without_upper': "mystrongpassword1",
        'invalid_without_lower': "MYSTRONGPASSWORD1",
        'invalid_without_digit': "MyStrongP",
        'invalid_at_most_8': "MyStron1",
        'invalid_more_than_255': _random_to_long_password(),
    }


def get_contact_data():
    return {
        "username": get_username_data().get('valid'),
        "password": get_password_data().get('valid'),
        "password_check": get_password_data().get('valid'),
        "person_name": "New User",
        "first_name": "New",
        "last_name": "User",
        "facsimile": "01234566",
        "phone": "02463341",
        "email": "newuser@example.com",
        "city": "Testcity",
        "address": "Teststreet 2",
        "postal_code": "442211",
        "newsletter": True,
        "survey": True,
        "dsgvo": True,
        "captcha_0": "dummy",
        "captcha_1": "PASSED",
    }


def get_username_data():
    return {
        'valid': "NewUser",
        'invalid_has_special': "NewUser!",
        'invalid_has_non_printable': "\bNewUser\b",
        'invalid_more_than_255': _random_to_long_username(),
    }


def get_account_data():
    return {
        "username": get_username_data().get('valid'),
        "person_name": "New User",
        "facsimile": "01234566",
        "phone": "02463341",
        "email": "newuser@example.com",
        "city": "Testcity",
        "address": "Teststreet 2",
        "postal_code": "442211",
        "confirmed_newsletter": True,
        "confirmed_survey": True,
    }

