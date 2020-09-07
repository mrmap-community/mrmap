import string
import random


def _random_to_long_password():
    some_lower = ''.join(random.choice(string.ascii_lowercase) for i in range(100))
    some_upper = ''.join(random.choice(string.ascii_uppercase) for i in range(100))
    some_digit = ''.join(random.choice(string.digits) for i in range(100))
    return some_lower + some_upper + some_digit


def _random_to_long_username():
    return ''.join(random.choice(string.ascii_lowercase) for i in range(256))


def _x_chars(x: int = 1):
    return ''.join(random.choice(string.ascii_letters) for i in range(x))


def get_email_data():
    return {
        'valid': 'tester@example.com',
        'invalid_to_long': _x_chars(256) + '@example.com'
    }


def get_password_data():
    # Password must have at least one lowercase letter
    # Password must have at least one Uppercase letter
    # Password must have at least one digit
    # Password must have at least nine characters
    # contains in following mismatching passwords:
    return {
        'valid': "MySuperStrongPassword!123.",
        'valid_2': "MySuperStrongPassword!123",
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


def get_capabilitites_url():
    # currently supported version for wms 1.3.0, 1.1.1, 1.1.0, 1.0.0
    # currently supported version for wfs 2.0.2, 2.0.0, 1.1.3, 1.1.0, 1.0.0
    return {
        "valid": "https://geo4.service24.rlp.de/wms/rp_lika_basis.fcgi?REQUEST=GetCapabilities&VERSION=1.1.1&SERVICE=WMS",
        "valid_wms_version_130": "http://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities",
        "valid_wms_version_111": "http://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetCapabilities",
        "valid_wms_version_110": "http://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=WMS&VERSION=1.1.0&REQUEST=GetCapabilities",
        "valid_wms_version_100": "http://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=WMS&VERSION=1.0.0&REQUEST=GetCapabilities",
        "valid_wfs_version_202": "http://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=WFS&VERSION=2.0.2&REQUEST=GetCapabilities",
        "valid_wfs_version_200": "http://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetCapabilities",
        "valid_wfs_version_113": "http://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=WFS&VERSION=1.1.3&REQUEST=GetCapabilities",
        "valid_wfs_version_110": "http://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=WFS&VERSION=1.1.0&REQUEST=GetCapabilities",
        "valid_wfs_version_100": "http://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=WFS&VERSION=1.0.0&REQUEST=GetCapabilities",
        "invalid_no_service": "http://geo5.service24.rlp.de/wms/karte_rp.fcgi?VERSION=1.3.0&REQUEST=GetCapabilities",
        "invalid_no_version": "http://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=WMS&REQUEST=GetCapabilities",
        "invalid_no_request": "http://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=WMS&VERSION=1.3.0",
        "invalid_version": "http://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=WMS&VERSION=9.4.0&REQUEST=GetCapabilities",
        "invalid_service_type": "http://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=ABC&VERSION=9.4.0&REQUEST=GetCapabilities",
    }
