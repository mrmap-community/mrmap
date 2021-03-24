from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Case, When
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _l
from django.utils.translation import gettext as _
from django.views.generic.base import ContextMixin
from django_bootstrap_swt.components import Tag, Badge
from django_bootstrap_swt.enums import BadgeColorEnum
from django_filters.views import FilterView
from guardian.mixins import LoginRequiredMixin
from MrMap.icons import IconEnum
from MrMap.messages import PUBLISH_REQUEST_DENIED, PUBLISH_REQUEST_ACCEPTED, \
    PUBLISH_REQUEST_SENT, ORGANIZATION_SUCCESSFULLY_EDITED
from MrMap.views import CustomSingleTableMixin
from main.buttons import DefaultActionButtons
from main.views import SecuredDependingListMixin, SecuredListMixin, SecuredDetailView, SecuredDeleteView, \
    SecuredCreateView, SecuredUpdateView
from structure.forms import OrganizationChangeForm
from structure.permissionEnums import PermissionEnum
from structure.models import Organization, PendingTask, ErrorReport, PublishRequest
from structure.tables.tables import OrganizationTable, \
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
                        'actions': [DefaultActionButtons(instance=self.object, request=self.request).render()],
                        'tab_nav': tab_nav,
                        'publisher_requests_count': PublishRequest.objects.filter(from_organization=self.object).count()})
        return context


class OrganizationTableView(SecuredListMixin, FilterView):
    model = Organization
    table_class = OrganizationTable
    filterset_fields = {'organization_name': ['icontains'],
                        'description': ['icontains']}

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.order_by(
            Case(When(id=self.request.user.organization.id if self.request.user.organization is not None else 0, then=0), default=1),
            'organization_name')
        return queryset


class OrganizationDetailView(OrganizationDetailContextMixin, SecuredDetailView):
    class Meta:
        verbose_name = _('Details')

    model = Organization
    template_name = 'MrMap/detail_views/table_tab.html'
    title = _('Details')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        details_table = OrganizationDetailTable(data=[self.object, ], request=self.request)
        context.update({'table': details_table})
        return context


class OrganizationUpdateView(SecuredUpdateView):
    model = Organization
    template_name = "MrMap/detail_views/generic_form.html"
    form_class = OrganizationChangeForm
    success_message = ORGANIZATION_SUCCESSFULLY_EDITED
    title = _('Edit organization')


class OrganizationMembersTableView(OrganizationDetailContextMixin, SecuredDependingListMixin, FilterView):
    model = get_user_model()
    depending_model = Organization
    table_class = OrganizationMemberTable
    filterset_fields = {'username': ['icontains']}
    template_name = 'MrMap/detail_views/table_tab.html'
    title = Tag(tag='i', attrs={"class": [IconEnum.PENDING_TASKS.value]}) + _(' Members')

    def get_queryset(self):
        return self.object.user_set.all()

    def get_table_kwargs(self):
        return {'organization': self.object}


class OrganizationPublishersTableView(SecuredDependingListMixin, OrganizationDetailContextMixin, FilterView):
    model = Organization
    depending_model = Organization
    table_class = OrganizationPublishersTable
    filterset_fields = {'organization_name': ['icontains']}
    template_name = 'MrMap/detail_views/table_tab.html'
    title = Tag(tag='i', attrs={"class": [IconEnum.PUBLISHERS.value]}) + _(' Publish for list')

    def get_queryset(self):
        return Organization.objects.filter(can_publish_for__pk=self.object.pk)

    def get_table_kwargs(self):
        return {'organization': self.object}


class PendingTaskDelete(SecuredDeleteView):
    model = PendingTask
    success_url = reverse_lazy('resource:pending-tasks')
    template_name = 'generic_views/generic_confirm.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "action_url": self.object.remove_view_uri,
            "action": _l("Delete"),
            "msg": _l("Are you sure you want to delete " + self.object.__str__()) + "?"
        })
        return context


class ErrorReportDetailView(SecuredDetailView):
    model = ErrorReport
    content_type = "text/plain"
    template_name = "structure/views/error-reports/error.txt"

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        response['Content-Disposition'] = f'attachment; filename="MrMap_error_report_{self.object.timestamp_now.strftime("%Y-%m-%dT%H:%M:%S")}.txt"'
        return response


class PublishRequestNewView(SecuredCreateView):
    model = PublishRequest
    fields = ('from_organization', 'to_organization', 'message')
    template_name = 'MrMap/detail_views/generic_form.html'
    title = _('Publish request')
    success_message = PUBLISH_REQUEST_SENT


class PublishRequestTableView(SecuredListMixin, FilterView):
    model = PublishRequest
    table_class = PublishesRequestTable
    filterset_fields = ['from_organization', 'to_organization', 'message']
    permission_required = [PermissionEnum.CAN_VIEW_PUBLISH_REQUEST.value]


class PublishRequestUpdateView(SecuredUpdateView):
    model = PublishRequest
    template_name = "MrMap/detail_views/generic_form.html"
    success_url = reverse_lazy('structure:publish_request_overview')
    fields = ('is_accepted', )
    success_message = PUBLISH_REQUEST_ACCEPTED
    title = _('Accept request')


class PublishRequestRemoveView(SecuredDeleteView):
    model = PublishRequest
    template_name = "MrMap/detail_views/delete.html"
    success_url = reverse_lazy('structure:index')
    success_message = PUBLISH_REQUEST_DENIED
    title = _('Deny request')


class UserTableView(LoginRequiredMixin, CustomSingleTableMixin, FilterView):
    model = get_user_model()
    table_class = MrMapUserTable
    filterset_fields = {'username': ['icontains'],
                        'organization__organization_name': ['icontains'],
                        'groups__name': ['icontains']}
