"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 07.05.19

"""
from django.contrib.auth.hashers import check_password
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest

from MapSkinner.settings import SESSION_EXPIRATION
from service.models import Metadata
from structure.models import Permission, Group, User


def get_user(username: str=None, user_id: int=None):
    """ Returns the user object matching to the given string

    Args:
        username: The username of the user
    Returns:
        Returns the user object if found, None otherwise
    """
    try:
        if username is not None:
            user = User.objects.get(username=username)
        elif user_id is not None:
            user = User.objects.get(id=user_id)
        return user
    except ObjectDoesNotExist:
        return None


def is_session_expired(request: HttpRequest):
    """ Checks whether the current session is expired or not

    Args:
        request: The request
    Returns:
         Returns true if expired, false otherwise
    """
    age = request.session.get_expiry_age()
    if age > 0 and age <= SESSION_EXPIRATION:
        # expired
        return False
    else:
        return True
