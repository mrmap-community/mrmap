import django_tables2 as tables
from django.urls import reverse
from django.utils.html import format_html
from django.db.models import Count
from django.utils.translation import gettext_lazy as _
from main.tables.template_code import RECORD_ABSOLUTE_LINK_VALUE_CONTENT, VALUE_ABSOLUTE_LINK, \
    SERVICE_STATUS_ICONS, SERVICE_HEALTH_ICONS
from monitoring.settings import WARNING_RELIABILITY, CRITICAL_RELIABILITY
from resourceNew.models import Service, Layer
from service.helper.enums import MetadataEnum
from service.templatecodes import RESOURCE_TABLE_ACTIONS
from guardian.core import ObjectPermissionChecker


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


class WmsServiceTable(tables.Table):
    perm_checker = None
    title = tables.TemplateColumn(template_code=RECORD_ABSOLUTE_LINK_VALUE_CONTENT,
                                  accessor="metadata")

    """
    status_icons = tables.TemplateColumn(template_code=SERVICE_STATUS_ICONS,
                                         verbose_name=_('Status'),
                                         empty_values=[],)
    health_icons = tables.TemplateColumn(template_code=SERVICE_HEALTH_ICONS,
                                         verbose_name=_('Health'),
                                         empty_values=[],
                                         extra_context={'WARNING_RELIABILITY': WARNING_RELIABILITY,
                                                        'CRITICAL_RELIABILITY': CRITICAL_RELIABILITY})
    contact = tables.TemplateColumn(template_code=VALUE_ABSOLUTE_LINK,
                                    accessor="")"""
    owner = tables.TemplateColumn(template_code=VALUE_ABSOLUTE_LINK,
                                  accessor='owned_by_org')
    """last_harvested = tables.Column(verbose_name=_('Last harvest'),
                                   empty_values=[],
                                   accessor='harvest_results__first')
    last_harvest_duration = tables.Column(verbose_name=_('Harvest duration'),
                                          empty_values=[],
                                          accessor='harvest_results__first')
    collected_harvest_records = tables.Column(verbose_name=_('Collected harvest records'),
                                              empty_values=[],
                                              accessor='harvest_results__first')
    """
    actions = tables.TemplateColumn(verbose_name=_('Actions'),
                                    empty_values=[],
                                    orderable=False,
                                    template_code=RESOURCE_TABLE_ACTIONS,
                                    attrs={"td": {"style": "white-space:nowrap;"}},
                                    extra_context={'perm_checker': perm_checker})

    class Meta:
        model = Service
        fields = ("title",
                  "layers_count",
                  "service_type__version",
                  #'service__service_type__version',

                  #'contact',
                  'created_at',
                  'owner',
                  'actions',
                  )
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'ogc-service-table'

    def before_render(self, request):
        self.perm_checker = ObjectPermissionChecker(request.user)
        # if we call self.data, all object from the underlying queryset will be selected. But in case of paging, only a
        # subset of the self.data is needed. django tables2 doesn't provide any way to get the cached qs of the current
        # page. So the following code snippet is a workaround to collect the current presented objects of the table
        # to avoid calling the database again.
        objs = []
        for obj in self.page.object_list:
            objs.append(obj.record)
        # for all objects of the current page, we prefetch all permissions for the given user. This optimizes the
        # rendering of the action column, cause we need to check if the user has the permission to perform the given
        # action. If we don't prefetch the permissions, any permission check in the template will perform one db query
        # for each object.
        if objs:
            self.perm_checker.prefetch_perms(objs)

    def render_layers_count(self, record, value):
        link = f'<a href="{reverse("resourceNew:layer_list")}?service__id__in={record.pk}">{value}</a>'
        return format_html(link)


class LayerTable(tables.Table):
    perm_checker = None
    title = tables.TemplateColumn(template_code=RECORD_ABSOLUTE_LINK_VALUE_CONTENT,
                                  accessor="metadata")
    service = tables.TemplateColumn(template_code=VALUE_ABSOLUTE_LINK)
    owner = tables.TemplateColumn(template_code=VALUE_ABSOLUTE_LINK,
                                  accessor='owned_by_org')
    actions = tables.TemplateColumn(verbose_name=_('Actions'),
                                    empty_values=[],
                                    orderable=False,
                                    template_code=RESOURCE_TABLE_ACTIONS,
                                    attrs={"td": {"style": "white-space:nowrap;"}},
                                    extra_context={'perm_checker': perm_checker})

    class Meta:
        model = Layer
        fields = ("title",
                  "descendants_count",
                  "children_count",
                  "dataset_metadata_count",
                  "service",
                  "created_at",
                  "owner",
                  "actions",
                  )
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'layer-table'

    def before_render(self, request):
        self.perm_checker = ObjectPermissionChecker(request.user)
        # if we call self.data, all object from the underlying queryset will be selected. But in case of paging, only a
        # subset of the self.data is needed. django tables2 doesn't provide any way to get the cached qs of the current
        # page. So the following code snippet is a workaround to collect the current presented objects of the table
        # to avoid calling the database again.
        objs = []
        for obj in self.page.object_list:
            objs.append(obj.record)
        # for all objects of the current page, we prefetch all permissions for the given user. This optimizes the
        # rendering of the action column, cause we need to check if the user has the permission to perform the given
        # action. If we don't prefetch the permissions, any permission check in the template will perform one db query
        # for each object.
        if objs:
            self.perm_checker.prefetch_perms(objs)

    def render_children_count(self, record, value):
        link = f'<a href="{reverse("resourceNew:layer_list")}?id__in='
        for child in record.children.all():
            link += f'{child.pk},'
        link += f'">{value}</a>'
        return format_html(link)

    def render_dataset_metadata_count(self, record, value):
        link = f'<a href="{reverse("resourceNew:dataset_metadata_list")}?self_pointing_layers__id__in={record.pk}">{value}</a>'
        return format_html(link)
