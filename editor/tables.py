from django.urls import reverse
from django.utils.html import format_html

from MrMap.columns import MrMapColumn
from MrMap.consts import construct_url
from MrMap.tables import MrMapTable
from django.utils.translation import gettext_lazy as _

from MrMap.utils import get_theme, get_ok_nok_icon
from structure.models import Permission


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
        accessor='allowed_operations',
        verbose_name=_('Access allowed'),
        empty_values=[],
        tooltip=_('Boolean flag if the access is restricted or not.'), )

    editor_access_restricted_spatially = MrMapColumn(
        accessor='allowed_operations',
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
        super(EditorAcessTable, self).__init__(*args, **kwargs)

    def render_editor_group_name(self, record):
        url = reverse('structure:detail-group', args=(record.id,))
        icon = ''
        tooltip = _(f'Click to open the detail view of <strong>{record.name}</strong>')
        if record.name == 'Public':
            icon = get_theme(self.user)['ICONS']['PUBLIC']
            tooltip = _('This is the anonymous public user group.') + f" {tooltip}"

        return construct_url(classes=get_theme(self.user)["TABLE"]["LINK_COLOR"],
                             href=url,
                             content=icon + ' ' + record.name,
                             tooltip=tooltip, )

    def render_editor_organization(self, record):
        if record.organization:
            url = reverse('structure:detail-organization', args=(record.organization.id,))
            tooltip = _(f'Click to open the detail view of <strong>{record.organization.organization_name}</strong>.')
            return construct_url(classes=get_theme(self.user)["TABLE"]["LINK_COLOR"],
                                 href=url,
                                 content=record.organization.organization_name,
                                 tooltip=tooltip, )
        else:
            return '-'

    @staticmethod
    def render_editor_access_allowed(value):
        allowed = False

        if value:
            # ToDo: check if the SecuredOperation Object is from type access allowed and set the allowed flag to True
            pass

        return get_ok_nok_icon(allowed)

    @staticmethod
    def render_editor_access_restricted_spatially(value):
        allowed = False

        if value:
            # ToDo: check if the SecuredOperation Object is from type access spatially allowed and set the allowed flag to True
            pass

        return get_ok_nok_icon(allowed)

    def render_editor_actions(self, record):
        btns = ''
        btns += self.get_btn(
            #ToDo: current-view-args should be in the table object passed from the constructor
            href=reverse('editor:access_geometry_form', args=(self.related_metadata.id, record.id,)) + f"?current-view={self.current_view}&current-view-arg={self.related_metadata.id}",
            btn_color=get_theme(self.user)["TABLE"]["BTN_INFO_COLOR"],
            btn_value=get_theme(self.user)["ICONS"]['EDIT'],
            permission=Permission(can_edit_metadata_service=True),
            tooltip=format_html(_(f"Edit access for group <strong>{record.name}</strong>"), ),
            tooltip_placement='left', )

        return format_html(btns)
