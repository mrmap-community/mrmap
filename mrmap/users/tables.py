from main.tables.columns import DefaultActionButtonsColumn
from main.tables.template_code import VALUE_ABSOLUTE_LINK
import django_tables2 as tables
from main.tables.tables import SecuredTable
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from users.models import Subscription


class SubscriptionTable(SecuredTable):
    metadata = tables.TemplateColumn(template_code=VALUE_ABSOLUTE_LINK)
    actions = DefaultActionButtonsColumn(model=Subscription)

    class Meta:
        model = Subscription
        fields = ('metadata',
                  'notify_on_update',
                  'notify_on_metadata_edit',
                  'notify_on_access_edit')
        prefix = 'subscription-table'
