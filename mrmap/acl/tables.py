import django_tables2 as tables
from django.template import Template, Context
from django.utils.html import format_html
from acl.models.acl import AccessControlList
from main.tables.columns import DefaultActionButtonsColumn
from main.tables.template_code import RECORD_ABSOLUTE_LINK, VALUE_BADGE, VALUE_ABSOLUTE_LINK
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
        prefix = 'acl-table'

    def render_permissions(self, value):
        str = ''
        for perm in value.all():
            context = Context()
            context.update({'value': perm.name,
                            'color': 'badge-info'})
            str += Template(template_string=VALUE_BADGE).render(context=context)
        return format_html(str)

    def render_user_set(self, value):
        return value.count()
