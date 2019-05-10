"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 08.05.19

"""
import pytz
from django.utils import timezone
from django.contrib import messages
from django.http import HttpRequest
from django.shortcuts import redirect, render

from MapSkinner.decorator import check_access
from MapSkinner.settings import SESSION_EXPIRATION
from structure.forms import LoginForm
from structure.helper import user_helper
from django.utils.translation import gettext_lazy as _

from structure.models import User


def login(request: HttpRequest):
    """ Logs the structure in and redirects to overview

    Args:
        request (HttpRequest): The incoming request
    Returns:
         A view
    """
    template = "login.html"
    login_form = LoginForm(request.POST)
    if login_form.is_valid():
        username = login_form.cleaned_data.get("username")
        password = login_form.cleaned_data.get("password")
        user = user_helper.get_user(username=username)
        if user is None:
            messages.add_message(request, messages.ERROR, _("Username or password incorrect"))
            return redirect("login")
        if not user_helper.is_password_valid(user, password):
            messages.add_message(request, messages.ERROR, _("Username or password incorrect"))
            return redirect("login")
        user.last_login = timezone.now()
        user.logged_in = True
        user.save()
        request.session["user_id"] = user.id
        request.session.set_expiry(SESSION_EXPIRATION)
        return redirect('service:index')
    login_form = LoginForm()
    params = {
        "login_form": login_form,
        "login_article_title": _("Sign in for Mr. Map"),
        "login_article": _("Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet. Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet. ")
    }
    return render(request=request, template_name=template, context=params)

@check_access
def logout(request: HttpRequest, user: User):
    """ Logs the structure out and redirects to login view

    Args:
        request (HttpRequest): The incoming request
    Returns:
         A view
    """
    user.logged_in = False
    user.save()
    messages.add_message(request, messages.SUCCESS, _("Successfully logged out!"))
    return redirect('login')