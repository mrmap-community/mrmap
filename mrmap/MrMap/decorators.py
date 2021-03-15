"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 08.05.19

"""
import json
import uuid

from django.contrib import messages
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
from functools import wraps
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.shortcuts import resolve_url


def user_passes_test(test_func, login_url=None, redirect_field_name=REDIRECT_FIELD_NAME):
    """
    Decorator for views that checks that the user passes the given test,
    redirecting to the log-in page if necessary. The test should be a callable
    that takes the user object and returns True if the user passes.
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if test_func(request, request.user):
                return view_func(request, *args, **kwargs)
            path = request.build_absolute_uri()
            resolved_login_url = resolve_url(login_url or settings.LOGIN_URL)
            # If the login url is the same scheme and net location then just
            # use the path as the "next" url.
            login_scheme, login_netloc = urlparse(resolved_login_url)[:2]
            current_scheme, current_netloc = urlparse(path)[:2]
            if ((not login_scheme or login_scheme == current_scheme) and
                    (not login_netloc or login_netloc == current_netloc)):
                path = request.get_full_path()
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(
                path, resolved_login_url, redirect_field_name)
        return _wrapped_view
    return decorator


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
        if user.has_permissions(perms):
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
    def check_ownership(request, user):
        if user.is_superuser:
            return True

        resource = get_object_or_404(klass, id=request.resolver_match.kwargs.get(id_name), )
        user_groups = user.get_groups

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
