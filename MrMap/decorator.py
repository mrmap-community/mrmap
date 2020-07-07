"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 08.05.19

"""
import json

from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse

from MrMap.messages import NO_PERMISSION, SERVICE_NOT_FOUND, RESOURCE_IS_OWNED_BY_ANOTHER_GROUP, \
    REQUESTING_USER_IS_NOT_MEMBER_OF_THE_GROUP, REQUESTING_USER_IS_NOT_MEMBER_OF_THE_ORGANIZATION
from MrMap.utils import get_dict_value_insensitive
from service.models import Metadata, ProxyLog, Resource
from structure.models import Permission, MrMapUser, MrMapGroup, Organization
from users.helper import user_helper


def check_permission(permission_needed: Permission):
    """ Checks whether the user has the required permission for the requested action

    Args:
        permission_needed (Permission): The permission object that defines which permissions are needed
    Returns:
         The function
    """
    def method_wrap(function):
        def wrap(request, *args, **kwargs):
            user = user_helper.get_user(request)
            user_permissions = user.get_permissions()
            perm_needed = permission_needed.get_permission_list()
            for perm in perm_needed:
                if perm not in user_permissions:
                    messages.add_message(request, messages.ERROR, NO_PERMISSION)
                    return redirect(request.META.get("HTTP_REFERER") if "HTTP_REFERER" in request.META else reverse('home'))
            return function(request=request, *args, **kwargs)

        wrap.__doc__ = function.__doc__
        wrap.__name__ = function.__name__
        return wrap
    return method_wrap


def check_ownership(klass, id_name: str):
    """ Checks whether the user is owner of the resource by groupmemberships

    Args:
        klass: the class object which will be requested
        id_name: name of the id used in the kwargs
    Returns:
        The function
    """

    def method_wrap(function):
        def wrap(request, *args, **kwargs):
            resource = get_object_or_404(klass, id=kwargs.get(id_name),)

            user = user_helper.get_user(request=request)
            user_groups = user.get_groups()

            if isinstance(resource, MrMapGroup):
                if resource in user_groups:
                    return function(request=request, *args, **kwargs)
                else:
                    messages.add_message(request, messages.ERROR, REQUESTING_USER_IS_NOT_MEMBER_OF_THE_GROUP)

            elif isinstance(resource, Organization):
                if user.organization == resource or user == resource.created_by:
                    return function(request=request, *args, **kwargs)
                else:
                    messages.add_message(request, messages.ERROR, REQUESTING_USER_IS_NOT_MEMBER_OF_THE_ORGANIZATION)

            else:
                if resource.created_by in user_groups:
                    return function(request=request, *args, **kwargs)
                else:
                    messages.add_message(request, messages.ERROR, RESOURCE_IS_OWNED_BY_ANOTHER_GROUP)
            return HttpResponseRedirect(
                request.META.get("HTTP_REFERER") if "HTTP_REFERER" in request.META else reverse('home'),
                status=303)

        wrap.__doc__ = function.__doc__
        wrap.__name__ = function.__name__
        return wrap
    return method_wrap


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
        if 'metadata_id' in kwargs:
            try:
                int(kwargs["metadata_id"])
                # We could cast the id to an integer. This means a public integer has been provided. We need to redirect
                # to the entry using the uuid
                try:
                    md = Metadata.objects.get(public_id=kwargs["metadata_id"])
                    request.path = request.path.replace("/{}".format(kwargs["metadata_id"]), "/{}".format(str(md.id)))
                    return redirect(request.build_absolute_uri())
                except ObjectDoesNotExist:
                    # This means there was an integer given but it can not be resolved to any public_id!
                    pass
            except ValueError:
                pass
        return function(request=request, *args, **kwargs)

    wrap.__doc__ = function.__doc__
    wrap.__name__ = function.__name__
    return wrap