from django.urls import reverse
from django.utils.html import format_html
from django_bootstrap_swt.components import Link, LinkButton
from django_bootstrap_swt.enums import ButtonColorEnum
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


class MrMapUserTable(tables.Table):
    caption = _("Shows registered users.")

    class Meta:
        model = MrMapUser
        fields = ('username', 'organization')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
