"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.05.19

"""

import datetime
import os

from django.contrib import messages
from django.contrib.auth import logout, authenticate, login
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.http import HttpRequest, HttpResponseRedirect
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
from MapSkinner.utils import print_debug_mode
from service.helper.crypto_handler import CryptoHandler
from service.models import Metadata
from structure.forms import LoginForm, RegistrationForm
from structure.models import MrMapUser, UserActivation, PendingRequest, GroupActivity, Organization
from users.forms import PasswordResetForm, UserForm, PasswordChangeForm
from users.helper import user_helper
from django.urls import reverse


def _return_account_view(request: HttpRequest, user: MrMapUser, params):
    template = "views/account.html"
    render_params = _prepare_account_view_params(user)
    if params:
        render_params.update(params)

    context = DefaultContext(request, render_params, user)
    return render(request=request, template_name=template, context=context.get_context())


def _prepare_account_view_params(user: MrMapUser):
    edit_account_form = UserForm(instance=user, initial={'theme': user.theme})
    edit_account_form.action_url = reverse('account-edit', )

    password_change_form = PasswordChangeForm()
    password_change_form.action_url = reverse('password-change', )

    params = {
        "user": user,
        "edit_account_form": edit_account_form,
        "password_change_form": password_change_form,
    }
    return params


def login_view(request: HttpRequest):
    """ Login landing page

    Args:
        request (HttpRequest): The incoming request
    Returns:
         A view
    """
    template = "views/login.html"
    form = LoginForm(request.POST)

    # check if user is still logged in!
    user = request.user

    if not user.is_anonymous and user.is_authenticated:
        return redirect("home")

    # Someone wants to login
    if request.method == 'POST' and form.is_valid() and user.is_anonymous:
        # trial to login the user
        username = form.cleaned_data.get("username")
        password = form.cleaned_data.get("password")
        #user = user_helper.get_user(username=username)
        user = authenticate(request=request, username=username, password=password)
        login(request, user)
        # does the user exist?
        if user is None:
            messages.add_message(request, messages.ERROR, USERNAME_OR_PW_INVALID)
            return redirect("login")
        # is user active?
        if not user.is_active:
            messages.add_message(request, messages.INFO, ACCOUNT_NOT_ACTIVATED)
            return redirect("login")

        _next = request.session.get("next", None)

        if _next is None:
            home_uri = redirect("home")._headers.get("location", [None, "/home"])[1]
            _next = ROOT_URL + home_uri
        else:
            _next = ROOT_URL + _next
            try:
                del request.session["next"]
            except KeyError:
                # this should not be possible - however ...
                pass
        return redirect(_next)


    params = {
        "login_form": LoginForm(),
        "login_article_title": _("Sign in for Mr. Map"),
        "login_article": _("Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet. Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet. ")
    }
    context = DefaultContext(request, params)
    return render(request=request, template_name=template, context=context.get_context())


#@check_session
def home_view(request: HttpRequest):
    """ Renders the dashboard / home view of the user

    Args:
        request: The incoming request
        user: The performing user
    Returns:
         A rendered view
    """
    user = request.user
    template = "views/dashboard.html"
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
        "all_count": user_services_wms + user_services_wfs,
        "requests": pending_requests,
        "group_activities": group_activities,
        "groups": user.groups.all(),
        "organizations": Organization.objects.filter(is_auto_generated=False)
    }
    context = DefaultContext(request, params, user)
    return render(request, template, context.get_context())


@check_session
def account(request: HttpRequest, user: MrMapUser, params={}):
    """ Renders an overview of the user's account information

    Args:
        params:
        request (HttpRequest): The incoming request
        user (MrMapUser): The user
    Returns:
         A rendered view
    """
    return _return_account_view(request, user, params)


@check_session
def password_change(request: HttpRequest, user: MrMapUser):
    """ Renders the form for password changing and validates the input afterwards

    Args:
        request (HttpRequest): The incoming request
        user (MrMapUser): The user
    Returns:
        A view
    """
    form = PasswordChangeForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        password = form.cleaned_data["password"]
        user.password = make_password(password, user.salt)
        user.save()
        messages.add_message(request, messages.SUCCESS, PASSWORD_CHANGE_SUCCESS)
    else:
        return account(request=request, params={'password_change_form': form,
                                                'show_password_change_form': True})

    return redirect(reverse("account"))


@check_session
def account_edit(request: HttpRequest, user: MrMapUser):
    """ Renders a form for editing user account data

    Args:
        request (HttpRequest): The incoming request
        user (MrMapUser): The user
    Returns:
        A view
    """
    form = UserForm(request.POST or None, instance=user)
    if request.method == 'POST' and form.is_valid():
        # save changes
        user = form.save()
        user.save()
        messages.add_message(request, messages.SUCCESS, ACCOUNT_UPDATE_SUCCESS)
        return redirect("account")

    return _return_account_view(request, user, {
        "edit_account_form": form,
        "show_edit_account_form": True
    })




def activate_user(request: HttpRequest, activation_hash: str):
    """ Checks the activation hash and activates the user's account if possible

    Args:
        request (HttpRequest): The incoming request
        activation_hash (str): The activation hash from the url
    Returns:
         A rendered view
    """
    template = "views/user_activation.html"

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


def logout_view(request: HttpRequest):
    """ Logs the structure out and redirects to login view

    Args:
        user:
        request (HttpRequest): The incoming request
    Returns:
         A view
    """
    user = request.user
    #user.logged_in = False
    #user.save()
    logout(request)

    # remove session related data
    del_keys = [
        "user_id",
        "next",
    ]
    for key in del_keys:
        try:
            del request.session[key]
        except KeyError:
            pass

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
    template = "views/password_reset.html"
    form = PasswordResetForm(request.POST or None)
    params = {
        "form": form,
    }
    if request.method == 'POST' and form.is_valid():
        # we dont need to check the email address here: see clean function of PasswordResetForm class
        user = MrMapUser.objects.get(email=form.cleaned_data.get("email"))

        # generate new password
        # ToDo: Do sending via email!
        sec_handler = CryptoHandler()
        gen_pw = sec_handler.sha256(user.salt + str(timezone.now()))[:7].upper()
        print_debug_mode(gen_pw)
        user.password = make_password(gen_pw, user.salt)
        user.save()
        messages.add_message(request, messages.INFO, PASSWORD_SENT)
        return redirect('login')

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
    template = "views/register.html"
    form = RegistrationForm(request.POST or None)
    params = {
        "form": form,
        "registration_article": _("Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet. Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet. "),
        "registration_title": _("Sign up"),
        "action_url": ROOT_URL + "/register/"
    }
    if request.method == "POST" and form.is_valid():
        cleaned_data = form.cleaned_data

        # create new user and send mail
        user = MrMapUser()
        user.username = cleaned_data.get("username")
        user.salt = str(os.urandom(25).hex())
        user.password = make_password(cleaned_data.get("password"), salt=user.salt)
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

    context = DefaultContext(request, params)
    return render(request=request, template_name=template, context=context.get_context())
