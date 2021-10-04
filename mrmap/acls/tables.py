import django_tables2 as tables
from django.template import Template, Context
from django.utils.html import format_html
from acls.models.acls import AccessControlList
from extras.tables.columns import DefaultActionButtonsColumn
from extras.tables.template_code import RECORD_ABSOLUTE_LINK, VALUE_BADGE, VALUE_ABSOLUTE_LINK, VALUE_BADGE_LIST, \
    VALUE_TABLE_LINK_LIST
from django.utils.translation import gettext as _


class AccessControlListTable(tables.Table):
    name = tables.TemplateColumn(template_code=RECORD_ABSOLUTE_LINK)
    user_set = tables.Column(verbose_name=_('Users'))
    owned_by_org = tables.TemplateColumn(template_code=VALUE_ABSOLUTE_LINK)
    actions = DefaultActionButtonsColumn(model=AccessControlList)

    class Meta:
        model = AccessControlList
        fields = ('name', 'description', 'permissions', 'user_set', 'owned_by_org')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'acls-table'

    def render_permissions(self, value):
        str = ''
        for perm in value.all():
            context = Context()
            context.update({'value': perm.name,
                            'color': 'bg-info'})
            str += Template(template_string=VALUE_BADGE).render(context=context)
        return format_html(str)

    def render_user_set(self, value):
        return value.count()


class AccessControlListDetailTable(tables.Table):
    name = tables.TemplateColumn(template_code=RECORD_ABSOLUTE_LINK)
    user_set__all = tables.TemplateColumn(template_code=VALUE_TABLE_LINK_LIST, verbose_name=_('Users'))
    permissions__all = tables.TemplateColumn(template_code=VALUE_BADGE_LIST, verbose_name=_('Allowed permissions'))
    # accessible_metadata__all = tables.TemplateColumn(template_code=VALUE_TABLE_LINK_LIST, verbose_name=_('Accessible resources'))
    accessible_accesscontrollist__all = tables.TemplateColumn(template_code=VALUE_TABLE_LINK_LIST, verbose_name=_('Accessible access control lists'))
    accessible_organizations__all = tables.TemplateColumn(template_code=VALUE_TABLE_LINK_LIST, verbose_name=_('Accessible organizations'))

    class Meta:
        model = AccessControlList
        fields = ('name',
                  'uuid',
                  'description',
                  'user_set__all',
                  'permissions__all',
                  # 'accessible_metadata__all',
                  'accessible_accesscontrollist__all',
                  'accessible_organizations__all',
                  'default_acl')
        template_name = "skeletons/django_tables2_vertical_table.html"
        prefix = 'acls-detail-table'
        orderable = False
