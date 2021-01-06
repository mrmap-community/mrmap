"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 08.05.19

"""
import json
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse
from django.shortcuts import get_object_or_404

from MrMap.messages import NO_PERMISSION, SERVICE_NOT_FOUND, RESOURCE_IS_OWNED_BY_ANOTHER_GROUP, \
    REQUESTING_USER_IS_NOT_MEMBER_OF_THE_GROUP, REQUESTING_USER_IS_NOT_MEMBER_OF_THE_ORGANIZATION
from MrMap.utils import get_dict_value_insensitive
from service.models import Metadata, ProxyLog
from service.settings import NONE_UUID
from structure.models import MrMapGroup, Organization
from users.helper import user_helper


def permission_required(perm, login_url=None):
    """
    Decorator for views that checks whether a user has a particular permission
    enabled, redirecting to the log-in page if necessary.
    If the raise_exception parameter is given the PermissionDenied exception
    is raised.
    """
    def check_perms(request, user):
        if isinstance(perm, str):
            perms = (perm,)
        else:
            perms = perm
        # First check if the user has the permission (even anon users)
        if user.has_perms(perms):
            return True
        else:
            messages.add_message(request, messages.ERROR, NO_PERMISSION)
        # As the last resort, show the login form
        return False
    return user_passes_test(check_perms, login_url=login_url)


def ownership_required(klass, id_name: str, login_url=None):
    """ Checks whether the user is owner of the resource by groupmemberships

    Args:
        klass: the class object which will be requested
        id_name: name of the id used in the kwargs
        login_url: the url we redirect to if the check fails
    Returns:
        The function
    """
    def check_ownership(request, user, **kwargs):
        resource = get_object_or_404(klass, id=kwargs.get(id_name), )
        user_groups = user.get_groups()

        if isinstance(resource, MrMapGroup):
            if resource in user_groups:
                return True
            else:
                messages.add_message(request, messages.ERROR, REQUESTING_USER_IS_NOT_MEMBER_OF_THE_GROUP)
        elif isinstance(resource, Organization):
            if user.organization == resource or user == resource.created_by:
                return True
            else:
                messages.add_message(request, messages.ERROR, REQUESTING_USER_IS_NOT_MEMBER_OF_THE_ORGANIZATION)
        else:
            if resource.created_by in user_groups:
                return True
            else:
                messages.add_message(request, messages.ERROR, RESOURCE_IS_OWNED_BY_ANOTHER_GROUP)
        return False

    return user_passes_test(check_ownership, login_url=login_url)


def log_proxy(function):
    """ Checks whether the metadata has a logging proxy configuration and adds another log record

    Args:
        function (Function): The wrapped function
    Returns:
        The function
    """
    def wrap(request, *args, **kwargs):
        user = user_helper.get_user(request=request)
        try:
            md = Metadata.objects.get(id=kwargs["metadata_id"])
        except ObjectDoesNotExist:
            return HttpResponse(status=404, content=SERVICE_NOT_FOUND)

        logged_user = None
        if user.is_authenticated:
            logged_user = user

        uri = request.path
        post_body = {}
        if request.method.lower() == "post":
            post_body = request.POST.dict()
        elif request.method.lower() == "get":
            uri += "?" + request.environ.get("QUERY_STRING")
        post_body = json.dumps(post_body)

        proxy_log = None
        if md.use_proxy_uri and md.log_proxy_access:
            proxy_log = ProxyLog(
                metadata=md,
                uri=uri,
                operation=get_dict_value_insensitive(request.GET.dict(), "request"),
                post_body=post_body,
                user=logged_user
            )
            proxy_log.save()
        return function(request=request, proxy_log=proxy_log, *args, **kwargs)

    wrap.__doc__ = function.__doc__
    wrap.__name__ = function.__name__
    return wrap


def resolve_metadata_public_id(function):
    def wrap(request, *args, **kwargs):
        possible_parameter_names = [
            "metadata_id",  # regular usage
            "pk",  # usage in DjangoRestFramework (API)
        ]
        found_params = [p for p in possible_parameter_names if p in kwargs]
        for param in found_params:
            try:
                uuid.UUID(kwargs[param])
                # We could cast the id to an UUID. This means the regular integer has been provided. Nothing to do here
            except ValueError:
                # We could not create a uuid from the given metadata_id -> it might be a public_id
                try:
                    md = Metadata.objects.get(public_id=kwargs[param])
                    kwargs[param] = str(md.id)
                except ObjectDoesNotExist:
                    # No metadata could be found, we provide the empty uuid
                    kwargs[param] = NONE_UUID
        return function(request=request, *args, **kwargs)

    wrap.__doc__ = function.__doc__
    wrap.__name__ = function.__name__
    return wrap
