"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 08.05.19

"""
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _

from structure.helper import user_helper


def check_access(function):
    def wrap(request, *args, **kwargs):
        if user_helper.is_session_expired(request):
            messages.add_message(request, messages.INFO, _("Session timeout"))
            return redirect("structure:login")
        user = user_helper.get_user(user_id=request.session.get("user_id"))
        if user is None:
            messages.add_message(request, messages.ERROR, _("You have been logged out."))
            return redirect("structure:login")
        return function(request=request, user=user, *args, **kwargs)

    wrap.__doc__ = function.__doc__
    wrap.__name__ = function.__name__
    return wrap