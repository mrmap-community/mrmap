from django.contrib.auth import get_user_model
from extras.tables.columns import DefaultActionButtonsColumn
from extras.tables.template_code import VALUE_ABSOLUTE_LINK
import django_tables2 as tables
from extras.tables.tables import SecuredTable
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


class MrMapUserTable(tables.Table):
    class Meta:
        model = get_user_model()
        fields = ('username', 'organization', 'groups', 'is_superuser')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
