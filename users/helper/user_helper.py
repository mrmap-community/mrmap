"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 07.05.19

"""
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest

from MapSkinner.settings import SESSION_EXPIRATION
from structure.models import Group, User, GroupActivity


def get_user(request: HttpRequest=None, username: str=None, user_id: int=None):
    """ Returns the user object matching to the given string

    Args:
        request (HttpRequest): An incoming request
        user_id (int): The user id
        username (str): The username of the user
    Returns:
        Returns the user object if found, None otherwise
    """
    try:
        if username is not None:
            user = User.objects.get(username=username)
        elif user_id is not None:
            user = User.objects.get(id=user_id)
        elif request is not None:
            user = User.objects.get(id=request.session.get("user_id"))
        else:
            return None
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
        # in valid range
        return False
    else:
        return True


def create_group_activity(group: Group, user: User, msg, metadata_title: str):
    """ Creates a group activity record for logging group actions.

    This covers basically changes on metadata aka services

    Args:
        group (Group): The metadata related group
        user (User): The performing user
        msg (str): The description
        metadata_title (str): The related metadata's title
    Returns:
        nothing
    """
    group_activity = GroupActivity()
    group_activity.metadata = metadata_title
    group_activity.user = user
    group_activity.group = group
    group_activity.description = msg
    group_activity.save()
