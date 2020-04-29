"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 08.05.19

"""
import json

from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse

from MapSkinner.messages import NO_PERMISSION, SERVICE_NOT_FOUND, RESOURCE_IS_OWNED_BY_ANOTHER_GROUP
from service.models import Metadata, ProxyLog, Resource
from structure.models import Permission, MrMapUser, MrMapGroup
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
                if resource.created_by in user_groups:
                    return function(request=request, *args, **kwargs)
                
            messages.add_message(request, messages.ERROR, RESOURCE_IS_OWNED_BY_ANOTHER_GROUP)
            return redirect(request.META.get("HTTP_REFERER") if "HTTP_REFERER" in request.META else reverse('home'))

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
                post_body=post_body,
                user=logged_user
            )
            proxy_log.save()
        return function(request=request, proxy_log=proxy_log, *args, **kwargs)

    wrap.__doc__ = function.__doc__
    wrap.__name__ = function.__name__
    return wrap