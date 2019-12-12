"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 08.05.19

"""
from django.contrib import messages
from django.shortcuts import redirect

from MapSkinner.messages import SESSION_TIMEOUT, NO_PERMISSION, LOGOUT_FORCED
from MapSkinner.responses import BackendAjaxResponse
from MapSkinner.settings import ROOT_URL
from structure.models import Permission
from users.helper import user_helper


def check_session(function):
    """ Checks whether the user's session is valid or not

    Args:
        function: The decorated function
    Returns:
         The function
    """
    def wrap(request, *args, **kwargs):
        if user_helper.is_session_expired(request):
            _next = request.path

            # make sure the logout path will not be stored as a _next value
            logout_path = redirect("logout")._headers.get("location", [None, "/logout"])[1]
            if logout_path == request.path:
                _next = None

            request.session["next"] = _next
            messages.add_message(request, messages.INFO, SESSION_TIMEOUT)

            if request.environ.get("HTTP_X_REQUESTED_WITH", None) is not None:
                # this is an ajax call -> redirect user to login page if the session isn't valid anymore
                return BackendAjaxResponse(html="", redirect=ROOT_URL).get_response()
            else:
                return redirect("login")

        user = user_helper.get_user(user_id=request.session.get("user_id"))

        if user is None:
            if request.session.get("user_id", None) is not None:
                del request.session["user_id"]
            messages.add_message(request, messages.ERROR, LOGOUT_FORCED)

            return redirect("login")
        return function(request=request, user=user, *args, **kwargs)

    wrap.__doc__ = function.__doc__
    wrap.__name__ = function.__name__
    return wrap


def check_permission(permission_needed: Permission):
    """ Checks whether the user has the required permission for the requested action

    Args:
        permission_needed (Permission): The permission object that defines which permissions are needed
    Returns:
         The function
    """
    def method_wrap(function):
        def wrap(request, *args, **kwargs):
            user = user_helper.get_user(user_id=request.session.get("user_id"))
            user_permissions = user.get_permissions()
            perm_needed = permission_needed.get_permission_list()
            for perm in perm_needed:
                if perm not in user_permissions:
                    messages.add_message(request, messages.ERROR, NO_PERMISSION)
                    return redirect(request.META.get("HTTP_REFERER"))
            return function(request=request, *args, **kwargs)

        wrap.__doc__ = function.__doc__
        wrap.__name__ = function.__name__
        return wrap
    return method_wrap
