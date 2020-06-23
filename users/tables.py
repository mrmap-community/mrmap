from django.urls import reverse
from django.utils.html import format_html
from MrMap.columns import MrMapColumn
from MrMap.tables import MrMapTable
from django.utils.translation import gettext_lazy as _
from structure.models import Permission


class SubscriptionTable(MrMapTable):
    caption = _("Shows all datasets which are configured in your Mr. Map environment. You can Edit them if you want.")

    subscribed_services = MrMapColumn(verbose_name=_('Services'),
                                      tooltip=_('The subscribed services for this subscription'),
                                      empty_values=[],)
    subscription_actions = MrMapColumn(verbose_name=_('Actions'),
                                       tooltip=_('All actions you can do with the subscription'),
                                       empty_values=[],
                                       orderable=False)

    def render_subscription_actions(self, record):
        # ToDo 'editor:index' has to be a dynamic value from the current view where the user comes from
        edit_btn = self.get_edit_btn(href=reverse('editor:dataset-metadata-wizard-instance', args=('editor:index', record.id)),
                                     tooltip=format_html(_("Edit {} [{}] dataset"), record.title, record.id),
                                     tooltip_placement='left',
                                     permission=Permission())

        btns = format_html(edit_btn)

        return btns