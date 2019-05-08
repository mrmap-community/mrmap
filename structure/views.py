import datetime
from django.contrib import messages
from django.http import HttpRequest
from django.shortcuts import render, redirect
from django.utils.translation import gettext_lazy as _

from MapSkinner.decorator import check_access
from MapSkinner.settings import SESSION_EXPIRATION
from structure.forms import LoginForm
from structure.models import Permission, User, Group
from .helper import user_helper


@check_access
def index(request: HttpRequest, user: User):
    """ Renders an overview of all groups

    Args:
        request (HttpRequest): The incoming request
        user (User):
    Returns:
         A view
    """
    template = "index_structure.html"
    user_groups = user.groups.all()
    groups = []
    for user_group in user_groups:
        groups.append(user_group)
        groups.extend(Group.objects.filter(
            parent=user_group
        ))
    params = {
        "permissions": user_helper.get_permissions(user),
        "groups": groups,
    }
    return render(request=request, template_name=template, context=params)


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
            return redirect("structure:login")
        if not user_helper.is_password_valid(user, password):
            messages.add_message(request, messages.ERROR, _("Username or password incorrect"))
            return redirect("structure:login")
        user.last_login = datetime.datetime.now()
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
def logout(request: HttpRequest, user:User):
    """ Logs the structure out and redirects to login view

    Args:
        request (HttpRequest): The incoming request
    Returns:
         A view
    """
    user.logged_in = False
    user.save()
    messages.add_message(request, messages.SUCCESS, _("Successfully logged out!"))
    return redirect('structure:login')
