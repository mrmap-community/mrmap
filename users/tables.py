from django.urls import reverse
from django.utils.html import format_html
from MrMap.columns import MrMapColumn
from MrMap.consts import URL_PATTERN
from MrMap.tables import MrMapTable
from django.utils.translation import gettext_lazy as _

from MrMap.utils import get_theme
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
    actions = MrMapColumn(
        verbose_name=_('Actions'),
        tooltip=_('Actions to perform'),
        empty_values=[],
        orderable=False
    )

    def __init__(self, *args, **kwargs):
        super(SubscriptionTable, self).__init__(query_class=Subscription, *args, **kwargs)

    def render_subscribed_services(self, record, value):
        url = reverse('service:detail', args=(record.metadata.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )

    def render_actions(self, record):
        return format_html(self.get_edit_btn(
            href=reverse('subscription-edit', args=(record.id, self.current_view)),
            tooltip=format_html(_(f"Edit subscription {record.metadata.title} [{record.metadata.id}] dataset"),),
            tooltip_placement='left',
            permission=Permission()
        ))
