"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.05.19

"""

import os
from random import random
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth import logout, authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.http import HttpRequest
from django.shortcuts import redirect, render, get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from MrMap.messages import USERNAME_OR_PW_INVALID, \
    ACTIVATION_LINK_INVALID, ACCOUNT_NOT_ACTIVATED, \
    LOGOUT_SUCCESS, PASSWORD_SENT, ACTIVATION_LINK_SENT, ACTIVATION_LINK_EXPIRED, \
    RESOURCE_NOT_FOUND_OR_NOT_OWNER
from MrMap.responses import DefaultContext
from MrMap.settings import ROOT_URL, LAST_ACTIVITY_DATE_RANGE
from service.helper.crypto_handler import CryptoHandler
from service.models import Metadata
from structure.forms import LoginForm, RegistrationForm
from structure.models import MrMapUser, UserActivation, GroupActivity, Organization, MrMapGroup, \
    PublishRequest, GroupInvitationRequest
from users.forms import PasswordResetForm, UserForm, PasswordChangeForm, SubscriptionForm, SubscriptionRemoveForm
from users.helper import user_helper
from django.urls import reverse

from users.models import Subscription
from users.settings import users_logger
from users.tables import SubscriptionTable


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

    if user.is_authenticated:
        return redirect("home")

    # Someone wants to login
    if request.method == 'POST' and form.is_valid() and user.is_anonymous:
        # trial to login the user
        username = form.cleaned_data.get("username")
        password = form.cleaned_data.get("password")
        user = authenticate(request=request, username=username, password=password)

        if user is None:
            # Is user not activated yet?
            try:
                user = MrMapUser.objects.get_by_natural_key(username)
                if not user.is_active:
                    messages.add_message(request, messages.INFO, ACCOUNT_NOT_ACTIVATED)
                    return redirect("login")
            except ObjectDoesNotExist:
                messages.add_message(request, messages.ERROR, USERNAME_OR_PW_INVALID)
                return redirect("login")

        login(request, user)
        _next = form.cleaned_data.get("next", None)

        if _next is None or len(_next) == 0:
            home_uri = reverse("home")
            _next = home_uri

        return redirect(_next)

    params = {
        "login_form": LoginForm(),
        "login_article_title": _("Sign in for Mr. Map"),
        "login_article": _(
            "Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet. Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet. "),
        "username_label": form['username'].label,
        "password_label": form['password'].label
    }
    context = DefaultContext(request, params)
    return render(request=request, template_name=template, context=context.get_context())


@login_required
def home_view(request: HttpRequest,  update_params=None, status_code=None):
    """ Renders the dashboard / home view of the user

    Args:
        request: The incoming request
        user: The performing user
    Returns:
         A rendered view
    """
    user = user_helper.get_user(request)
    template = "views/dashboard.html"
    user_groups = user.get_groups()
    user_services_wms = Metadata.objects.filter(
        service__service_type__name="wms",
        service__is_root=True,
        created_by__in=user_groups,
        service__is_deleted=False,
    ).count()
    user_services_wfs = Metadata.objects.filter(
        service__service_type__name="wfs",
        service__is_root=True,
        created_by__in=user_groups,
        service__is_deleted=False,
    ).count()

    datasets_count = user.get_datasets_as_qs(count=True)

    activities_since = timezone.now() - timezone.timedelta(days=LAST_ACTIVITY_DATE_RANGE)
    group_activities = GroupActivity.objects.filter(group__in=user_groups, created_on__gte=activities_since).order_by(
        "-created_on")

    pending_requests = PublishRequest.objects.filter(organization=user.organization)
    group_invitation_requests = GroupInvitationRequest.objects.filter(
        invited_user=user
    )
    params = {
        "wms_count": user_services_wms,
        "wfs_count": user_services_wfs,
        "datasets_count": datasets_count,
        "all_count": user_services_wms + user_services_wfs + datasets_count,
        "publishing_requests": pending_requests,
        "group_invitation_requests": group_invitation_requests,
        "no_requests": not group_invitation_requests.exists() and not pending_requests.exists(),
        "group_activities": group_activities,
        "groups": user_groups,
        "organizations": Organization.objects.filter(is_auto_generated=False),
        "current_view": "home",
    }
    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request,
                  template_name=template,
                  context=context.get_context(),
                  status=200 if status_code is None else status_code)


@login_required
def account(request: HttpRequest, update_params: dict = None, status_code: int = 200, ):
    """ Renders an overview of the user's account information

    Args:
        request (HttpRequest): The incoming request
        update_params:
        status_code (MrMapUser): The user
    Returns:
         A rendered view
    """
    template = "views/account.html"
    user = user_helper.get_user(request)
    subscriptions_count = Subscription.objects.filter(user=user).count()
    params = {
        "subscriptions_count": subscriptions_count,
        "current_view": 'account',
    }

    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request, template_name=template, context=context.get_context(), status=status_code)


@login_required
def subscriptions(request: HttpRequest, update_params: dict = None, status_code: int = 200, ):
    """ Renders an overview of the user's account information

    Args:
        request (HttpRequest): The incoming request
        update_params:
        status_code (MrMapUser): The user
    Returns:
         A rendered view
    """
    template = "views/subscriptions.html"
    user = user_helper.get_user(request)

    subscription_table = SubscriptionTable(request=request,
                                           current_view='subscription-index')

    params = {
        "subscriptions": subscription_table,
        "current_view": 'subscription-index',
    }

    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request, template_name=template, context=context.get_context(), status=status_code)


@login_required
def password_change(request: HttpRequest):
    """ Renders the form for password changing and validates the input afterwards

    Args:
        request (HttpRequest): The incoming request
    Returns:
        A view
    """
    form = PasswordChangeForm(data=request.POST or None,
                              request=request,
                              reverse_lookup='password-change',
                              # ToDo: after refactoring of all forms is done, show_modal can be removed
                              show_modal=True,
                              form_title=_(f"Change password"),
                              )

    return form.process_request(valid_func=form.process_change_password)


@login_required
def account_edit(request: HttpRequest):
    """ Renders a form for editing user account data

    Args:
        request (HttpRequest): The incoming request
    Returns:
        A view
    """
    user = user_helper.get_user(request)
    form = UserForm(data=request.POST or None,
                    request=request,
                    reverse_lookup='account-edit',
                    # ToDo: after refactoring of all forms is done, show_modal can be removed
                    show_modal=True,
                    form_title=_(f"<strong>Edit your account information's</strong>"),
                    instance=user,
                    initial={'theme': user.theme},)
    return form.process_request(form.process_account_change)


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
        # The activation was confirmed too late!
        messages.add_message(request, messages.ERROR, ACTIVATION_LINK_EXPIRED)
        # Remove the inactive user object
        user_activation.user.delete()
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
    """ Logout the user and redirect to login view

    Args:
        request (HttpRequest): The incoming request
    Returns:
         A view
    """
    messages.add_message(request, messages.SUCCESS, LOGOUT_SUCCESS)
    logout(request)
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
        gen_pw = sec_handler.sha256(
            user.salt + str(timezone.now()) + str(random() * 10000)
        )[:7].upper()
        users_logger.debug(gen_pw)
        user.set_password(gen_pw)
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
        "registration_article": _(
            "Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet. Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet. "),
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

        # Add user to Public group
        public_group = MrMapGroup.objects.get(
            is_public_group=True
        )
        public_group.user_set.add(user)

        # create user_activation object to improve checking against activation link
        user.create_activation()

        messages.add_message(request, messages.SUCCESS, ACTIVATION_LINK_SENT)
        return redirect("login")

    context = DefaultContext(request, params)
    return render(request=request, template_name=template, context=context.get_context())


@login_required
def subscription_index_view(request: HttpRequest, update_params: dict = None, status_code: int = 200, ):
    """ Renders an overview of all subscriptions of the performing user

    Args:
        request (HttpRequest): The incoming request
    Returns:
         A rendered view
    """
    template = "views/subscriptions.html"
    user = user_helper.get_user(request)

    subscription_table = SubscriptionTable(request=request,
                                           current_view='subscription-index')

    params = {
        "subscriptions": subscription_table,
        "current_view": 'subscription-index',
    }

    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request, template_name=template, context=context.get_context(), status=status_code)


@login_required
def subscription_new_view(request: HttpRequest, ):
    """ Renders a view for editing a subscription

    Args:
        request (HttpRequest): The incoming request
        current_view (str): The current view where the request comes from
    Returns:
         A rendered view
    """
    form = SubscriptionForm(
        data=request.POST or None,
        request=request,
        reverse_lookup='subscription-new',
        form_title=_('New Subscription'),
        # ToDo: show_modal will be default True in future
        show_modal=True,
        has_autocomplete_fields=True,
     )
    return form.process_request(valid_func=form.process_new_subscription)


@login_required
def subscription_edit_view(request: HttpRequest, subscription_id: str, ):
    """ Renders a view for editing a subscription

    Args:
        request (HttpRequest): The incoming request
        subscription_id (str): The uuid of the subscription as string
        current_view: The current view where the request comes from
    Returns:
         A rendered view
    """
    user = user_helper.get_user(request)
    try:
        subscription = Subscription.objects.get(
            id=subscription_id,
            user=user,
        )
    except ObjectDoesNotExist:
        messages.error(request, RESOURCE_NOT_FOUND_OR_NOT_OWNER)
        return redirect('users:home')

    form = SubscriptionForm(data=request.POST or None,
                            instance=subscription,
                            is_edit=True,
                            request=request,
                            reverse_lookup='subscription-edit',
                            reverse_args=[subscription_id, ],
                            form_title=_('New Subscription'),
                            # ToDo: show_modal will be default True in future
                            show_modal=True,
                            )
    return form.process_request(valid_func=form.process_edit_subscription)


@login_required
def subscription_remove(request: HttpRequest, subscription_id: str, ):
    """ Removes a subscription

    Args:
        request (HttpRequest): The incoming request
        id (str): The uuid of the subscription as string
    Returns:
         A rendered view
    """
    user = user_helper.get_user(request)
    subscription = get_object_or_404(klass=Subscription,
                                     id=subscription_id,
                                     user=user)

    form = SubscriptionRemoveForm(data=request.POST or None,
                                  request=request,
                                  reverse_lookup='subscription-remove',
                                  reverse_args=[subscription_id, ],
                                  form_title=_(f'Remove Subscription for service <strong>{subscription.metadata}</strong>'),
                                  # ToDo: show_modal will be default True in future
                                  show_modal=True,
                                  instance=subscription,)
    return form.process_request(valid_func=form.process_remove_subscription)

