import json
import django_tables2 as tables
from celery import states
from django.db.models import Count
from django.template import Template, Context
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django_bootstrap_swt.components import Link, Tag, Badge, Accordion
from django_bootstrap_swt.enums import ProgressColorEnum
from django_bootstrap_swt.utils import RenderHelper
from MrMap.columns import MrMapColumn
from MrMap.icons import IconEnum, get_all_icons, get_icon
from MrMap.tables import MrMapTable
from django.db.models import Count
from django.utils.translation import gettext_lazy as _
from MrMap.templatecodes import PROGRESS_BAR, TOOLTIP
from main.tables.template_code import RECORD_ABSOLUTE_LINK, RECORD_ABSOLUTE_LINK_VALUE_CONTENT, VALUE_ABSOLUTE_LINK, \
    SERVICE_STATUS_ICONS, SERVICE_HEALTH_ICONS
from monitoring.settings import WARNING_RELIABILITY, CRITICAL_RELIABILITY
from quality.models import ConformityCheckRun
from service.helper.enums import MetadataEnum, OGCServiceEnum
from service.models import MetadataRelation, Metadata, FeatureTypeElement, ProxyLog, MapContext
from service.settings import service_logger
from structure.enums import PendingTaskEnum
from service.templatecodes import RESOURCE_TABLE_ACTIONS
from service.templatecodes import RESOURCE_TABLE_ACTIONS, MAP_CONTEXT_TABLE_ACTIONS
from structure.template_codes import PENDING_TASK_ACTIONS
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


