from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import format_html

from MrMap.columns import MrMapColumn
from MrMap.consts import BTN_SM_CLASS
from MrMap.tables import MrMapTable
from django.utils.translation import gettext_lazy as _

from MrMap.utils import get_theme


class SubscriptionTable(MrMapTable):
    caption = _("Shows all datasets which are configured in your Mr. Map environment. You can Edit them if you want.")
    subscription_actions = MrMapColumn(verbose_name=_('Actions'), empty_values=[], orderable=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def render_subscription_actions(self, record):
        # ToDo: only add buttons if the user has the permission for it
        context_edit_btn = {
            "btn_size": BTN_SM_CLASS,
            "btn_color": get_theme(self.user)["TABLE"]["BTN_WARNING_COLOR"],
            "btn_value": get_theme(self.user)["ICONS"]['EDIT'],
            # ToDo 'editor:index' has to be a dynamic value from the current view where the user comes from
            "btn_url": reverse('editor:dataset-metadata-wizard-instance', args=('editor:index', record.id)),
            "tooltip": format_html(_("Edit {} [{}] dataset"), record.title, record.id),
            "tooltip_placement": "left",
        }
        edit_btn = render_to_string(template_name="sceletons/open-link-button.html",
                                    context=context_edit_btn)

        btns = format_html(edit_btn)

        return btns