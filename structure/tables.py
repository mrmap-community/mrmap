import django_tables2 as tables
from django.utils.html import format_html
from django.urls import reverse
from django_bootstrap_swt.components import Link, Tag, Badge, LinkButton, Button
from django_bootstrap_swt.enums import ButtonColorEnum, TooltipPlacementEnum
from django_bootstrap_swt.utils import RenderHelper

from MrMap.columns import MrMapColumn
from MrMap.icons import IconEnum
from MrMap.tables import MrMapTable
from MrMap.utils import get_theme, get_ok_nok_icon
from MrMap.consts import URL_PATTERN
from django.utils.translation import gettext_lazy as _

from structure.models import MrMapGroup, Organization, PublishRequest, MrMapUser
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
        url = reverse('structure:group_details', args=(record.id,))
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


class PublishesForTable(tables.Table):
    class Meta:
        model = Organization
        fields = ('organization_name',)
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        # todo: set this prefix dynamic
        prefix = 'publishers-for-table'

    def render_organization_name(self, record, value):
        return Link(url=record.detail_view_uri, content=value).render(safe=True)


class PublishesRequestTable(tables.Table):
    actions = MrMapColumn(
        verbose_name=_('Actions'),
        tooltip=_('Actions you can perform'),
        empty_values=[],
        orderable=False,
        attrs={"td": {"style": "white-space:nowrap;"}}
    )

    class Meta:
        model = PublishRequest
        fields = ('group', 'organization', 'message')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        # todo: set this prefix dynamic
        prefix = 'publishers-for-table'

    def before_render(self, request):
        self.render_helper = RenderHelper(user_permissions=list(filter(None, request.user.get_permissions())))

    def render_organization(self, value):
        return Link(url=value.detail_view_uri, content=value).render(safe=True)

    def render_group(self, value):
        return Link(url=value.detail_view_uri, content=value).render(safe=True)

    def render_actions(self, record):
        ok_icon = Tag(tag='i', attrs={"class": [IconEnum.OK.value]}).render()
        st_ok_text = Tag(tag='div', attrs={"class": ['d-lg-none']}, content=ok_icon).render()
        gt_ok_text = Tag(tag='div', attrs={"class": ['d-none', 'd-lg-block']},
                         content=ok_icon + _(' accept').__str__()).render()
        nok_icon = Tag(tag='i', attrs={"class": [IconEnum.NOK.value]}).render()
        st_nok_text = Tag(tag='div', attrs={"class": ['d-lg-none']}, content=nok_icon).render()
        gt_nok_text = Tag(tag='div', attrs={"class": ['d-none', 'd-lg-block']},
                          content=nok_icon + _(' deny').__str__()).render()

        actions = [

            LinkButton(url=f"{record.accept_publish_request_uri}?is_accepted=True",
                       content=st_ok_text+gt_ok_text,
                       color=ButtonColorEnum.SUCCESS),
            LinkButton(url=f"{record.accept_publish_request_uri}",
                       content=st_nok_text + gt_nok_text,
                       color=ButtonColorEnum.DANGER)

        ]
        self.render_helper.update_attrs = {"class": ["mr-1"]}
        rendered_items = format_html(self.render_helper.render_list_coherent(items=actions))
        self.render_helper.update_attrs = None
        return rendered_items


class PublishesForTableOld(MrMapTable):
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
        url = reverse('structure:group_details', args=(record.id,))
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


