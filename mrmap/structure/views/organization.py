from django.utils.translation import gettext as _
from django.views.generic.base import ContextMixin
from main.enums.bootstrap import BadgeColorEnum
from django_filters.views import FilterView
from MrMap.messages import ORGANIZATION_SUCCESSFULLY_EDITED
from acl.models.acl import AccessControlList
from acl.tables import AccessControlListTable
from main.buttons import DefaultActionButtons
from main.views import SecuredDependingListMixin, SecuredListMixin, SecuredDetailView, SecuredUpdateView
from structure.forms import OrganizationChangeForm
from structure.models import Organization, PublishRequest
from structure.tables.tables import OrganizationTable, OrganizationDetailTable, OrganizationPublishersTable


class OrganizationDetailContextMixin(ContextMixin):
    object = None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tab_nav = [{'url': self.object.get_absolute_url,
                    'title': _('Details')},
                   {'url': self.object.publishers_uri,
                    'title': _('Publishers ').__str__() + f'<span class="badge {BadgeColorEnum.SECONDARY.value}">{self.object.get_publishers().count()}</span>'},
                   {'url': self.object.acls_uri,
                    'title': _('ACLs ').__str__() + f'<span class="badge {BadgeColorEnum.SECONDARY.value}">{self.object.get_acls().count()}</span>'}
                   ]
        context.update({"object": self.object,
                        'actions': [DefaultActionButtons(instance=self.object, request=self.request).render()],
                        'tab_nav': tab_nav,
                        'publisher_requests_count': PublishRequest.objects.filter(from_organization=self.object).count()})
        return context


class OrganizationTableView(SecuredListMixin, FilterView):
    model = Organization
    table_class = OrganizationTable
    filterset_fields = {'name': ['icontains'],
                        'description': ['icontains']}


class OrganizationDetailView(OrganizationDetailContextMixin, SecuredDetailView):
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
    form_class = OrganizationChangeForm
    success_message = ORGANIZATION_SUCCESSFULLY_EDITED


class OrganizationPublishersTableView(SecuredDependingListMixin, OrganizationDetailContextMixin, FilterView):
    model = Organization
    depending_model = Organization
    depending_field_name = 'can_publish_for'
    table_class = OrganizationPublishersTable
    filterset_fields = {'name': ['icontains']}
    template_name = 'MrMap/detail_views/table_tab.html'


class OrganizationAccessControlListTableView(SecuredDependingListMixin, OrganizationDetailContextMixin, FilterView):
    model = AccessControlList
    depending_model = Organization
    depending_field_name = 'owned_by_org'
    table_class = AccessControlListTable
    #filterset_fields = {'name': ['icontains']}
    """filterset_fields = {'name': ['icontains'],
                        'description': ['icontains'],
                        'owned_by_org': ['exact']}"""
    template_name = 'MrMap/detail_views/table_tab.html'
