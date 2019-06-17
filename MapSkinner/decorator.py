"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 08.05.19

"""
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _

from MapSkinner.responses import BackendAjaxResponse
from MapSkinner.settings import ROOT_URL
from users.helper import user_helper


def check_access(function):
    def wrap(request, *args, **kwargs):
        if user_helper.is_session_expired(request):
            messages.add_message(request, messages.INFO, _("Session timeout. You have been logged out."))
            if request.environ.get("HTTP_X_REQUESTED_WITH", None) is not None:
                # this is an ajax call -> redirect user to login page if the session isn't valid anymore
                return BackendAjaxResponse(html="", redirect=ROOT_URL).get_response()
            else:
                return redirect("login")
        user = user_helper.get_user(user_id=request.session.get("user_id"))
        if user is None:
            messages.add_message(request, messages.ERROR, _("You have been logged out."))
            return redirect("login")
        return function(request=request, user=user, *args, **kwargs)

    wrap.__doc__ = function.__doc__
    wrap.__name__ = function.__name__
    return wrap