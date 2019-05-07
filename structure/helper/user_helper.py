"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 07.05.19

"""
from django.contrib.auth.hashers import check_password
from django.core.exceptions import ObjectDoesNotExist

from structure.models import User


def get_user(username: str):
    """ Returns the user object matching to the given string

    Args:
        username: The username of the user
    Returns:
        Returns the user object if found, None otherwise
    """
    try:
        user = User.objects.get(username=username)
        return user
    except ObjectDoesNotExist:
        return None


def is_password_valid(user: User, password: str):
    """ Checks if the incoming password is valid for the user

    Args:
        user: The user object which needs to be checked against
        password: The password that might match to the user
    Returns:
         True or False
    """
    return check_password(password, user.password)