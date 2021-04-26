from django.contrib.auth import get_user_model
import json
from celery import states
from celery.worker.control import revoke
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.db.models import Case, When, Q
from django.http import HttpResponseRedirect
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.views.generic import DeleteView, DetailView, UpdateView, CreateView
from django.views.generic.base import ContextMixin
from django_bootstrap_swt.components import Tag, Badge
from django_bootstrap_swt.enums import BadgeColorEnum
from django_celery_results.models import TaskResult
from django_filters.views import FilterView
from MrMap.icons import IconEnum
from MrMap.messages import PUBLISH_REQUEST_DENIED, \
    PUBLISH_REQUEST_ACCEPTED, \
    ORGANIZATION_SUCCESSFULLY_CREATED, ORGANIZATION_SUCCESSFULLY_DELETED, PUBLISH_REQUEST_SENT, \
    ORGANIZATION_SUCCESSFULLY_EDITED, NO_PERMISSION
from MrMap.views import InitFormMixin, GenericViewContextMixin, CustomSingleTableMixin, \
    SuccessMessageDeleteMixin
from main.views import SecuredDependingListMixin
from structure.forms import OrganizationChangeForm
from structure.permissionEnums import PermissionEnum
from structure.models import Organization, PublishRequest
from django.urls import reverse_lazy

from structure.tables.tables import OrganizationTable, OrganizationDetailTable, OrganizationMemberTable, \
    OrganizationPublishersTable, PublishesRequestTable, MrMapUserTable


class OrganizationDetailContextMixin(ContextMixin):
    object = None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tab_nav = [{'url': self.object.get_absolute_url,
                    'title': _('Details')},
                   {'url': self.object.publishers_uri,
                    'title': _('Publishers ').__str__() +
                             Badge(content=str(self.object.publishers.count()),
                                   color=BadgeColorEnum.SECONDARY)},
                   ]
        context.update({"object": self.object,
                        'actions': self.object.get_actions(),
                        'tab_nav': tab_nav,
                        'publisher_requests_count': PublishRequest.objects.filter(organization=self.object).count()})
        return context


@method_decorator(login_required, name='dispatch')
class OrganizationTableView(CustomSingleTableMixin, FilterView):
    model = Organization
    table_class = OrganizationTable
    filterset_fields = {'name': ['icontains'],
                        'parent__organization_name': ['icontains'],
                        'is_auto_generated': ['exact']}

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.order_by(
            Case(When(id=self.request.user.organization.id if self.request.user.organization is not None else 0, then=0), default=1),
            'name')
        return queryset


@method_decorator(login_required, name='dispatch')
class OrganizationNewView(PermissionRequiredMixin, InitFormMixin, GenericViewContextMixin, SuccessMessageMixin, CreateView):
    model = Organization
    template_name = 'MrMap/detail_views/generic_form.html'
    title = _('New organization')
    success_message = ORGANIZATION_SUCCESSFULLY_CREATED
    permission_required = PermissionEnum.CAN_CREATE_ORGANIZATION.value
    raise_exception = True
    permission_denied_message = NO_PERMISSION

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"request": self.request})
        return kwargs


@method_decorator(login_required, name='dispatch')
class OrganizationDetailView(GenericViewContextMixin, OrganizationDetailContextMixin, DetailView):
    class Meta:
        verbose_name = _('Details')

    model = Organization
    template_name = 'MrMap/detail_views/table_tab.html'
    queryset = Organization.objects.all()
    title = _('Details')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        details_table = OrganizationDetailTable(data=[self.object, ], request=self.request)
        context.update({'table': details_table})
        return context


@method_decorator(login_required, name='dispatch')
class OrganizationEditView(PermissionRequiredMixin, InitFormMixin, GenericViewContextMixin, SuccessMessageMixin, UpdateView):
    template_name = 'MrMap/detail_views/generic_form.html'
    success_message = ORGANIZATION_SUCCESSFULLY_EDITED
    model = Organization
    form_class = OrganizationChangeForm
    title = _('Edit organization')
    permission_required = PermissionEnum.CAN_EDIT_ORGANIZATION.value
    raise_exception = True
    permission_denied_message = NO_PERMISSION

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"request": self.request})
        return kwargs


@method_decorator(login_required, name='dispatch')
class OrganizationDeleteView(PermissionRequiredMixin, GenericViewContextMixin, SuccessMessageDeleteMixin, DeleteView):
    model = Organization
    template_name = "MrMap/detail_views/delete.html"
    success_url = reverse_lazy('structure:organization_overview')
    success_message = ORGANIZATION_SUCCESSFULLY_DELETED
    queryset = Organization.objects.filter(is_auto_generated=False)
    title = _('Delete organization')
    permission_required = PermissionEnum.CAN_DELETE_ORGANIZATION.value
    raise_exception = True
    permission_denied_message = NO_PERMISSION

    def get_msg_dict(self):
        return {'name': self.get_object().name}


