"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.05.19

"""

import datetime
import os

from django.contrib import messages
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.http import HttpRequest
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from MapSkinner.decorator import check_session
from MapSkinner.messages import FORM_INPUT_INVALID, ACCOUNT_UPDATE_SUCCESS, USERNAME_OR_PW_INVALID, \
    ACTIVATION_LINK_INVALID, ACCOUNT_NOT_ACTIVATED, PASSWORD_CHANGE_SUCCESS, PASSWORD_CHANGE_NO_MATCH, UNKNOWN_EMAIL, \
    LOGOUT_SUCCESS, PASSWORD_SENT, EMAIL_INVALID, ACTIVATION_LINK_SENT
from MapSkinner.responses import DefaultContext, BackendAjaxResponse
from MapSkinner.settings import SESSION_EXPIRATION, ROOT_URL, LAST_ACTIVITY_DATE_RANGE
from MapSkinner.utils import sha256
from service.models import Metadata
from structure.forms import LoginForm, RegistrationForm
from structure.models import User, UserActivation, PendingRequest, GroupActivity
from users.forms import PasswordResetForm, UserForm, PasswordChangeForm
from users.helper import user_helper


def login(request: HttpRequest):
    """ Login landing page

    Args:
        request (HttpRequest): The incoming request
    Returns:
         A view
    """
    template = "login.html"
    login_form = LoginForm(request.POST)

    # check if user is still logged in!
    user_id = request.session.get("user_id")
    if login_form.is_valid() or user_id is not None:
        if user_id is not None:
            user = user_helper.get_user(user_id=user_id)
        else:
            username = login_form.cleaned_data.get("username")
            password = login_form.cleaned_data.get("password")
            user = user_helper.get_user(username=username)
            if user is None or not user.is_password_valid(password):
                messages.add_message(request, messages.ERROR, USERNAME_OR_PW_INVALID)
                return redirect("login")
        if user is None:
            messages.add_message(request, messages.ERROR, USERNAME_OR_PW_INVALID)
            return redirect("login")
        if not user.is_active:
            messages.add_message(request, messages.INFO, ACCOUNT_NOT_ACTIVATED)
            return redirect("login")
        user.last_login = timezone.now()
        user.logged_in = True
        user.save()
        request.session["user_id"] = user.id
        request.session.set_expiry(SESSION_EXPIRATION)

        _next = request.session.get("next", None)

        if _next is None:
            home_uri = redirect("home")._headers.get("location", [None, "/home"])[1]
            _next = ROOT_URL + home_uri
        else:
            _next = ROOT_URL + _next
            del request.session["next"]
        return redirect(_next)
    login_form = LoginForm()
    params = {
        "login_form": login_form,
        "login_article_title": _("Sign in for Mr. Map"),
        "login_article": _("Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet. Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet. ")
    }
    context = DefaultContext(request, params)
    return render(request=request, template_name=template, context=context.get_context())


@check_session
def home_view(request: HttpRequest, user: User):
    """ Renders the dashboard / home view of the user

    Args:
        request: The incoming request
        user: The performing user
    Returns:
         A rendered view
    """
    template = "dashboard.html"
    user_services_wms = Metadata.objects.filter(
            service__servicetype__name="wms",
            service__is_root=True,
            created_by__in=user.groups.all(),
            service__is_deleted=False,
        ).count()
    user_services_wfs = Metadata.objects.filter(
            service__servicetype__name="wfs",
            service__is_root=True,
            created_by__in=user.groups.all(),
            service__is_deleted=False,
        ).count()
    activities_since = timezone.now() - datetime.timedelta(days=LAST_ACTIVITY_DATE_RANGE)
    group_activities = GroupActivity.objects.filter(group__in=user.groups.all(), created_on__gte=activities_since).order_by("-created_on")
    pending_requests = PendingRequest.objects.filter(organization=user.organization)
    params = {
        "wms_count": user_services_wms,
        "wfs_count": user_services_wfs,
        "requests": pending_requests,
        "group_activities": group_activities,
    }
    context = DefaultContext(request, params, user)
    return render(request, template, context.get_context())


@check_session
def account(request: HttpRequest, user: User):
    """ Renders an overview of the user's account information

    Args:
        request (HttpRequest): The incoming request
        user (User): The user
    Returns:
         A rendered view
    """
    template = "account.html"
    form = UserForm(instance=user)
    params = {
        "user": user,
        "form": form,
    }
    context = DefaultContext(request, params, user)
    return render(request, template, context.get_context())

@check_session
def password_change(request: HttpRequest, user: User):
    """ Renders the form for password changing and validates the input afterwards

    Args:
        request (HttpRequest): The incoming request
        user (User): The user
    Returns:
        A view
    """
    template = "change_password.html"
    form = PasswordChangeForm()
    if request.method == 'POST':
        form = PasswordChangeForm(request.POST)
        if form.is_valid():
            password = form.data.get("password")
            password_again = form.data.get("password_again")
            if password != password_again:
                messages.add_message(request, messages.ERROR, PASSWORD_CHANGE_NO_MATCH)
            else:
                user.password = make_password(password, user.salt)
                user.save()
                messages.add_message(request, messages.SUCCESS, PASSWORD_CHANGE_SUCCESS)
        else:
            messages.add_message(request, messages.ERROR, FORM_INPUT_INVALID)
        return redirect("account")
    else:
        params = {
            "form": form,
            "article": _("Please insert your new password. You have to fulfill the password constraints."),
            "action_url": ROOT_URL + "/users/password/edit/"
        }
        context = DefaultContext(request, params, user)
        html = render_to_string(request=request, template_name=template, context=context.get_context())
        return BackendAjaxResponse(html=html).get_response()

@check_session
def account_edit(request: HttpRequest, user: User):
    """ Renders a form for editing user account data

    Args:
        request (HttpRequest): The incoming request
        user (User): The user
    Returns:
        A view
    """
    template = "users_form.html"
    form = UserForm(request.POST or None, instance=user)
    if request.method == 'POST':
        if form.is_valid():
            # save changes
            user = form.save()
            user.save()
            messages.add_message(request, messages.SUCCESS, ACCOUNT_UPDATE_SUCCESS)
        else:
            messages.add_message(request, messages.ERROR, FORM_INPUT_INVALID)
        return redirect("account")
    else:
        params = {
            "form": form,
            "article": _("You can update your account information using this form."),
            "action_url": ROOT_URL + "/users/edit/"
        }
        context = DefaultContext(request, params, user)
        html = render_to_string(request=request, template_name=template, context=context.get_context())
        return BackendAjaxResponse(html=html).get_response()


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
        messages.add_message(request, messages.ERROR, ACTIVATION_LINK_INVALID)
        return redirect("login")

    activation_until = user_activation.activation_until
    if activation_until < timezone.now():
        # the activation was confirmed too late!
        messages.add_message(request, messages.ERROR, ACTIVATION_LINK_INVALID)
        return redirect("login")

    user = user_activation.user
    user.is_active = True
    user.save()
    user_activation.delete()
    params = {
        "user": user,
    }
    context = DefaultContext(request, params, user)
    return render(request=request, template_name=template, context=context.get_context())


@check_session
def logout(request: HttpRequest, user: User):
    """ Logs the structure out and redirects to login view

    Args:
        request (HttpRequest): The incoming request
    Returns:
         A view
    """
    user.logged_in = False
    user.save()
    del request.session["user_id"]
    messages.add_message(request, messages.SUCCESS, LOGOUT_SUCCESS)
    return redirect('login')


@transaction.atomic
def password_reset(request: HttpRequest):
    """ Renders a view for requesting a new auto-generated password which will be sent via mail

    Args:
        request (HttpRequest): The incoming request
    Returns:
         A view
    """
    template = "password_reset.html"
    form = PasswordResetForm()
    if request.method == 'POST':
        form = PasswordResetForm(request.POST)
        if form.is_valid:
            # generate new password
            try:
                user = User.objects.get(email=form.data.get("email"))
            except ObjectDoesNotExist:
                messages.add_message(request, messages.ERROR, UNKNOWN_EMAIL)
                return redirect('password-reset')
            # ToDo: Do sending via email!
            gen_pw = sha256(user.salt + str(timezone.now()))[:7].upper()
            print(gen_pw)
            user.password = make_password(gen_pw, user.salt)
            user.save()
            messages.add_message(request, messages.INFO, PASSWORD_SENT)
            return redirect('login')
        else:
            messages.add_message(request, messages.ERROR, EMAIL_INVALID)
            return redirect('password-reset')
    else:
        params = {
            "form": form,
        }
        context = DefaultContext(request, params)
        return render(request, template, context=context.get_context())


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
        "action_url": ROOT_URL + "/register/"
    }
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            cleaned_data = form.cleaned_data
            password = cleaned_data.get("password")
            password_check = cleaned_data.get("password_check")
            if password != password_check:
                messages.add_message(request, messages.ERROR, PASSWORD_CHANGE_NO_MATCH)
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
                user.create_activation()

                messages.add_message(request, messages.SUCCESS, ACTIVATION_LINK_SENT)
                return redirect("login")
        else:
            params["not_valid"] = True
            params["form"] = form
            for error_key, error_val in form.errors.items():
                for e in error_val.data:
                    messages.add_message(request, messages.ERROR, e.message)
    context = DefaultContext(request, params)
    return render(request=request, template_name=template, context=context.get_context())
