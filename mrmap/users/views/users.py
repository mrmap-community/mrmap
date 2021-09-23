"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.05.19

"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.views import LoginView, PasswordChangeView, PasswordResetView
from django.contrib.messages.views import SuccessMessageMixin
from django.contrib.sites.shortcuts import get_current_site
from django.shortcuts import redirect, get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, ListView, TemplateView
from django_filters.views import FilterView
from guardian.mixins import LoginRequiredMixin
from django.views.generic import DetailView, ListView, TemplateView
from MrMap.messages import ACTIVATION_LINK_EXPIRED, \
    SUBSCRIPTION_SUCCESSFULLY_DELETED, SUBSCRIPTION_EDITING_SUCCESSFULL, SUBSCRIPTION_SUCCESSFULLY_CREATED, \
    PASSWORD_CHANGE_SUCCESS, PASSWORD_SENT
from extras.views import SecuredUpdateView, SecuredDeleteView, SecuredCreateView, SecuredListMixin
from users.forms.users import RegistrationForm
from users.models.groups import Organization, PublishRequest
from users.forms.users import SubscriptionForm, MrMapUserForm
from users.models.users import Subscription, UserActivation
from users.tables.users import SubscriptionTable, MrMapUserTable
from django.conf import settings
from django.contrib.auth import get_user_model



class MrMapLoginView(SuccessMessageMixin, LoginView):
    template_name = "users/views/logged_out/login.html"
    redirect_authenticated_user = True
    success_message = _('Successfully signed in.')

    # Add logging if form is invalid to check logs against security policy
    def form_invalid(self, form):
        settings.ROOT_LOGGER.info(f'User {form.cleaned_data["username"]} trial to login, but the following error occurs. '
                          f'{form.errors}')
        return super().form_invalid(form=form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "login_article_title": _("Sign in for Mr. Map"),
            "login_article": _(
                "Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet. Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet. "),
        })
        return context


class HomeView(LoginRequiredMixin, TemplateView):
    template_name = "users/views/home/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        pending_requests = PublishRequest.objects.filter(to_organization__in=self.request.user.organizations)
        context.update({
            "publishing_requests": pending_requests,
            "organizations": Organization.objects.all(),
        })
        return context


class ProfileView(LoginRequiredMixin, DetailView):
    template_name = "users/views/profile/profile.html"
    model = get_user_model()
    slug_field = "username"

    def get_object(self, queryset=None):
        return get_object_or_404(get_user_model(), username=self.request.user.username)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'subscriptions_count': Subscription.objects.filter(user=self.request.user).count()})
        return context


class MrMapPasswordChangeView(SuccessMessageMixin, PasswordChangeView):
    template_name = 'users/views/profile/password_change.html'
    success_message = PASSWORD_CHANGE_SUCCESS


class MrMapPasswordResetView(SuccessMessageMixin, PasswordResetView):
    template_name = 'users/views/logged_out/password_reset_or_confirm.html'
    success_message = PASSWORD_SENT


class EditProfileView(SecuredUpdateView):
    template_name = 'users/views/profile/password_change.html'
    success_message = _('Profile successfully edited.')
    model = get_user_model()
    form_class = MrMapUserForm
    title = _('Edit profile')


    # cause this view is callable without primary key. The object will be always the logged in user.
    def get_object(self, queryset=None):
        return get_object_or_404(get_user_model(), username=self.request.user.username)


class ActivateUser(SecuredDeleteView):
    template_name = "views/user_activation.html"
    model = UserActivation
    success_url = reverse_lazy('login')

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        if self.object.activation_until < timezone.now():
            # The activation was confirmed too late!
            messages.add_message(request, messages.ERROR, ACTIVATION_LINK_EXPIRED)
            # Remove the inactive user object
            self.object.user_activation.user.delete()
            return redirect("login")

        self.object.user.is_active = True
        self.object.user.save()
        return self.delete(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'user': self.object.user})
        return context


class SignUpView(SecuredCreateView):
    template_name = 'users/views/logged_out/sign_up.html'
    success_url = reverse_lazy('login')
    model = get_user_model()
    form_class = RegistrationForm
    success_message = "Your profile was created successfully"
    title = _("Signup")

    def form_valid(self, form):
        response = super().form_valid(form)
        # create UserActivation and send mail to user
        user = self.object
        user_activation = UserActivation.objects.create(user=user)

        current_site = get_current_site(self.request)
        subject = 'Activate Your MrMap Account'
        message = render_to_string('users/email/signup.html', {
            'user': user,
            'domain': current_site.domain,
            'token': user_activation.activation_hash,
        })
        user.email_user(subject, message)
        return response


class SubscriptionTableView(SecuredListMixin, ListView):
    model = Subscription
    table_class = SubscriptionTable
    template_name = 'users/views/profile/manage_subscriptions.html'

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(user=self.request.user)


class AddSubscriptionView(SecuredCreateView):
    model = Subscription
    template_name = "users/views/profile/add_update_subscription.html"
    form_class = SubscriptionForm
    success_message = SUBSCRIPTION_SUCCESSFULLY_CREATED
    title = _('Add subscription')

    def get_initial(self):
        initial = super().get_initial()
        initial.update({'user': self.request.user})
        return initial


class UpdateSubscriptionView(SecuredUpdateView):
    model = Subscription
    template_name = "users/views/profile/add_update_subscription.html"
    form_class = SubscriptionForm
    success_message = SUBSCRIPTION_EDITING_SUCCESSFULL

    def get_title(self):
        return format_html(_(f'Update subscription for <strong>{self.object.metadata}</strong>'))


class DeleteSubscriptionView(SecuredDeleteView):
    model = Subscription
    template_name = "users/views/profile/delete_subscription.html"
    success_url = reverse_lazy('manage_subscriptions')
    success_message = SUBSCRIPTION_SUCCESSFULLY_DELETED
    title = _('Delete subscription')



class UserTableView(SecuredListMixin, FilterView):
    model = get_user_model()
    table_class = MrMapUserTable
    filterset_fields = {'username': ['icontains'],
                        'groups__name': ['icontains']}