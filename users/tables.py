from django.urls import reverse
from django.utils.html import format_html
from MrMap.columns import MrMapColumn
from MrMap.tables import MrMapTable
from django.utils.translation import gettext_lazy as _
from structure.models import Permission


class SubscriptionTable(MrMapTable):
    caption = _("Shows your subscripted services.")

    subscribed_services = MrMapColumn(
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

    def render_subscription_actions(self, record):
        # ToDo 'editor:index' has to be a dynamic value from the current view where the user comes from
        edit_btn = self.get_edit_btn(
            href=reverse('editor:dataset-metadata-wizard-instance', args=('editor:index', record.id)),
            tooltip=format_html(_("Edit {} [{}] dataset"), record.title, record.id),
            tooltip_placement='left',
            permission=Permission()
        )

        btns = format_html(edit_btn)

        return btns