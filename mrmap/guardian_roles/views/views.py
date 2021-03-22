from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.messages.views import SuccessMessageMixin
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.views.generic import DetailView, UpdateView
from django_filters.views import FilterView
from guardian.mixins import PermissionRequiredMixin

from MrMap.icons import get_icon, IconEnum
from MrMap.views import CustomSingleTableMixin, GenericViewContextMixin, DependingListView, InitFormMixin
from guardian_roles.enums import PermissionEnum
from guardian_roles.forms import UserSetChangeForm
from guardian_roles.messages import ROLE_SUCCESSFULLY_EDITED
from guardian_roles.models.core import OrganizationBasedTemplateRole
from guardian_roles.tables.tables import OrganizationBasedTemplateRoleTable, OrganizationBasedTemplateRoleDetailTable, \
    OrganizationBasedTemplateRoleMemberTable
from guardian_roles.views.mixins import OrganizationBasedTemplateRoleDetailContextMixin


@method_decorator(login_required, name='dispatch')
class OrganizationBasedTemplateRoleView(CustomSingleTableMixin, FilterView):
    model = OrganizationBasedTemplateRole
    table_class = OrganizationBasedTemplateRoleTable
    title = _('Roles').__str__()


@method_decorator(login_required, name='dispatch')
class OrganizationBasedTemplateRoleDetailView(GenericViewContextMixin, OrganizationBasedTemplateRoleDetailContextMixin, DetailView):
    class Meta:
        verbose_name = _('Details')

    model = OrganizationBasedTemplateRole
    template_name = 'MrMap/detail_views/table_tab.html'
    queryset = OrganizationBasedTemplateRole.objects.all()
    title = _('Details')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        details_table = OrganizationBasedTemplateRoleDetailTable(data=[self.object, ], request=self.request)
        context.update({'table': details_table})
        return context


@method_decorator(login_required, name='dispatch')
class OrganizationBasedTemplateRoleChangeView(PermissionRequiredMixin, InitFormMixin, GenericViewContextMixin, SuccessMessageMixin, UpdateView):
    template_name = 'MrMap/detail_views/generic_form.html'
    success_message = ROLE_SUCCESSFULLY_EDITED
    model = OrganizationBasedTemplateRole
    form_class = UserSetChangeForm
    title = _('Edit Role')
    permission_required = PermissionEnum.CAN_EDIT_ORGANIZATION.value
    #  raise_exception = True
    #  permission_denied_message = NO_PERMISSION

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"request": self.request})
        return kwargs


@method_decorator(login_required, name='dispatch')
class OrganizationBasedTemplateRoleMembersTableView(DependingListView, OrganizationBasedTemplateRoleDetailContextMixin, CustomSingleTableMixin, FilterView):
    model = get_user_model()
    depending_model = OrganizationBasedTemplateRole
    table_class = OrganizationBasedTemplateRoleMemberTable
    filterset_fields = {'username': ['icontains']}
    template_name = 'MrMap/detail_views/table_tab.html'
    object = None
    title = get_icon(IconEnum.GROUP) + _(' Members')

    def get_queryset(self):
        return self.object.user_set.all()
