import django_tables2 as tables
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from extras.tables.tables import SecuredTable
from extras.tables.template_code import RECORD_ABSOLUTE_LINK_VALUE_CONTENT, VALUE_ABSOLUTE_LINK, \
    SERVICE_STATUS_ICONS, OPERATION_URLS
from registry.models import Service, Layer, FeatureType, FeatureTypeElement
from registry.tables.template_codes import SERVICE_DETAIL_ICONS, LAYER_FEATURE_TYPE_DETAIL_ICONS, \
    FEATURE_TYPE_ELEMENT_DETAIL_ICONS, LAYER_TABLE_ACTIONS, FEATURE_TYPE_TABLE_ACTIONS, SERVICE_TABLE_ACTIONS

TOOLTIP_TITLE = _('The resource title')
TOOLTIP_ACTIVE = _('Shows whether the resource is active or not.')
TOOLTIP_SECURED_ACCESS = _('Shows whether the resource is only accessible for certain groups and/or in certain areas.')
TOOLTIP_SECURED_EXTERNALLY = _('Shows whether the resource needs authentication to its origin server.')
TOOLTIP_VERSION = _('The resource version')
TOOLTIP_DATA_PROVIDER = _('The organization which provides the resource.')
TOOLTIP_REGISTERED_BY_GROUP = _('The group which registered the resource.')
TOOLTIP_REGISTERED_FOR = _('The organization for which the resource is registered.')
TOOLTIP_CREATED_ON = _('The registration date.')
TOOLTIP_ACTIONS = _('Performable Actions')
TOOLTIP_STATUS = _(
    'Shows the status of the resource. You can see active state, secured access state and secured externally state.')
TOOLTIP_HEALTH = _('Shows the health status of the resource.')
TOOLTIP_VALIDATION = _('Shows the validation status of the resource')


class ServiceTable(SecuredTable):
    perm_checker = None
    details = tables.TemplateColumn(template_code=SERVICE_DETAIL_ICONS,
                                    verbose_name=_("Details"),
                                    orderable=False)
    status_icons = tables.TemplateColumn(template_code=SERVICE_STATUS_ICONS,
                                         verbose_name=_('Status'),
                                         empty_values=[],)
    operation_urls__all = tables.TemplateColumn(template_code=OPERATION_URLS)
    """
    health_icons = tables.TemplateColumn(template_code=SERVICE_HEALTH_ICONS,
                                         verbose_name=_('Health'),
                                         empty_values=[],
                                         extra_context={'WARNING_RELIABILITY': WARNING_RELIABILITY,
                                                        'CRITICAL_RELIABILITY': CRITICAL_RELIABILITY})
    contact = tables.TemplateColumn(template_code=VALUE_ABSOLUTE_LINK,
                                    accessor="")"""
    owner = tables.TemplateColumn(template_code=VALUE_ABSOLUTE_LINK,
                                  accessor='owned_by_org')
    actions = tables.TemplateColumn(verbose_name=_('Actions'),
                                    empty_values=[],
                                    orderable=False,
                                    template_code=SERVICE_TABLE_ACTIONS,
                                    attrs={"td": {"style": "white-space:nowrap;"}},
                                    extra_context={'perm_checker': perm_checker})

    class Meta:
        model = Service
        fields = ("title",
                  "status_icons",
                  "details",
                  "layers_count",
                  "feature_types_count",
                  "service_type__version",
                  # 'service__service_type__version',
                  # 'contact',
                  "operation_urls__all",
                  'created_at',
                  'owner',
                  'actions',
                  )
        prefix = 'ogc-service-table'

    def render_layers_count(self, record, value):
        link = f'<a href="{reverse("registry:layer_list")}?service__id__in={record.pk}">{value}</a>'
        return format_html(link)

    def render_feature_types_count(self, record, value):
        link = f'<a href="{reverse("registry:feature_type_list")}?service__id__in={record.pk}">{value}</a>'
        return format_html(link)


