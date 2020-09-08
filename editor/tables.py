from django.urls import reverse
from django.utils.html import format_html

from MrMap.columns import MrMapColumn
from MrMap.tables import MrMapTable
from django.utils.translation import gettext_lazy as _

from MrMap.utils import get_theme, get_ok_nok_icon
from structure.permissionEnums import PermissionEnum


class EditorAcessTable(MrMapTable):

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

    editor_actions = MrMapColumn(
        verbose_name=_('Actions'),
        empty_values=[],
        orderable=False,
        tooltip=_('Actions you can perform'),
        attrs={"td": {"style": "white-space:nowrap;"}})

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
            icon = get_theme(self.user)['ICONS']['PUBLIC']
            tooltip = _('This is the anonymous public user group.') + " {}".format(tooltip)
        return self.get_link(tooltip=tooltip,
                             href=url,
                             value=format_html("{} {}".format(icon, record.name)),
                             permission=None,
                             open_in_new_tab=True, )

    def render_editor_organization(self, record):
        if record.organization:
            url = reverse('structure:detail-organization', args=(record.organization.id,))
            tooltip = _('Click to open the detail view of <strong>{}</strong>.'.format(record.organization.organization_name))
            return self.get_link(tooltip=tooltip,
                                 href=url,
                                 value=record.organization.organization_name,
                                 permission=None,
                                 open_in_new_tab=True, )
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
        btns += self.get_btn(
            #ToDo: current-view-args should be in the table object passed from the constructor
            href=reverse('editor:access_geometry_form', args=(self.related_metadata.id, record.id,)) + f"?current-view={self.current_view}&current-view-arg={self.related_metadata.id}",
            btn_color=get_theme(self.user)["TABLE"]["BTN_INFO_COLOR"],
            btn_value=get_theme(self.user)["ICONS"]['EDIT'],
            permission=PermissionEnum.CAN_EDIT_METADATA,
            tooltip=format_html(_(f"Edit access for group <strong>{record.name}</strong>"), ),
            tooltip_placement='left', )

        return format_html(btns)
