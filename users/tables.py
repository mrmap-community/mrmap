from django.urls import reverse
from django.utils.html import format_html
from django_bootstrap_swt.components import Link
from django_bootstrap_swt.utils import RenderHelper
from django_tables2 import tables
from MrMap.columns import MrMapColumn
from MrMap.tables import MrMapTable
from django.utils.translation import gettext_lazy as _
from MrMap.utils import get_theme
from structure.models import MrMapUser
from structure.permissionEnums import PermissionEnum
from users.models import Subscription


class SubscriptionTable(tables.Table):
    render_helper = None
    actions = MrMapColumn(
        verbose_name=_('Actions'),
        tooltip=_('Actions to perform'),
        empty_values=[],
        orderable=False,
        attrs={"td": {"style": "white-space:nowrap;"}}
    )

    class Meta:
        model = Subscription
        fields = ('metadata',
                  'notify_on_update',
                  'notify_on_metadata_edit',
                  'notify_on_access_edit')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        # todo: set this prefix dynamic
        prefix = 'subscription-table'

    def before_render(self, request):
        self.render_helper = RenderHelper(user_permissions=list(filter(None, request.user.get_permissions())))

    def render_metadata(self, value):
        return Link(url=value.get_absolute_url(), content=value).render(safe=True)

    def render_actions(self, record):
        self.render_helper.update_attrs = {"class": ["btn-sm", "mr-1"]}
        renderd_actions = self.render_helper.render_list_coherent(items=record.get_actions())
        self.render_helper.update_attrs = None
        return format_html(renderd_actions)


class MrMapUserTable(MrMapTable):
    caption = _("Shows registered users.")

    username = MrMapColumn(
        accessor='username',
        verbose_name=_('Username'),
        tooltip=_('User`s name'),
        empty_values=[],
    )

    organization = MrMapColumn(
        accessor='organization__organization_name',
        verbose_name=_('Organization'),
        tooltip=_('User`s organization'),
        empty_values=[],
    )

    actions = MrMapColumn(
        verbose_name=_('Actions'),
        tooltip=_('Actions to perform'),
        empty_values=[],
        orderable=False,
        attrs={"td": {"style": "white-space:nowrap;"}}
    )

    def __init__(self, *args, **kwargs):
        self.group = None if "group" not in kwargs else kwargs.pop("group")
        super().__init__(query_class=MrMapUser, *args, **kwargs)
        self.is_group_detail_view = self.group is not None

    def render_actions(self, record):
        btns = ''

        if not self.is_group_detail_view and record != self.user:
            btns += format_html(self.get_btn(
                href=reverse('structure:invite-user-to-group', args=(record.id, ))+f"?current-view={self.current_view}",
                btn_color=get_theme(self.user)["TABLE"]["BTN_WARNING_COLOR"],
                btn_value=get_theme(self.user)["ICONS"]['GROUP'],
                permission=PermissionEnum.CAN_ADD_USER_TO_GROUP,
                tooltip=format_html(_("Add user to group"), ),
                tooltip_placement='left',
            ))

        if self.is_group_detail_view and record != self.user and self.group.created_by != record:
            # The user can't remove himself or the group creator!
            btns += format_html(self.get_btn(
                href=reverse('structure:remove-user-from-group', args=(self.group.id, record.id, ))+f"?current-view={self.current_view}",
                btn_color=get_theme(self.user)["TABLE"]["BTN_DANGER_COLOR"],
                btn_value=get_theme(self.user)["ICONS"]['SIGNOUT'],
                permission=PermissionEnum.CAN_ADD_USER_TO_GROUP,
                tooltip=format_html(_("Remove user from group"), ),
                tooltip_placement='left',
            ))

        return format_html(btns)