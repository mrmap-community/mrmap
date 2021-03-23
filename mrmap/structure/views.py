from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.db.models import Case, When, Q
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _l
from django.utils.translation import gettext as _
from django.views.generic import DeleteView, DetailView, UpdateView, CreateView
from django.views.generic.base import ContextMixin
from django_bootstrap_swt.components import Tag, Badge
from django_bootstrap_swt.enums import BadgeColorEnum
from django_filters.views import FilterView
from guardian.mixins import LoginRequiredMixin, PermissionListMixin
from MrMap.icons import IconEnum
from MrMap.messages import PUBLISH_REQUEST_DENIED, PUBLISH_REQUEST_ACCEPTED, \
    PUBLISH_REQUEST_SENT, NO_PERMISSION
from MrMap.views import InitFormMixin, GenericViewContextMixin, CustomSingleTableMixin, DependingListView
from structure.permissionEnums import PermissionEnum
from structure.models import Organization, PendingTask, ErrorReport, PublishRequest
from structure.tables import OrganizationTable, \
    OrganizationDetailTable, OrganizationMemberTable, MrMapUserTable, \
    PublishesRequestTable, OrganizationPublishersTable
from django.urls import reverse_lazy


class OrganizationDetailContextMixin(ContextMixin):
    object = None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tab_nav = [{'url': self.object.get_absolute_url,
                    'title': _('Details')},
                   {'url': self.object.members_view_uri,
                    'title': _('Members ').__str__() + Badge(content=str(self.object.user_set.count()),
                                                             color=BadgeColorEnum.SECONDARY)},
                   {'url': self.object.publishers_uri,
                    'title': _('Publishers ').__str__() +
                             Badge(content=str(self.object.get_publishers().count()),
                                   color=BadgeColorEnum.SECONDARY)},
                   ]
        context.update({"object": self.object,
                        'actions': self.object.get_actions(),
                        'tab_nav': tab_nav,
                        'publisher_requests_count': PublishRequest.objects.filter(from_organization=self.object).count()})
        return context


class OrganizationTableView(LoginRequiredMixin, PermissionListMixin, CustomSingleTableMixin, FilterView):
    model = Organization
    table_class = OrganizationTable
    filterset_fields = {'organization_name': ['icontains'],
                        #'parent__organization_name': ['icontains'],
                        'is_auto_generated': ['exact']}
    permission_required = [PermissionEnum.CAN_VIEW_ORGANIZATION.value]

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.order_by(
            Case(When(id=self.request.user.organization.id if self.request.user.organization is not None else 0, then=0), default=1),
            'organization_name')
        return queryset


class OrganizationDetailView(LoginRequiredMixin, PermissionRequiredMixin, GenericViewContextMixin, OrganizationDetailContextMixin, DetailView):
    class Meta:
        verbose_name = _('Details')

    model = Organization
    template_name = 'MrMap/detail_views/table_tab.html'
    permission_required = [PermissionEnum.CAN_VIEW_ORGANIZATION.value]
    title = _('Details')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        details_table = OrganizationDetailTable(data=[self.object, ], request=self.request)
        context.update({'table': details_table})
        return context


class OrganizationMembersTableView(LoginRequiredMixin, PermissionListMixin, DependingListView, OrganizationDetailContextMixin, CustomSingleTableMixin, FilterView):
    model = get_user_model()
    depending_model = Organization
    table_class = OrganizationMemberTable
    filterset_fields = {'username': ['icontains']}
    template_name = 'MrMap/detail_views/table_tab.html'
    permission_required = [PermissionEnum.CAN_VIEW_ORGANIZATION.value]
    object = None
    title = Tag(tag='i', attrs={"class": [IconEnum.PENDING_TASKS.value]}) + _(' Members')

    def get_queryset(self):
        return self.object.user_set.all()

    def get_table_kwargs(self):
        return {'organization': self.object}


class OrganizationPublishersTableView(LoginRequiredMixin, PermissionListMixin, DependingListView, OrganizationDetailContextMixin, CustomSingleTableMixin, FilterView):
    model = Organization
    depending_model = Organization
    table_class = OrganizationPublishersTable
    filterset_fields = {'organization_name': ['icontains']}
    template_name = 'MrMap/detail_views/table_tab.html'
    permission_required = [PermissionEnum.CAN_VIEW_ORGANIZATION.value]
    object = None
    title = Tag(tag='i', attrs={"class": [IconEnum.PUBLISHERS.value]}) + _(' Publish for list')

    def get_queryset(self):
        return Organization.objects.filter(can_publish_for__pk=self.object.pk)

    def get_table_kwargs(self):
        return {'organization': self.object}


class PendingTaskDelete(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = PendingTask
    success_url = reverse_lazy('resource:pending-tasks')
    template_name = 'generic_views/generic_confirm.html'
    permission_required = [PermissionEnum.CAN_DELETE_PENDING_TASK.value]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "action_url": self.object.remove_view_uri,
            "action": _l("Delete"),
            "msg": _l("Are you sure you want to delete " + self.object.__str__()) + "?"
        })
        return context


class ErrorReportDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = ErrorReport
    content_type = "text/plain"
    template_name = "structure/views/error-reports/error.txt"
    permission_required = [PermissionEnum.CAN_VIEW_PENDING_TASK.value]

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        response['Content-Disposition'] = f'attachment; filename="MrMap_error_report_{self.object.timestamp_now.strftime("%Y-%m-%dT%H:%M:%S")}.txt"'
        return response


class PublishRequestNewView(LoginRequiredMixin, PermissionRequiredMixin, GenericViewContextMixin, InitFormMixin, SuccessMessageMixin, CreateView):
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


class PublishRequestTableView(LoginRequiredMixin, PermissionListMixin, CustomSingleTableMixin, FilterView):
    model = PublishRequest
    table_class = PublishesRequestTable
    filterset_fields = ['group', 'organization', 'message']
    permission_required = [PermissionEnum.CAN_VIEW_PUBLISH_REQUEST.value]


class PublishRequestAcceptView(LoginRequiredMixin, PermissionRequiredMixin, GenericViewContextMixin, SuccessMessageMixin, InitFormMixin, UpdateView):
    model = PublishRequest
    template_name = "MrMap/detail_views/generic_form.html"
    success_url = reverse_lazy('structure:publish_request_overview')
    fields = ('is_accepted', )
    success_message = PUBLISH_REQUEST_ACCEPTED
    title = _('Accept request')
    permission_required = PermissionEnum.CAN_EDIT_PUBLISH_REQUEST.value
    raise_exception = True
    permission_denied_message = NO_PERMISSION

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
        except ValidationError as e:
            messages.error(self.request, e.message)
            response = HttpResponseRedirect(self.get_success_url())
        return response


class PublishRequestRemoveView(LoginRequiredMixin, PermissionRequiredMixin, GenericViewContextMixin, SuccessMessageMixin, DeleteView):
    model = PublishRequest
    template_name = "MrMap/detail_views/delete.html"
    success_url = reverse_lazy('structure:index')
    success_message = PUBLISH_REQUEST_DENIED
    title = _('Deny request')
    permission_required = PermissionEnum.CAN_DELETE_PUBLISH_REQUEST.value
    raise_exception = True
    permission_denied_message = NO_PERMISSION


class UserTableView(LoginRequiredMixin, CustomSingleTableMixin, FilterView):
    model = get_user_model()
    table_class = MrMapUserTable
    filterset_fields = {'username': ['icontains'],
                        'organization__organization_name': ['icontains'],
                        'groups__name': ['icontains']}
