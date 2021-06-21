import django_tables2 as tables
from main.tables.tables import SecuredTable
from main.tables.template_code import DEFAULT_ACTION_BUTTONS
from resourceNew.models.security import AllowedOperation, ServiceAccessGroup, ProxyLog
from django.utils.translation import gettext_lazy as _


class ServiceAccessGroupTable(SecuredTable):
    perm_checker = None
    actions = tables.TemplateColumn(verbose_name=_('Actions'),
                                    empty_values=[],
                                    orderable=False,
                                    template_code=DEFAULT_ACTION_BUTTONS,
                                    attrs={"td": {"style": "white-space:nowrap;"}},
                                    extra_context={'perm_checker': perm_checker})

    class Meta:
        model = ServiceAccessGroup
        fields = ("name",
                  "description",)
        prefix = 'service-access-group-table'


class AllowedOperationTable(SecuredTable):
    perm_checker = None

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
                  "allowed_groups",
                  "allowed_area",
                  "actions",
                  )
        prefix = 'allowed-operation-table'


class ProxyLogTable(tables.Table):

    class Meta:
        model = ProxyLog
        fields = ("service",
                  "user",
                  "operation",
                  "uri",
                  "timestamp",
                  "response_wfs_num_features",
                  "response_wms_megapixel")
        prefix = 'proxy-log-table'
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