class GroupTable(tables.Table):
    actions = MrMapColumn(
        verbose_name=_('Actions'),
        tooltip=_('Actions you can perform'),
        empty_values=[],
        orderable=False,
        attrs={"td": {"style": "white-space:nowrap;"}}
    )

    class Meta:
        model = MrMapGroup
        fields = ('name', 'description', 'organization', 'actions')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        # todo: set this prefix dynamic
        prefix = 'mrmapgroup-table'

    caption = _("Shows all groups which are configured in your Mr. Map environment.")

    def before_render(self, request):
        self.render_helper = RenderHelper(user_permissions=list(filter(None, request.user.get_permissions())))

    def render_name(self, record, value):
        content = Tag(tag='i', attrs={"class": [IconEnum.PUBLIC.value]}) + ' ' + value if record.is_public_group else value
        return Link(url=record.detail_view_uri,
                    content=content,
                    tooltip=_('Click to open the detail view of <strong>{}</strong>').format(value)).render(safe=True)

    def render_organization(self, value):
        return Link(url=value.detail_view_uri,
                    content=value,
                    tooltip=_('Click to open the detail view of the organization')).render(safe=True)

    def render_actions(self, record):
        self.render_helper.update_attrs = {"class": ["btn-sm", "mr-1"]}
        renderd_actions = self.render_helper.render_list_coherent(items=record.get_actions())
        self.render_helper.update_attrs = None
        return format_html(renderd_actions)


class GroupDetailTable(tables.Table):
    inherited_permissions = tables.Column(verbose_name=_('Inherited Permissions'))

    class Meta:
        model = MrMapGroup
        fields = ('name', 'description', 'organization', 'permissions', 'inherited_permissions')
        template_name = "skeletons/django_tables2_vertical_table.html"
        # todo: set this prefix dynamic
        prefix = 'mrmapgroup-detail-table'
        orderable = False

    def before_render(self, request):
        self.render_helper = RenderHelper(user_permissions=list(filter(None, request.user.get_permissions())))

    def render_permissions(self, record):
        perms = []
        for perm in self.request.user.get_permissions(record):
            perms.append(Badge(content=perm if perm else _('None'), pill=True))

        self.render_helper.update_attrs = {"class": ["mr-1"]}
        renderd_perms = self.render_helper.render_list_coherent(items=perms)
        self.render_helper.update_attrs = None
        return format_html(renderd_perms)

    def render_inherited_permissions(self, record):
        inherited_permission = []
        parent = record.parent_group
        while parent is not None:
            permissions = self.request.user.get_permissions(parent)
            perm_dict = {
                "group": parent,
                "permissions": permissions,
            }
            inherited_permission.append(perm_dict)
            parent = parent.parent_group

        perms = []
        for perm in inherited_permission:
            perms.append(Badge(content=perm if perm else _('None'), pill=True))

        self.render_helper.update_attrs = {"class": ["mr-1"]}
        renderd_perms = self.render_helper.render_list_coherent(items=perms)
        self.render_helper.update_attrs = None
        return format_html(renderd_perms)


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


class MrMapUserTable(tables.Table):
    caption = _("Shows registered users.")
    actions = MrMapColumn(
        verbose_name=_('Actions'),
        tooltip=_('Actions to perform'),
        empty_values=[],
        orderable=False,
        attrs={"td": {"style": "white-space:nowrap;"}}
    )

    class Meta:
        model = MrMapUser
        fields = ('username', 'organization')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"

    def __init__(self, group: MrMapGroup, *args, **kwargs):
        self.group = group
        super().__init__(*args, **kwargs)

    def before_render(self, request):
        self.render_helper = RenderHelper(user_permissions=list(filter(None, request.user.get_permissions())))

    def render_actions(self, record):
        remove_icon = Tag(tag='i', attrs={"class": [IconEnum.DELETE.value]}).render()
        st_edit_text = Tag(tag='div', attrs={"class": ['d-lg-none']}, content=remove_icon).render()
        gt_edit_text = Tag(tag='div', attrs={"class": ['d-none', 'd-lg-block']},
                           content=remove_icon + _(' Remove').__str__()).render()

        btns = [
            LinkButton(url=self.group.remove_member_view_uri(record),
                       content=st_edit_text + gt_edit_text,
                       color=ButtonColorEnum.DANGER,
                       tooltip=_(f"Remove <strong>{record}</strong> from <strong>{self.group}</strong>"),
                       tooltip_placement=TooltipPlacementEnum.LEFT)
        ]
        return format_html(self.render_helper.render_list_coherent(items=btns))
