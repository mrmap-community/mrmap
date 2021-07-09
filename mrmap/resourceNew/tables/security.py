import django_tables2 as tables
from main.tables.tables import SecuredTable
from main.tables.template_code import DEFAULT_ACTION_BUTTONS, VALUE_ABSOLUTE_LINK, VALUE_TABLE_LINK
from resourceNew.models.security import AllowedOperation, ServiceAccessGroup, AnalyzedResponseLog, ExternalAuthentication, \
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


class ProxyLogTable(tables.Table):

    class Meta:
        model = AnalyzedResponseLog
        fields = ("service",
                  "user",
                  "operation",
                  "uri",
                  "timestamp",
                  "response_wfs_num_features",
                  "response_wms_megapixel")
        prefix = 'proxy-log-table'
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"

