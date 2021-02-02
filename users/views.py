"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.05.19

"""

import os
from collections import OrderedDict
from random import random
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import make_password
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.http import HttpRequest
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _, gettext
from django.views.generic import DetailView, ListView
from django.views.generic.edit import UpdateView, CreateView, DeleteView
from django_bootstrap_swt.components import Tag
from django_tables2 import SingleTableMixin
from MrMap.icons import IconEnum
from MrMap.messages import ACTIVATION_LINK_INVALID, PASSWORD_SENT, ACTIVATION_LINK_SENT, ACTIVATION_LINK_EXPIRED
from MrMap.responses import DefaultContext
from MrMap.settings import ROOT_URL, LAST_ACTIVITY_DATE_RANGE
from service.helper.crypto_handler import CryptoHandler
from service.models import Metadata
from structure.forms import RegistrationForm
from structure.models import MrMapUser, UserActivation, GroupActivity, Organization, MrMapGroup, \
    PublishRequest, GroupInvitationRequest
from users.forms import PasswordResetForm, SubscriptionForm
from users.helper import user_helper
from users.models import Subscription
from users.settings import users_logger
from users.tables import SubscriptionTable


class MrMapLoginView(LoginView):
    template_name = "views/login.html"
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "login_article_title": _("Sign in for Mr. Map"),
            "login_article": _(
                "Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet. Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet. "),
        })
        context = DefaultContext(request=self.request, context=context, user=self.request.user).context
        return context


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


@method_decorator(login_required, name='dispatch')
class ProfileView(DetailView):
    template_name = "views/profile/profile.html"
    model = MrMapUser
    slug_field = "username"

    def get_object(self, queryset=None):
        return get_object_or_404(MrMapUser, username=self.request.user.username)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context = DefaultContext(request=self.request, context=context).get_context()
        context.update({'subscriptions_count': Subscription.objects.filter(user=self.request.user).count()})
        breadcrumb_config = OrderedDict()
        breadcrumb_config['accounts'] = False
        breadcrumb_config['profile'] = True
        context.update({'breadcrumb_config': breadcrumb_config})
        return context


class MrMapPasswordChangeView(PasswordChangeView):
    template_name = 'views/profile/password_change.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context = DefaultContext(request=self.request, context=context).get_context()
        breadcrumb_config = OrderedDict()
        breadcrumb_config['accounts'] = {'is_representative': False, 'current_path': '/accounts'}
        breadcrumb_config['profile'] = {'is_representative': True, 'current_path': '/accounts/profile'}
        breadcrumb_config['change-password'] = {'is_representative': True, 'current_path': '/accounts/profile/change-password'}
        context.update({'breadcrumb_config': breadcrumb_config})
        return context


class EditProfileView(UpdateView):
    template_name = 'views/profile/password_change.html'
    model = MrMapUser
    fields = [
        "first_name",
        "last_name",
        "email",
        "confirmed_newsletter",
        "confirmed_survey",
        "theme",
    ]

    def get_object(self, queryset=None):
        return get_object_or_404(MrMapUser, username=self.request.user.username)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context = DefaultContext(request=self.request, context=context).get_context()
        context.update({'title': _('Edit profile')})
        breadcrumb_config = OrderedDict()
        breadcrumb_config['accounts'] = {'is_representative': False, 'current_path': '/accounts'}
        breadcrumb_config['profile'] = {'is_representative': True, 'current_path': '/accounts/profile'}
        breadcrumb_config['edit'] = {'is_representative': True, 'current_path': '/accounts/profile/edit'}
        context.update({'breadcrumb_config': breadcrumb_config})
        return context


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


@method_decorator(login_required, name='dispatch')
class SubscriptionTableView(SingleTableMixin, ListView):
    model = Subscription
    table_class = SubscriptionTable
    template_name = 'views/profile/manage_subscriptions.html'

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(user=self.request.user)

    def get_table(self, **kwargs):
        # set some custom attributes for template rendering
        table = super(SubscriptionTableView, self).get_table(**kwargs)
        table.title = Tag(tag='i', attrs={"class": [IconEnum.SUBSCRIPTION.value]}) + gettext(' Subscriptions')
        return table

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context = DefaultContext(request=self.request, context=context).get_context()
        context.update({'title': _('Edit profile')})
        return context

    def dispatch(self, request, *args, **kwargs):
        # configure table_pagination dynamically to support per_page switching
        self.table_pagination = {"per_page": self.request.GET.get('per_page', 5), }
        return super(SubscriptionTableView, self).dispatch(request, *args, **kwargs)


@method_decorator(login_required, name='dispatch')
class AddSubscriptionView(CreateView):
    model = Subscription
    template_name = "views/profile/add_update_subscription.html"
    form_class = SubscriptionForm

    def get_initial(self):
        initial = super().get_initial()
        initial.update({'user': self.request.user})
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context = DefaultContext(request=self.request, context=context).get_context()
        context.update({'title': _('Add subscription')})
        return context


@method_decorator(login_required, name='dispatch')
class UpdateSubscriptionView(UpdateView):
    model = Subscription
    template_name = "views/profile/add_update_subscription.html"
    form_class = SubscriptionForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context = DefaultContext(request=self.request, context=context).get_context()
        context.update({'title': format_html(_(f'Update subscription for <strong>{self.object.metadata}</strong>'))})
        return context


@method_decorator(login_required, name='dispatch')
class DeleteSubscriptionView(DeleteView):
    model = Subscription
    template_name = "views/profile/delete_subscription.html"
    success_url = reverse_lazy('manage_subscriptions')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context = DefaultContext(request=self.request, context=context).get_context()
        context.update({'title': _('Delete subscription')})
        return context
