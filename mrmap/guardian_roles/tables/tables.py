import django_tables2 as tables
from django_bootstrap_swt.utils import RenderHelper

from MrMap.tables import ActionTableMixin
from guardian_roles.models.core import OrganizationBasedTemplateRole
from guardian_roles.tables.template_code import ABSOLUTE_LINK
from structure.models import MrMapUser


class OrganizationBasedTemplateRoleTable(tables.Table):
    name = tables.TemplateColumn(
        template_code=ABSOLUTE_LINK,
    )

    class Meta:
        model = OrganizationBasedTemplateRole
        fields = ('name', 'description')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'role-table'


class OrganizationBasedTemplateRoleDetailTable(tables.Table):

    class Meta:
        model = OrganizationBasedTemplateRole
        fields = ('name', 'description')
        template_name = "skeletons/django_tables2_vertical_table.html"
        prefix = 'role-detail-table'
        orderable = False


class OrganizationBasedTemplateRoleMemberTable(tables.Table):
    class Meta:
        model = MrMapUser
        fields = ('username', )
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
