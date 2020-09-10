import django_tables2 as tables
from django.utils.html import format_html
from django.urls import reverse

from MrMap.columns import MrMapColumn
from MrMap.tables import MrMapTable
from MrMap.utils import get_theme, get_ok_nok_icon
from MrMap.consts import URL_PATTERN
from django.utils.translation import gettext_lazy as _

from structure.permissionEnums import PermissionEnum


class PublisherTable(MrMapTable):
    class Meta:
        row_attrs = {
            "class": "text-center"
        }
    publisher_group = MrMapColumn(accessor='name', verbose_name=_('Group'))
    publisher_org = MrMapColumn(accessor='organization', verbose_name=_('Group organization'))
    publisher_action = MrMapColumn(
        verbose_name=_('Actions'),
        tooltip=_('Actions you can perform'),
        empty_values=[],
        orderable=False,
        attrs={"td": {"style": "white-space:nowrap;"}}
    )

    def __init__(self, *args, **kwargs):
        self.organization = None if "organization" not in kwargs else kwargs.pop("organization")
        super().__init__(*args, **kwargs)

    def render_publisher_group(self, value, record):
        """ Renders publisher_group as link to detail view of group

        Args:
            value:
            record:
        Returns:

        """
        url = reverse('structure:detail-group', args=(record.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )

    def render_publisher_org(self, value, record):
        """ Renders publisher_org as link to detail view of organization

        Args:
            value:
            record:
        Returns:

        """
        url = reverse('structure:detail-organization', args=(record.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )

    def render_publisher_action(self, record):
        btns = ''
        btns += format_html(self.get_btn(
            href=reverse('structure:remove-publisher', args=(self.organization.id, record.id,)) + f"?current-view={self.current_view}&current-view-arg={self.organization.id}",
            btn_color=get_theme(self.user)["TABLE"]["BTN_DANGER_COLOR"],
            btn_value=get_theme(self.user)["ICONS"]['REMOVE'],
            tooltip=format_html(_("Remove <strong>{}</strong> as publisher").format(record.name), ),
            tooltip_placement='left',
            permission=PermissionEnum.CAN_TOGGLE_PUBLISH_REQUESTS,
        ))
        return format_html(btns)


class PublishesForTable(MrMapTable):
    class Meta:
        row_attrs = {
            "class": "text-center"
        }
    publisher_org = tables.Column(accessor='organization_name', verbose_name=_('Organization'))
    publisher_action = tables.TemplateColumn(
        template_name="includes/detail/publisher_requests_accept_reject.html",
        verbose_name=_('Action'),
        orderable=False,
        extra_context={
            "remove_publisher": True,
            "publishes_for": True,
        }
    )

    def render_publisher_org(self, value, record):
        """ Renders publisher_org as link to detail view of organization

        Args:
            value:
            record:
        Returns:

        """
        url = reverse('structure:detail-organization', args=(record.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )


class PublisherRequestTable(MrMapTable):
    class Meta:
        row_attrs = {
            "class": "text-center"
        }
    publisher_group = tables.Column(accessor='group', verbose_name=_('Group'))
    publisher_org = tables.Column(accessor='group.organization', verbose_name=_('Group organization'))
    message = tables.Column(accessor='message', verbose_name=_('Message'))
    activation_until = tables.Column(accessor='activation_until', verbose_name=_('Activation until'))
    publisher_action = tables.TemplateColumn(
        template_name="includes/detail/publisher_requests_accept_reject.html",
        verbose_name=_('Action'),
        orderable=False,
        extra_context={
        }
    )

    def render_publisher_group(self, value, record):
        """ Renders publisher_group as link to detail view of group

        Args:
            value:
            record:
        Returns:

        """
        url = reverse('structure:detail-group', args=(record.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )

    def render_publisher_org(self, value, record):
        """ Renders publisher_org as link to detail view of organization

        Args:
            value:
            record:
        Returns:

        """
        url = reverse('structure:detail-organization', args=(record.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )


class GroupTable(MrMapTable):
    groups_name = MrMapColumn(
        accessor='name',
        verbose_name=_('Name'),
        tooltip=_("The name of the group"),)
    groups_description = MrMapColumn(
        accessor='description',
        verbose_name=_('Description'),
        tooltip=_("The description of the group"),)
    groups_organization = MrMapColumn(
        accessor='organization.organization_name',
        verbose_name=_('Organization'),
        tooltip=_("The organization wich is the home organization of the group"),)
    groups_actions = MrMapColumn(
        verbose_name=_('Actions'),
        tooltip=_('Actions you can perform'),
        empty_values=[],
        orderable=False,
        attrs={"td": {"style": "white-space:nowrap;"}}
    )

    caption = _("Shows all groups which are configured in your Mr. Map environment.")

    def render_groups_name(self, value, record):
        url = reverse('structure:detail-group', args=(record.id,))
        icon = ''
        value = _(value)
        tooltip = _('Click to open the detail view of <strong>{}</strong>').format(value)
        if record.is_public_group:
            icon = get_theme(self.user)['ICONS']['PUBLIC']
            tooltip = _('This is the anonymous public user group.') + f" {tooltip}"
        return self.get_link(tooltip=tooltip,
                             href=url,
                             value=format_html(f"{icon} {value}"),
                             permission=None,
                             open_in_new_tab=False, )

    @staticmethod
    def render_groups_description(value, record):
        value = _(value)
        return value

    def render_groups_organization(self, value, record):
        return self.get_link(tooltip=_('Click to open the detail view of the organization'),
                             href=reverse('structure:detail-organization', args=(record.organization.id,)),
                             value=value,
                             permission=None,
                             open_in_new_tab=False, )

    def render_groups_actions(self, record):
        btns = ''
        if not record.is_public_group:
            btns += format_html(self.get_btn(
                href=reverse('structure:leave-group', args=(record.id,)) + f"?current-view={self.current_view}",
                btn_color=get_theme(self.user)["TABLE"]["BTN_WARNING_COLOR"],
                btn_value=get_theme(self.user)["ICONS"]['SIGNOUT'],
                tooltip=format_html(_("Leave <strong>{}</strong>").format(record.name), ),
                tooltip_placement='left',
                permission=PermissionEnum.CAN_DELETE_GROUP,
            ))
        btns += format_html(self.get_btn(
            href=reverse('structure:edit-group', args=(record.id,)) + f"?current-view={self.current_view}",
            btn_color=get_theme(self.user)["TABLE"]["BTN_WARNING_COLOR"],
            btn_value=get_theme(self.user)["ICONS"]['EDIT'],
            tooltip=format_html(_("Edit <strong>{}</strong>").format(record.name), ),
            tooltip_placement='left',
            permission=PermissionEnum.CAN_EDIT_GROUP,
        ))
        if not record.is_permission_group:
            btns += format_html(self.get_btn(
                href=reverse('structure:delete-group', args=(record.id,)) + f"?current-view={self.current_view}",
                btn_color=get_theme(self.user)["TABLE"]["BTN_DANGER_COLOR"],
                btn_value=get_theme(self.user)["ICONS"]['REMOVE'],
                tooltip=format_html(_(f"Remove <strong>{record.name} [{record.id}]</strong> group"), ),
                tooltip_placement='left',
                permission=PermissionEnum.CAN_DELETE_GROUP,
            ))
        return format_html(btns)


class OrganizationTable(MrMapTable):
    orgs_organization_name = MrMapColumn(
        accessor='organization_name',
        verbose_name=_('Name'),
        tooltip=_('Name of the given organizations'),)
    orgs_description = MrMapColumn(
        accessor='description',
        verbose_name=_('Description'),
        tooltip=_('Description of the given organizations'),)
    orgs_is_auto_generated = MrMapColumn(
        accessor='is_auto_generated',
        verbose_name=_('Real organization'),
        tooltip=_('If an organization comes from the capabilities, it will be marked as autogenerated'),)
    orgs_parent = MrMapColumn(
        accessor='parent',
        verbose_name=_('Parent'),
        tooltip=_('Parent organizations of the given organization'),)
    orgs_actions = MrMapColumn(
        verbose_name=_('Actions'),
        tooltip=_('Actions you can perform'),
        empty_values=[],
        orderable=False,
        attrs={"td": {"style": "white-space:nowrap;"}},)

    caption = _("Shows all organizations which are configured in your Mr. Map environment.")

    def render_orgs_organization_name(self, value, record):
        url = reverse('structure:detail-organization', args=(record.id,))
        icon = ''
        tooltip = _('Click to open the detail view of <strong>{}</strong>.').format(value)
        if self.user.organization is not None and self.user.organization == record:
            icon = get_theme(self.user)['ICONS']['HOME']
            tooltip = _('This is your organization.') + ' {}'.format(tooltip)
        return self.get_link(tooltip=tooltip,
                             href=url,
                             value=format_html("{} {}".format(icon, value)),
                             permission=None,
                             open_in_new_tab=False, )

    @staticmethod
    def render_orgs_is_auto_generated(value):
        """ Preprocessing for rendering of is_auto_generated value.

        Due to semantic reasons, we invert this value.

        Args:
            value: The value
        Returns:

        """
        val = not value
        return get_ok_nok_icon(val)

    def render_orgs_actions(self, record):
        btns = ''
        btns += format_html(self.get_btn(
            href=reverse('structure:edit-organization', args=(record.id,)) + f"?current-view={self.current_view}",
            btn_color=get_theme(self.user)["TABLE"]["BTN_WARNING_COLOR"],
            btn_value=get_theme(self.user)["ICONS"]['EDIT'],
            tooltip=format_html(_(f"Edit <strong>{record.organization_name} [{record.id}]</strong> organization"), ),
            tooltip_placement='left',
            permission=PermissionEnum.CAN_EDIT_ORGANIZATION,
        ))
        btns += format_html(self.get_btn(
            href=reverse('structure:publish-request', args=(record.id,)) + f"?current-view={self.current_view}",
            btn_color=get_theme(self.user)["TABLE"]["BTN_SECONDARY_COLOR"],
            btn_value=get_theme(self.user)["ICONS"]['PUBLISHER'],
            tooltip=format_html(
                _(f"Become publisher for organization <strong>{record.organization_name} [{record.id}]</strong>"), ),
            tooltip_placement='left',
            permission=PermissionEnum.CAN_REQUEST_TO_BECOME_PUBLISHER,
        ))
        btns += format_html(self.get_btn(
            href=reverse('structure:delete-organization', args=(record.id,)) + f"?current-view={self.current_view}",
            btn_color=get_theme(self.user)["TABLE"]["BTN_DANGER_COLOR"],
            btn_value=get_theme(self.user)["ICONS"]['REMOVE'],
            tooltip=format_html(_(f"Remove <strong>{record.organization_name} [{record.id}]</strong> organization"), ),
            tooltip_placement='left',
            permission=PermissionEnum.CAN_DELETE_ORGANIZATION,
        ))
        return format_html(btns)
