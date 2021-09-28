import django_tables2 as tables
import urllib3.util

from extras.tables.tables import SecuredTable
from extras.tables.template_code import DEFAULT_ACTION_BUTTONS, VALUE_ABSOLUTE_LINK, VALUE_TABLE_LINK, \
    VALUE_TABLE_LINK_LIST, VALUE_CONCRETE_TABLE_LINK
from registry.models.security import AllowedOperation, ServiceAccessGroup, AnalyzedResponseLog, ExternalAuthentication, \
    ProxySetting
from django.utils.translation import gettext_lazy as _
from leaflet.forms.fields import GeometryField
from leaflet.forms.widgets import LeafletWidget
from django.utils.safestring import mark_safe


class ExternalAuthenticationTable(SecuredTable):
    perm_checker = None
    secured_service = tables.TemplateColumn(template_code=VALUE_TABLE_LINK)
    actions = tables.TemplateColumn(verbose_name=_('Actions'),
                                    empty_values=[],
                                    orderable=False,
                                    template_code=DEFAULT_ACTION_BUTTONS,
                                    attrs={"td": {"style": "white-space:nowrap;"}},
                                    extra_context={'perm_checker': perm_checker})

    class Meta:
        model = ExternalAuthentication
        fields = ("username",
                  "secured_service",)
        prefix = 'external_authentication-table'

    def render_username(self, record):
        username, password = record.decrypt()
        return username


class ServiceAccessGroupTable(SecuredTable):
    perm_checker = None
    user_set__all = tables.ManyToManyColumn()
    actions = tables.TemplateColumn(verbose_name=_('Actions'),
                                    empty_values=[],
                                    orderable=False,
                                    template_code=DEFAULT_ACTION_BUTTONS,
                                    attrs={"td": {"style": "white-space:nowrap;"}},
                                    extra_context={'perm_checker': perm_checker})

    class Meta:
        model = ServiceAccessGroup
        fields = ("name",
                  "description",
                  "user_set__all")
        prefix = 'service-access-group-table'


class AllowedOperationTable(SecuredTable):
    perm_checker = None
    secured_service = tables.TemplateColumn(template_code=VALUE_TABLE_LINK)
    actions = tables.TemplateColumn(verbose_name=_('Actions'),
                                    empty_values=[],
                                    orderable=False,
                                    template_code=DEFAULT_ACTION_BUTTONS,
                                    attrs={"td": {"style": "white-space:nowrap;"}},
                                    extra_context={'perm_checker': perm_checker})

    class Meta:
        model = AllowedOperation
        fields = ("description",
                  "operations",
                  "secured_service",
                  "allowed_groups",
                  "allowed_area",
                  "actions",
                  )
        prefix = 'allowed-operation-table'

    def render_allowed_area(self, record, value):
        leaflet_widget = LeafletWidget()
        leaflet_widget.modifiable = False
        leaflet_field = GeometryField(widget=leaflet_widget)
        field_name = f'id-{record.id}-allowed_area'
        field_value = value.geojson
        leaflet_field_html = leaflet_field.widget.render(field_name, field_value)
        # todo: nest the leaflet client in a accordion. We need to customize the init call to the shown event of the
        #  accordion
        return mark_safe(leaflet_field_html)


class ProxySettingTable(SecuredTable):
    perm_checker = None
    secured_service = tables.TemplateColumn(template_code=VALUE_TABLE_LINK)
    actions = tables.TemplateColumn(verbose_name=_('Actions'),
                                    empty_values=[],
                                    orderable=False,
                                    template_code=DEFAULT_ACTION_BUTTONS,
                                    attrs={"td": {"style": "white-space:nowrap;"}},
                                    extra_context={'perm_checker': perm_checker})

    class Meta:
        model = ProxySetting
        fields = ("secured_service",
                  "camouflage",
                  "log_response",
                  )
        prefix = 'proxy-setting-table'


class AnalyzedResponseLogTable(SecuredTable):
    perm_checker = None
    response__request__service = tables.TemplateColumn(template_code=VALUE_CONCRETE_TABLE_LINK)
    operation = tables.Column(verbose_name=_("operation"),
                              accessor="response__request__url")

    class Meta:
        model = AnalyzedResponseLog
        fields = ("response__request__service",
                  "response__request__user",
                  "operation",
                  "response__request__url",
                  "response__request__timestamp",
                  "entity_count",
                  "entity_total_count",
                  "entity_unit")
        prefix = 'analyzed-response-log-table'

    def render_operation(self, value):
        import urllib.parse as urlparse
        from urllib.parse import parse_qs
        parsed = urlparse.urlparse(value)
        query_parameters = {k.lower(): v for k, v in parse_qs(parsed.query).items()}
        operation = query_parameters.get('request', None)
        if operation:
            operation = operation[0]
        return operation
