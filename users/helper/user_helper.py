"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 07.05.19

"""
import base64

from django.contrib.auth import authenticate
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest

from structure.models import MrMapGroup, MrMapUser, GroupActivity
from structure.settings import PUBLIC_GROUP_NAME


def get_user(request: HttpRequest=None, username: str=None, user_id: int=None):
    """ Returns the user object matching to the given string

    Args:
        request (HttpRequest): An incoming request
        user_id (int): The user id
        username (str): The username of the user
    Returns:
        Returns the user object if found, None otherwise
    """
    user = None
    try:
        if username is not None:
            user = MrMapUser.objects.get(username=username)
        elif user_id is not None:
            user = MrMapUser.objects.get(id=user_id)
        elif request is not None:
            try:
                user = request.user
            except ObjectDoesNotExist:
                pass
            if user.is_anonymous and not user.is_authenticated:
                # check for basic authentication
                auth_header = request.META.get('HTTP_AUTHORIZATION', '')
                auth_header = auth_header.split(" ")
                if len(auth_header) == 2:
                    credentials = auth_header[-1].encode("ascii")
                    username, password = base64.b64decode(credentials).decode("utf-8").split(":")

                    # Try to resolve the credentials to a user
                    user = authenticate(username=username, password=password)
                    if user.is_authenticated:
                        return user
                    return None
        else:
            return None
        return user
    except ObjectDoesNotExist:
        return None


def get_public_groups():
    """ Returns the public group, which is associated with the anonymousUser

    Returns:
         public_groups: QuerySet
    """
    public_groups = MrMapGroup.objects.filter(
        is_public_group=True
    )
    return public_groups


def create_group_activity(group: MrMapGroup, user: MrMapUser, msg, metadata_title: str):
    """ Creates a group activity record for logging group actions.

    This covers basically changes on metadata aka services

    Args:
        group (MrMapGroup): The metadata related group
        user (MrMapUser): The performing user
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
