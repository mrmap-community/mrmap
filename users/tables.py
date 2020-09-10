from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse
from django.utils.html import format_html
from MrMap.columns import MrMapColumn
from MrMap.tables import MrMapTable
from django.utils.translation import gettext_lazy as _
from MrMap.utils import get_ok_nok_icon, get_theme
from monitoring.models import Monitoring
from structure.models import MrMapUser

from structure.permissionEnums import PermissionEnum
from users.models import Subscription


class SubscriptionTable(MrMapTable):
    caption = _("Shows your subscripted services.")

    subscribed_services = MrMapColumn(
        accessor='metadata',
        verbose_name=_('Services'),
        tooltip=_('Subscribed services'),
        empty_values=[],
    )
    notify_on_update = MrMapColumn(
        verbose_name=_('Update notification'),
        tooltip=_('Notify on any service update'),
        empty_values=[],
        orderable=True,
    )
    notify_on_metadata_edit = MrMapColumn(
        verbose_name=_('Change notification'),
        tooltip=_('Notify on changed service metadata'),
        empty_values=[],
        orderable=True,
    )
    notify_on_access_edit = MrMapColumn(
        verbose_name=_('Access notification'),
        tooltip=_('Notify on changed service access'),
        empty_values=[],
        orderable=True,
    )
    health = MrMapColumn(
        verbose_name=_('Health'),
        tooltip=_('Health state of the ressource'),
        empty_values=[False,],
        orderable=False,
    )
    actions = MrMapColumn(
        verbose_name=_('Actions'),
        tooltip=_('Actions to perform'),
        empty_values=[],
        orderable=False,
        attrs={"td": {"style": "white-space:nowrap;"}}
    )

    def __init__(self, *args, **kwargs):
        super(SubscriptionTable, self).__init__(query_class=Subscription, *args, **kwargs)

    def render_subscribed_services(self, record, value):
        return format_html(self.get_link(
            href=reverse('resource:detail', args=(record.metadata.id,)),
            value=value,
            tooltip=format_html(
                _(f"Go to the detail view of service <strong>{record.metadata.title} [{record.metadata.id}]</strong>"), ),
            tooltip_placement='left',
            permission=None
        ))

    @staticmethod
    def render_notify_on_update(value):
        return get_ok_nok_icon(value)

    @staticmethod
    def render_notify_on_metadata_edit(value):
        return get_ok_nok_icon(value)

    @staticmethod
    def render_notify_on_access_edit(value):
        return get_ok_nok_icon(value)

    def render_health(self, record):
        try:
            last_monitoring_object = Monitoring.objects.filter(metadata=record.metadata).order_by('-timestamp').first()
        except ObjectDoesNotExist:
            last_monitoring_object = None

        icons = ''
        if last_monitoring_object:
            if last_monitoring_object.available:
                icon_color = 'text-success'
            else:
                icon_color = 'text-danger'
            icons += self.get_icon(icon_color=icon_color,
                                   icon=get_theme(self.user)["ICONS"]["HEARTBEAT"],
                                   tooltip=_(f'Last check runs on {last_monitoring_object.timestamp}'))
        else:
            icons += self.get_icon(icon_color='text-secondary',
                                   icon=get_theme(self.user)["ICONS"]["HEARTBEAT"],
                                   tooltip=_(f'Last check state is unknown'))

        return format_html(icons)

    def render_actions(self, record):
        btns = ''
        btns += format_html(self.get_btn(
            href=reverse('monitoring:run-monitoring', args=(record.metadata.id, ))+f"?current-view={self.current_view}",
            btn_color=get_theme(self.user)["TABLE"]["BTN_INFO_COLOR"],
            btn_value=get_theme(self.user)["ICONS"]['HEARTBEAT'],
            permission=PermissionEnum.CAN_RUN_MONITORING,
            tooltip=format_html(_("Run health check"), ),
            tooltip_placement='left',
        ))
        btns += format_html(self.get_btn(
            href=reverse('subscription-edit', args=(record.id,)) + f"?current-view={self.current_view}",
            btn_color=get_theme(self.user)["TABLE"]["BTN_WARNING_COLOR"],
            btn_value=get_theme(self.user)["ICONS"]['EDIT'],
            tooltip=format_html(_(f"Edit subscription for <strong>{record.metadata.title} [{record.metadata.id}]</strong>"), ),
            tooltip_placement='left',
            permission=None,
        ))
        btns += format_html(self.get_btn(
            href=reverse('subscription-remove', args=(record.id, )) + f"?current-view={self.current_view}",
            btn_color=get_theme(self.user)["TABLE"]["BTN_DANGER_COLOR"],
            btn_value=get_theme(self.user)["ICONS"]['REMOVE'],
            tooltip=format_html(_(f"Remove subscription for <strong>{record.metadata.title} [{record.metadata.id}]</strong>"), ),
            tooltip_placement='left',
            permission=None,
        ))

        return format_html(btns)

    def order_health(self, queryset, is_descending):
        # TODO:
        return queryset, True


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