class LayerTable(SecuredTable):
    perm_checker = None
    details = tables.TemplateColumn(template_code=LAYER_FEATURE_TYPE_DETAIL_ICONS,
                                    verbose_name=_("Details"),
                                    orderable=False)
    owner = tables.TemplateColumn(template_code=VALUE_ABSOLUTE_LINK,
                                  accessor='owned_by_org')
    actions = tables.TemplateColumn(verbose_name=_('Actions'),
                                    empty_values=[],
                                    orderable=False,
                                    template_code=LAYER_TABLE_ACTIONS,
                                    attrs={"td": {"style": "white-space:nowrap;"}},
                                    extra_context={'perm_checker': perm_checker})

    class Meta:
        model = Layer
        fields = ("title",
                  "identifier",
                  "details",
                  "children_count",
                  "dataset_metadata_count",
                  "parent",
                  "service",
                  "created_at",
                  "owner",
                  "actions",
                  )
        prefix = 'layer-table'

    def render_children_count(self, record, value):
        if value > 0:
            return format_html(f'<a href="{reverse("registry:layer_list")}?parent={record.pk}">{value}</a>')
        return value

    def render_dataset_metadata_count(self, record, value):
        if value > 0:
            return format_html(f'<a href="{reverse("registry:dataset_metadata_list")}?self_pointing_layers__id__in={record.pk}">{value}</a>')
        return value

    def render_parent(self, value):
        return format_html(f'<a href="{reverse("registry:layer_list")}?id__in={value.pk}">{value}</a>')

    def render_service(self, value):
        return format_html(f'<a href="{reverse("registry:service_wms_list")}?id={value.pk}">{value}</a>')


class FeatureTypeTable(SecuredTable):
    perm_checker = None
    details = tables.TemplateColumn(template_code=LAYER_FEATURE_TYPE_DETAIL_ICONS,
                                    verbose_name=_("Details"),
                                    orderable=False)
    owner = tables.TemplateColumn(template_code=VALUE_ABSOLUTE_LINK,
                                  accessor='owned_by_org')
    actions = tables.TemplateColumn(verbose_name=_('Actions'),
                                    empty_values=[],
                                    orderable=False,
                                    template_code=FEATURE_TYPE_TABLE_ACTIONS,
                                    attrs={"td": {"style": "white-space:nowrap;"}},
                                    extra_context={'perm_checker': perm_checker})

    class Meta:
        model = FeatureType
        fields = ("title",
                  "identifier",
                  "details",
                  "elements_count",
                  "dataset_metadata_count",
                  "service",
                  "created_at",
                  "owner",
                  "actions",
                  )
        prefix = 'feature-type-table'

    def render_elements_count(self, record, value):
        if value > 0:
            return format_html(f'<a href="{reverse("registry:feature_type_element_list")}?feature_type__id__in={record.pk}">{value}</a>')
        return value

    def render_dataset_metadata_count(self, record, value):
        if value > 0:
            return format_html(f'<a href="{reverse("registry:dataset_metadata_list")}?self_pointing_feature_types__id__in={record.pk}">{value}</a>')
        return value

    def render_service(self, value):
        return format_html(f'<a href="{reverse("registry:service_wfs_list")}?id={value.pk}">{value}</a>')


class FeatureTypeElementTable(SecuredTable):
    perm_checker = None
    details = tables.TemplateColumn(template_code=FEATURE_TYPE_ELEMENT_DETAIL_ICONS,
                                    verbose_name=_("Details"),
                                    orderable=False)
    owner = tables.TemplateColumn(template_code=VALUE_ABSOLUTE_LINK,
                                  accessor='owned_by_org')

    class Meta:
        model = FeatureTypeElement
        fields = ("name",
                  "details",
                  "data_type",
                  "feature_type",
                  "feature_type__service",)
        prefix = 'feature-type-element-table'

    def render_dataset_metadata_count(self, record, value):
        if value > 0:
            return format_html(f'<a href="{reverse("registry:dataset_metadata_list")}?self_pointing_feature_types__id__in={record.pk}">{value}</a>')
        return value

    def render_feature_type(self, value):
        return format_html(f'<a href="{reverse("registry:feature_type_list")}?id__in={value.pk}">{value}</a>')

    def render_feature_type__service(self, value):
        return format_html(f'<a href="{reverse("registry:service_wfs_list")}?id={value.pk}">{value}</a>')
