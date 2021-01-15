from django.urls import reverse
from django.utils.html import format_html
from django_bootstrap_swt.components import Link, Button, LinkButton, Tag
from django_tables2 import tables

from MrMap.columns import MrMapColumn
from MrMap.icons import IconEnum
from MrMap.tables import MrMapTable
from django.utils.translation import gettext_lazy as _

from MrMap.utils import get_theme, get_ok_nok_icon
from structure.models import MrMapGroup
from structure.permissionEnums import PermissionEnum


class EditorAcessTable(tables.Table):

    editor_group_name = MrMapColumn(
        accessor='name',
        verbose_name=_('Group Name'),
        empty_values=[],
        tooltip=_('The group for that the access is restricted or not.'),)

    editor_organization = MrMapColumn(
        accessor='organization',
        verbose_name=_('Organization'),
        empty_values=[],
        tooltip=_('The organization for that the access is restricted or not.'), )

    editor_access_allowed = MrMapColumn(
        accessor='id',
        verbose_name=_('Access allowed'),
        empty_values=[],
        tooltip=_('Boolean flag if the access is restricted or not.'), )

    editor_access_restricted_spatially = MrMapColumn(
        accessor='id',
        verbose_name=_('Access restricted spatially'),
        empty_values=[],
        tooltip=_('Boolean flag if the access is spatially restricted or not.'), )

    actions = MrMapColumn(
        verbose_name=_('Actions'),
        empty_values=[],
        orderable=False,
        tooltip=_('Actions you can perform'),
        attrs={"td": {"style": "white-space:nowrap;"}})

    """class Meta:
        model = MrMapGroup
        fields = ('status', 'service', 'phase', 'progress', 'actions')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'pending-task-table'
        orderable = False"""

    def __init__(self,
                 related_metadata,
                 *args,
                 **kwargs):
        self.related_metadata = related_metadata
        self.secured_operations = related_metadata.secured_operations.all()

        super(EditorAcessTable, self).__init__(*args, **kwargs)

    def render_editor_group_name(self, record):
        url = reverse('structure:detail-group', args=(record.id,))
        icon = ''
        tooltip = _('Click to open the detail view of <strong>{}</strong>'.format(record.name))
        if record.is_public_group:
            icon = Tag(tag='i', content=IconEnum.PUBLIC.value).render()
            tooltip = _('This is the anonymous public user group.') + " {}".format(tooltip)
        return Link(tooltip=tooltip,
                    url=url,
                    content=format_html("{} {}".format(icon, record.name)),
                    needs_perm=None,
                    open_in_new_tab=True, )

    def render_editor_organization(self, record):
        if record.organization:
            url = reverse('structure:detail-organization', args=(record.organization.id,))
            tooltip = _('Click to open the detail view of <strong>{}</strong>.'.format(record.organization.organization_name))
            return Link(tooltip=tooltip,
                        url=url,
                        content=record.organization.organization_name,
                        open_in_new_tab=True)
        else:
            return '-'

    def render_editor_access_allowed(self, value):
        group_access_on_metadata = self.secured_operations.filter(
            allowed_group__id=value
        )
        allowed = group_access_on_metadata.exists()

        return get_ok_nok_icon(allowed)

    def render_editor_access_restricted_spatially(self, value):
        group_access_on_metadata = self.secured_operations.filter(
            allowed_group__id=value
        ).exclude(
            bounding_geometry=None
        )
        allowed = group_access_on_metadata.exists()

        return get_ok_nok_icon(allowed)

    def render_editor_actions(self, record):
        btns = ''
        btns += LinkButton(
            url=reverse('editor:access_geometry_form', args=(self.related_metadata.id, record.id,)),
            color=get_theme(self.request.user)["TABLE"]["BTN_INFO_COLOR"],
            content=get_theme(self.request.user)["ICONS"]['EDIT'],
            needs_perm=PermissionEnum.CAN_EDIT_METADATA,
            tooltip=format_html(_(f"Edit access for group <strong>{record.name}</strong>"), ),
            tooltip_placement='left', )

        return format_html(btns)