class OgcServiceTable(tables.Table):
    perm_checker = None
    title = tables.TemplateColumn(template_code=RECORD_ABSOLUTE_LINK_VALUE_CONTENT)
    layers = tables.Column(verbose_name=_('Layers'),
                           empty_values=[],
                           accessor='service__child_services__count')
    featuretypes = tables.Column(verbose_name=_('Featuretypes'),
                                 empty_values=[],
                                 accessor='service__featuretypes__count')
    parent_service = tables.TemplateColumn(template_code=VALUE_ABSOLUTE_LINK,
                                           verbose_name=_('Parent service'),
                                           empty_values=[],
                                           accessor='service__parent_service__metadata')
    status_icons = tables.TemplateColumn(template_code=SERVICE_STATUS_ICONS,
                                         verbose_name=_('Status'),
                                         empty_values=[],)
    health_icons = tables.TemplateColumn(template_code=SERVICE_HEALTH_ICONS,
                                         verbose_name=_('Health'),
                                         empty_values=[],
                                         extra_context={'WARNING_RELIABILITY': WARNING_RELIABILITY,
                                                        'CRITICAL_RELIABILITY': CRITICAL_RELIABILITY})
    contact = tables.TemplateColumn(template_code=VALUE_ABSOLUTE_LINK)
    owner = tables.TemplateColumn(template_code=VALUE_ABSOLUTE_LINK,
                                  accessor='owned_by_org')
    last_harvested = tables.Column(verbose_name=_('Last harvest'),
                                   empty_values=[],
                                   accessor='harvest_results__first')
    last_harvest_duration = tables.Column(verbose_name=_('Harvest duration'),
                                          empty_values=[],
                                          accessor='harvest_results__first')
    collected_harvest_records = tables.Column(verbose_name=_('Collected harvest records'),
                                              empty_values=[],
                                              accessor='harvest_results__first')

    actions = tables.TemplateColumn(verbose_name=_('Actions'),
                                    empty_values=[],
                                    orderable=False,
                                    template_code=RESOURCE_TABLE_ACTIONS,
                                    attrs={"td": {"style": "white-space:nowrap;"}},
                                    extra_context={'perm_checker': perm_checker})

    class Meta:
        model = Metadata
        fields = ('title',
                  'layers',
                  'featuretypes',
                  'parent_service',
                  'status_icons',
                  'health_icons',
                  'service__service_type__version',
                  'last_harvested',
                  'last_harvest_duration',
                  'collected_harvest_records',
                  'contact',
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

    def render_last_harvested(self, value):
        return value.timestamp_end if value is not None else _('Never')

    def render_collected_harvest_records(self, record, value):
        dataset_count = record.get_related_metadatas().filter(metadata_type=MetadataEnum.DATASET.value).count()
        link = f"<a data-toggle='tooltip' title='{_('Number of dataset metadata harvested')}'href='{reverse('resource:datasets-index')}?dataset-filter-related_to={record.pk}'>{dataset_count}</a>"
        return format_html(f"{value.number_results} ({link})") if value is not None else '-'

    def render_harvest_duration(self, value):
        last_harvest_result = value
        if last_harvest_result and last_harvest_result.timestamp_end and last_harvest_result.timestamp_start:
            time_delta = last_harvest_result.timestamp_end - last_harvest_result.timestamp_start
            return f"{time_delta.days}d  {time_delta.seconds//3600}h {(time_delta.seconds//60)%60}m {(time_delta.seconds)%60}s"
        else:
            return '-'

    def order_layers(self, queryset, is_descending):
        queryset = queryset.annotate(
            count=Count("service__child_services")
        ).order_by(("-" if is_descending else "") + "count")
        return queryset, True

    def order_featuretypes(self, queryset, is_descending):
        queryset = queryset.annotate(
            count=Count("service__featuretypes")
        ).order_by(("-" if is_descending else "") + "count")
        return queryset, True

    def order_status_icons(self, queryset, is_descending):
        is_descending_str = "-" if is_descending else ""
        queryset = queryset.order_by(is_descending_str + "is_active",
                                     is_descending_str + "is_secured",
                                     is_descending_str + "external_authentication", )
        return queryset, True

    def order_health(self, queryset, is_descending):
        # TODO:
        return queryset, True


class DatasetTable(tables.Table):
    bs4helper = None
    related_objects = MrMapColumn(verbose_name=_('Related objects'), accessor='related_to__all', empty_values=[])
    origins = MrMapColumn(verbose_name=_('Origins'), empty_values=[])
    actions = tables.Column(verbose_name=_('Actions'), empty_values=[], orderable=False,
                            attrs={"td": {"style": "white-space:nowrap;"}})

    class Meta:
        model = Metadata
        fields = ('title',
                  'related_objects',
                  'origins',
                  'actions')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        # todo: set this prefix dynamic
        prefix = 'wms-table'

    def before_render(self, request):
        self.render_helper = RenderHelper(user_permissions=list(filter(None, request.user.get_all_permissions())))

    def render_title(self, value, record):
        return Link(url=record.detail_html_view_uri, content=value, open_in_new_tab=True).render(safe=True)

    def render_related_objects(self, value):
        link_list = []
        for metadata in value:
            if metadata.metadata_type == MetadataEnum.FEATURETYPE.value:
                kind_of_resource_icon = IconEnum.FEATURETYPE.value
                kind_of_resource = "Featuretype"
            elif metadata.metadata_type == MetadataEnum.LAYER.value:
                kind_of_resource_icon = IconEnum.LAYER.value
                kind_of_resource = "Layer"
            else:
                kind_of_resource_icon = ""
                kind_of_resource = ""
            kind_of_resource_icon = Tag(tag='i', attrs={"class": [kind_of_resource_icon]}, ).render()

            link_list.append(Link(url=metadata.detail_view_uri,
                                  content=format_html(kind_of_resource_icon + f" {metadata.title} [{metadata.id}]"),
                                  tooltip=_(f'Click to open the detail view of related {kind_of_resource} <strong>{metadata.title} [{metadata.id}]"</strong>'),), )
        return format_html(self.render_helper.render_list_coherent(items=link_list))

    def render_origins(self, record):
        related_metadatas = MetadataRelation.objects.filter(
            to_metadata=record
        )
        origin_list = []
        rel_mds = list(record.related_metadatas.all())
        relations = list(related_metadatas) + rel_mds
        for relation in relations:
            origin_list.append(f"{relation.origin}")

        return format_html(', '.join(origin_list))

    def render_actions(self, record):
        self.render_helper.update_attrs = {"class": ["btn-sm", "mr-1"]}
        renderd_actions = self.render_helper.render_list_coherent(items=record.get_actions())
        self.render_helper.update_attrs = None
        return format_html(renderd_actions)


class FeatureTypeElementTable(tables.Table):
    class Meta:
        model = FeatureTypeElement
        fields = ('name', 'type', )


class ResourceDetailTable(tables.Table):
    bs4helper = None
    parent_service = tables.Column(verbose_name=_('Parent service'))
    bbox_lat_lon = tables.Column(verbose_name=_('Bbox lat lon'))
    scale_min_max = tables.Column(verbose_name=_('Scale range'), empty_values=[])
    mime_types = tables.Column(verbose_name=_('Mime types'), empty_values=[], attrs={'td': {'class': 'col-sm-10'}})

    class Meta:
        model = Metadata
        fields = ('pk',
                  'service__service_type__name',
                  'service__service_type__version',
                  'last_modified',
                  'service__layer__identifier',
                  'parent_service',
                  'contact__person_name',
                  'contact__organization_name',
                  'contact__phone',
                  'contact__facsimile',
                  'contact__email',
                  'contact__address',
                  'contact__city',
                  'contact__postal_code',
                  'contact__state_or_province',
                  'contact__country',
                  'title',
                  'abstract',
                  'online_resource',
                  'keywords__all',
                  'access_constraints',
                  'service__layer__is_available',
                  'service__layer__is_queryable',
                  'service__layer__is_opaque',
                  'service__layer__is_cascaded',
                  'featuretype__is_searchable',
                  'is_secured',
                  'hits',
                  'scale_min_max',
                  'bbox_lat_lon',
                  'featuretype__default_srs',
                  'reference_system__all',
                  'mime_types',
                  )
        template_name = "skeletons/django_tables2_vertical_table.html"
        # todo: set this prefix dynamic
        prefix = 'layer-detail-table'
        orderable = False

    def __init__(self, *args, **kwargs):
        super(ResourceDetailTable, self).__init__(*args, **kwargs)
        self.exclude = []
        if self.data[0].is_metadata_type(MetadataEnum.SERVICE):
            self.exclude.extend(['parent_service',
                                 'service__layer__identifier',
                                 'service__layer__is_available',
                                 'service__layer__is_queryable',
                                 'service__layer__is_opaque',
                                 'service__layer__is_cascaded',
                                 'scale_min_max',
                                 'bbox_lat_lon',
                                 'featuretype__default_srs', ])
            if self.data[0].is_service_type(OGCServiceEnum.WFS):
                self.exclude.extend(['featuretype__is_searchable', ])
        else:
            self.exclude.extend([
                'access_constraints',
                'service__service_type__name',
                'service__service_type__version',
                'last_modified',
                'online_resource',
                'contact__person_name',
                'contact__organization_name',
                'contact__phone',
                'contact__facsimile',
                'contact__email',
                'contact__address',
                'contact__city',
                'contact__postal_code',
                'contact__state_or_province',
                'contact__country',
            ])

            if self.data[0].is_metadata_type(MetadataEnum.FEATURETYPE):
                self.exclude.extend(['service__layer__identifier',
                                     'service__layer__is_available',
                                     'service__layer__is_queryable',
                                     'service__layer__is_opaque',
                                     'service__layer__is_cascaded',
                                     'scale_min_max', ])

                self.columns['parent_service'].column.accessor = 'featuretype__parent_service__metadata'
                self.columns['bbox_lat_lon'].column.accessor = 'featuretype__bbox_lat_lon'
            else:
                self.exclude.extend(['featuretype__default_srs', ])
                self.columns['parent_service'].column.accessor = 'service__parent_service__metadata'
                self.columns['bbox_lat_lon'].column.accessor = 'service__layer__bbox_lat_lon'

    def render_parent_service(self, value):
        return Link(url=value.detail_view_uri, content=value).render(safe=True)

    def render_online_resource(self, value):
        return Link(url=value, content=value).render(safe=True)

    def render_keywords__all(self, value):
        badges = ''
        for kw in value:
            badges += Badge(content=kw, badge_pill=True)
        return format_html(badges) if value else _('No keywords provided')

    def render_scale_min_max(self, record):
        return f'[{record.service.layer.scale_min}, {record.service.layer.scale_max}]'

    def render_bbox_lat_lon(self, value):
        if value.area > 0.0:
            return None # LeafletClient(polygon=value).render(safe=True)
        else:
            return _('No spatial data provided!')

    def render_featuretype__default_srs(self, value):
        badge = Badge(content=f'{value.prefix}:{value.code}', badge_pill=True).render(safe=True)
        return badge if value else _('No default reference system provided')

    def render_reference_system__all(self, value):
        badges = ''
        for kw in value:
            badges += Badge(content=f'{kw.prefix}:{kw.code}', badge_pill=True)
        return format_html(badges) if value else _('No additional reference systems provided')

    def render_mime_types(self, record):
        mime_types = {}
        formats = record.get_formats()
        for mime in formats:
            op = mime_types.get(mime.operation)
            if op is None:
                op = []
            op.append(mime.mime_type)
            mi = {mime.operation: op}
            mime_types.update(mi)
        mime_type_accordions = ''
        for key, values in mime_types.items():
            badges = ''
            for value in values:
                badges += Badge(content=value)
            mime_type_accordions += Accordion(btn_value=key, content=badges)
        return format_html(mime_type_accordions)


class ChildLayerTable(MrMapTable):
    id = tables.Column(visible=False)
    title = tables.Column(visible=False)
    child_layer_title = tables.Column(empty_values=[], order_by='title', )

    caption = _("Shows all child layer of current WMS.")

    @staticmethod
    def render_child_layer_title(record):
        url = reverse('resource:get-metadata-html', args=(record['id'],))

        if record['sublayers_count'] > 0:
            return format_html("<a href='{}'>{} <span class='badge badge-secondary'>{}</span></a>",
                               url,
                               record['title'],
                               record['sublayers_count'])
        else:
            return format_html("<a href='{}'>{}</a>",
                               url,
                               record['title'], )


class FeatureTypeTable(MrMapTable):
    id = tables.Column(visible=False)
    title = tables.Column(visible=False)
    featuretype_title = tables.Column(empty_values=[], order_by='title', )

    caption = _("Shows all featuretypes of current WFS.")

    @staticmethod
    def render_featuretype_title(record):
        url = reverse('resource:get-metadata-html', args=(record['id'],))

        return format_html("<a href='{}'>{}</a>",
                           url,
                           record['title'], )


class CoupledMetadataTable(MrMapTable):
    id = tables.Column(visible=False)
    title = tables.Column(visible=False)
    coupled_metadata_title = tables.Column(empty_values=[], order_by='title', )

    caption = _("Shows all coupled metadata of current service.")

    @staticmethod
    def render_coupled_metadata_title(record):
        url = reverse('resource:get-metadata-html', args=(record['id'],))

        return format_html("<a href='{}'>{}</a>",
                           url,
                           record['title'], )


class UpdateServiceElements(MrMapTable):
    title = tables.Column(empty_values=[], )
    identifier = tables.Column(empty_values=[], )


class ProxyLogTable(tables.Table):
    caption = _("Shows all logs for a service.")
    user = tables.Column(default='Public group')

    class Meta:
        model = ProxyLog
        fields = ('metadata__id', 'metadata__title', 'timestamp', 'operation', 'response_wms_megapixel', 'response_wfs_num_features')
        sequence = ('metadata__id', 'metadata__title', 'user', '...')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'proxy-log-table'


# TODO
class MapContextTable(tables.Table):

    actions = tables.TemplateColumn(verbose_name=_('Actions'), empty_values=[], orderable=False, template_code=MAP_CONTEXT_TABLE_ACTIONS,
                                    attrs={"td": {"style": "white-space:nowrap;"}})

    class Meta:
        model = MapContext
        fields = ('title', 'abstract', 'actions')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        # todo: set this prefix dynamic
        prefix = 'map-context-table'
