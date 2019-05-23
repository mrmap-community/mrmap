"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 08.05.19

"""
import os

import datetime
import pytz
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone
from django.contrib import messages
from django.http import HttpRequest
from django.shortcuts import redirect, render, get_object_or_404

from MapSkinner.decorator import check_access
from MapSkinner.responses import DefaultContext
from MapSkinner.settings import SESSION_EXPIRATION, USER_ACTIVATION_TIME_WINDOW
from MapSkinner.utils import sha256
from structure.forms import LoginForm, RegistrationForm
from structure.helper import user_helper
from django.utils.translation import gettext_lazy as _

from structure.models import User, UserActivation


def login(request: HttpRequest):
    """ Login landing page

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
        if not user.is_active:
            messages.add_message(request, messages.INFO, _("Your account is currently not activated"))
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
    context = DefaultContext(request, params)
    return render(request=request, template_name=template, context=context.get_context())


def activate_user(request: HttpRequest, activation_hash: str):
    """ Checks the activation hash and activates the user's account if possible

    Args:
        request (HttpRequest): The incoming request
        activation_hash (str): The activation hash from the url
    Returns:
         A rendered view
    """
    template = "user_activation.html"

    try:
        user_activation = UserActivation.objects.get(activation_hash=activation_hash)
    except ObjectDoesNotExist:
        messages.add_message(request, messages.ERROR, _("Your activation link was invalid. Please contact an administrator."))
        return redirect("login")

    activation_until = user_activation.activation_until
    if activation_until < timezone.now():
        # the activation was confirmed too late!
        messages.add_message(request, messages.ERROR, _("Your activation link was outdated. The account couldn't be activated. Please register again."))
        return redirect("login")

    user = user_activation.user
    user.is_active = True
    user.save()
    user_activation.delete()
    params = {
        "user": user,
    }
    context = DefaultContext(request, params)
    return render(request=request, template_name=template, context=context.get_context())


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

@transaction.atomic
def register(request: HttpRequest):
    """

    Args:
        request (HttpRequest): The incoming request
    Returns:
         A view
    """
    template = "user_registration.html"
    form = RegistrationForm()
    params = {
        "form": form,
        "registration_article": _("Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet. Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet. "),
        "registration_title": _("Sign up"),
    }
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            cleaned_data = form.cleaned_data
            password = cleaned_data.get("password")
            password_check = cleaned_data.get("password_check")
            if password != password_check:
                messages.add_message(request, messages.ERROR, _("Passwords did not match!"))
            else:
                # create new user and send mail
                user = User()
                user.username = cleaned_data.get("username")
                user.salt = str(os.urandom(25).hex())
                user.password = make_password(password, salt=user.salt)
                user.person_name = cleaned_data.get("first_name") + " " + cleaned_data.get("last_name")
                user.facsimile = cleaned_data.get("facsimile")
                user.phone = cleaned_data.get("phone")
                user.email = cleaned_data.get("email")
                user.city = cleaned_data.get("city")
                user.address = cleaned_data.get("address")
                user.postal_code = cleaned_data.get("postal_code")
                user.confirmed_dsgvo = timezone.now()
                user.confirmed_newsletter = cleaned_data.get("newsletter")
                user.confirmed_survey = cleaned_data.get("survey")
                user.is_active = False
                user.save()
                # create user_activation object to improve checking against activation link
                user_activation = UserActivation()
                user_activation.user = user
                user_activation.activation_until = timezone.now() + datetime.timedelta(hours=USER_ACTIVATION_TIME_WINDOW)
                user_activation.activation_hash = sha256(user.username + user.salt + str(user_activation.activation_until))
                user_activation.save()

                messages.add_message(request, messages.SUCCESS, _("An activation link for your account was sent. Please check your e-mails!"))
                return redirect("login")
        else:
            params["not_valid"] = True
            for error_key, error_val in form.errors.items():
                for e in error_val.data:
                    messages.add_message(request, messages.ERROR, e.message)
    context = DefaultContext(request, params)
    return render(request=request, template_name=template, context=context.get_context())