@method_decorator(login_required, name='dispatch')
class OrganizationMembersTableView(SecuredDependingListMixin, OrganizationDetailContextMixin, CustomSingleTableMixin, FilterView):
    model = get_user_model()
    depending_model = Organization
    table_class = OrganizationMemberTable
    filterset_fields = {'username': ['icontains']}
    template_name = 'MrMap/detail_views/table_tab.html'
    object = None
    title = Tag(tag='i', attrs={"class": [IconEnum.PENDING_TASKS.value]}) + _(' Members')

    def get_queryset(self):
        return self.object.primary_users.all()

    def get_table_kwargs(self):
        return {'organization': self.object}


@method_decorator(login_required, name='dispatch')
class OrganizationPublishersTableView(SecuredDependingListMixin, OrganizationDetailContextMixin, CustomSingleTableMixin, FilterView):
    model = Organization
    depending_model = Organization
    table_class = OrganizationPublishersTable
    filterset_fields = {'name': ['icontains']}
    template_name = 'MrMap/detail_views/table_tab.html'
    object = None
    title = Tag(tag='i', attrs={"class": [IconEnum.PUBLISHERS.value]}) + _(' Publish for list')

    def get_queryset(self):
        return self.object.publishers.all()

    def get_table_kwargs(self):
        return {'organization': self.object}


@method_decorator(login_required, name='dispatch')
class PublishRequestNewView(PermissionRequiredMixin, GenericViewContextMixin, InitFormMixin, SuccessMessageMixin, CreateView):
    model = PublishRequest
    fields = ('group', 'organization', 'message')
    template_name = 'MrMap/detail_views/generic_form.html'
    title = _('Publish request')
    success_message = PUBLISH_REQUEST_SENT
    permission_required = PermissionEnum.CAN_ADD_PUBLISH_REQUEST.value
    raise_exception = True
    permission_denied_message = NO_PERMISSION

    def form_valid(self, form):
        group = form.cleaned_data['group']
        organization = form.cleaned_data['organization']
        if group.publish_for_organizations.filter(id=organization.id).exists():
            form.add_error(None, _(f'{group} can already publish for Organization.'))
            return self.form_invalid(form)
        else:
            return super().form_valid(form)


@method_decorator(login_required, name='dispatch')
class PublishRequestTableView(CustomSingleTableMixin, FilterView):
    model = PublishRequest
    table_class = PublishesRequestTable
    filterset_fields = ['group', 'organization', 'message']

    def get_queryset(self):
        queryset = super().get_queryset()
        if not self.request.user.is_superuser:
            # show only requests for groups or organization where the user is member of
            # superuser can see all pending requests
            queryset.filter(Q(group__in=self.request.user.groups.all()) |
                            Q(organization=self.request.user.organization))
        return queryset


@method_decorator(login_required, name='dispatch')
class PublishRequestAcceptView(PermissionRequiredMixin, GenericViewContextMixin, SuccessMessageMixin, InitFormMixin, UpdateView):
    model = PublishRequest
    template_name = "MrMap/detail_views/generic_form.html"
    success_url = reverse_lazy('structure:publish_request_overview')
    fields = ('is_accepted', )
    success_message = PUBLISH_REQUEST_ACCEPTED
    title = _('Accept request')
    permission_required = PermissionEnum.CAN_TOGGLE_PUBLISH_REQUESTS.value
    raise_exception = True
    permission_denied_message = NO_PERMISSION

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
        except ValidationError as e:
            messages.error(self.request, e.message)
            response = HttpResponseRedirect(self.get_success_url())
        return response


@method_decorator(login_required, name='dispatch')
class PublishRequestRemoveView(PermissionRequiredMixin, GenericViewContextMixin, SuccessMessageMixin, DeleteView):
    model = PublishRequest
    template_name = "MrMap/detail_views/delete.html"
    success_url = reverse_lazy('structure:index')
    success_message = PUBLISH_REQUEST_DENIED
    title = _('Deny request')
    permission_required = PermissionEnum.CAN_TOGGLE_PUBLISH_REQUESTS.value
    raise_exception = True
    permission_denied_message = NO_PERMISSION


@method_decorator(login_required, name='dispatch')
class UserTableView(CustomSingleTableMixin, FilterView):
    model = get_user_model()
    table_class = MrMapUserTable
    filterset_fields = {'username': ['icontains'],
                        'organization__organization_name': ['icontains'],
                        'groups__name': ['icontains']}
