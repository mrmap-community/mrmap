import django_tables2 as tables
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django_bootstrap_swt.components import Link, Badge, Tag
from django_bootstrap_swt.enums import BadgeColorEnum, TextColorEnum
from django_bootstrap_swt.utils import RenderHelper

from MrMap.icons import IconEnum
from main.tables.template_code import VALUE_ABSOLUTE_LINK
from monitoring.enums import HealthStateEnum
from monitoring.models import HealthState, MonitoringResult, MonitoringRun


class MonitoringRunTable(tables.Table):
    class Meta:
        model = MonitoringRun
        fields = ('uuid', 'metadatas__all', 'start', 'end', 'duration')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'monitoring-result-table'

    health_state = tables.Column(accessor='health_state', verbose_name=_('Related health state'))
    results = tables.Column(verbose_name=_('Related results'), empty_values=[])

    def before_render(self, request):
        self.render_helper = RenderHelper(user_permissions=list(filter(None, request.user.get_all_permissions())))

    def render_uuid(self, record, value):
        return Link(url=record.get_absolute_url(), content=value).render(safe=True)

    def render_metadatas__all(self, value):
        links = []
        for metadata in value:
            links.append(Tag(tag='span', attrs={"class": ['mr-1']},
                             content=Link(url=metadata.get_absolute_url(), content=metadata).render() + ','))
        return format_html(self.render_helper.render_list_coherent(items=links))

    def render_results(self, record):
        if record.result_view_uri:
            return Link(url=record.result_view_uri, content=_('results')).render(safe=True)
        else:
            return ''

    def render_health_state(self, value):
        if value.health_state_code == HealthStateEnum.WARNING.value:
            color = TextColorEnum.WARNING
        elif value.health_state_code == HealthStateEnum.CRITICAL.value:
            color = TextColorEnum.DANGER
        elif value.health_state_code == HealthStateEnum.UNAUTHORIZED.value:
            color = TextColorEnum.SECONDARY
        else:
            color = TextColorEnum.SUCCESS
        return Link(url=value.get_absolute_url, color=color, content=value.pk).render(safe=True)


class MonitoringResultTable(tables.Table):
    metadata = tables.TemplateColumn(template_code=VALUE_ABSOLUTE_LINK,
                                     accessor="metadata",
                                     verbose_name=_("Resource"))

    class Meta:
        model = MonitoringResult
        fields = ('uuid', 'monitoring_run', 'metadata', 'timestamp', 'available', 'status_code', 'monitored_uri')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'monitoring-result-table'

    def render_uuid(self, record, value):
        if record.available:
            color = TextColorEnum.SUCCESS
        else:
            color = TextColorEnum.DANGER
        return Link(url=record.get_absolute_url(), color=color, content=value).render(safe=True)

    def render_monitoring_run(self, value):
        return Link(url=value.get_absolute_url(), content=value).render(safe=True)

    def render_status_code(self, value):
        if 200 <= value < 300:
            color = BadgeColorEnum.SUCCESS
        elif 400 <= value < 500:
            color = BadgeColorEnum.WARNING
        elif 500 <= value < 600:
            color = BadgeColorEnum.DANGER
        else:
            color = BadgeColorEnum.SECONDARY
        return Badge(content=value, color=color).render(safe=True)

    def render_monitored_uri(self, value):
        return Link(url=value, content=value, open_in_new_tab=True).render(safe=True)


class MonitoringResultDetailTable(MonitoringResultTable):
    class Meta:
        model = MonitoringResult
        fields = ('error_msg',)
        sequence = ("...", "error_msg")
        template_name = "skeletons/django_tables2_vertical_table.html"
        prefix = 'monitoring-result-detail-table'
        orderable = False


class HealthStateTable(tables.Table):
    reasons = tables.Column(accessor='reasons__all', verbose_name=_('Reasons'))
    results = tables.Column(accessor='monitoring_run', verbose_name=_('Monitoring results'))

    class Meta:
        model = HealthState
        fields = ('uuid', 'metadata', 'health_state_code', 'monitoring_run')
        sequence = ('metadata', 'health_state_code', 'monitoring_run', '...')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'health-state-table'

    def before_render(self, request):
        self.render_helper = RenderHelper(user_permissions=list(filter(None, request.user.get_all_permissions())))

    def render_uuid(self, record, value):
        return Link(url=record.get_absolute_url, content=value).render(safe=True)

    def render_metadata(self, value):
        return Link(url=value.get_absolute_url, content=value).render(safe=True)

    def render_monitoring_run(self, value):
        return Link(url=value.get_absolute_url, content=value).render(safe=True)

    def render_health_state_code(self, value):
        if value == HealthStateEnum.WARNING.value:
            icon = Tag(tag='i', attrs={"class": [TextColorEnum.WARNING.value, IconEnum.WARNING.value]},
                       tooltip=_('This is a warning reason.'))
        elif value == HealthStateEnum.CRITICAL.value:
            icon = Tag(tag='i', attrs={"class": [TextColorEnum.DANGER.value, IconEnum.CRITICAL.value]},
                       tooltip=_('This is a critical reason.'))
        elif value == HealthStateEnum.UNAUTHORIZED.value:
            icon = Tag(tag='i', attrs={"class": [TextColorEnum.INFO.value, IconEnum.PASSWORD.value]}, tooltip=_(
                'This check runs without getting state relevant results, cause the service needs an authentication for this request.'))
        else:
            icon = Tag(tag='i', attrs={"class": [TextColorEnum.SUCCESS.value, IconEnum.OK.value]},
                       tooltip=_('Good standing health.'))
        return icon.render(safe=True)

    def render_reasons(self, value):
        string = ''
        for health_state_reason in value:
            string += health_state_reason.reason
        return format_html(string)

    def render_results(self, value):
        return Link(url=value.result_view_uri, content=_('Results')).render(safe=True)


class HealthStateDetailTable(HealthStateTable):
    class Meta:
        model = HealthState
        fields = ('reliability_1w',
                  'reliability_1m',
                  'reliability_3m',
                  'average_response_time',
                  'average_response_time_1w',
                  'average_response_time_1m',
                  'average_response_time_3m')
        sequence = ('health_state_code', '...')
        template_name = "skeletons/django_tables2_vertical_table.html"
        prefix = 'health-state-detail-table'
        orderable = False
