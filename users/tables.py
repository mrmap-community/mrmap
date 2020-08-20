from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse
from django.utils.html import format_html
from MrMap.columns import MrMapColumn
from MrMap.tables import MrMapTable
from django.utils.translation import gettext_lazy as _
from MrMap.utils import get_ok_nok_icon, get_theme
from monitoring.models import Monitoring
from structure.models import Permission
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
            permission=Permission()
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
            href="#",
            btn_color=get_theme(self.user)["TABLE"]["BTN_INFO_COLOR"],
            btn_value=get_theme(self.user)["ICONS"]['HEARTBEAT'],
            permission=Permission(),
            tooltip=format_html(_("Run health check"), ),
            tooltip_placement='left',
        ))
        btns += format_html(self.get_btn(
            href=reverse('subscription-edit', args=(record.id,)) + f"?current-view={self.current_view}",
            btn_color=get_theme(self.user)["TABLE"]["BTN_WARNING_COLOR"],
            btn_value=get_theme(self.user)["ICONS"]['EDIT'],
            tooltip=format_html(_(f"Edit subscription for <strong>{record.metadata.title} [{record.metadata.id}]</strong>"), ),
            tooltip_placement='left',
            permission=Permission(),
        ))
        btns += format_html(self.get_btn(
            href=reverse('subscription-remove', args=(record.id, )) + f"?current-view={self.current_view}",
            btn_color=get_theme(self.user)["TABLE"]["BTN_DANGER_COLOR"],
            btn_value=get_theme(self.user)["ICONS"]['REMOVE'],
            tooltip=format_html(_(f"Remove subscription for <strong>{record.metadata.title} [{record.metadata.id}]</strong>"), ),
            tooltip_placement='left',
            permission=Permission(),
        ))


        return format_html(btns)

    def order_health(self, queryset, is_descending):
        # TODO:
        return queryset, True
