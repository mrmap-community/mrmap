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
        fields = ('uuid', 'resources_all', 'start', 'end', 'duration')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'monitoring-result-table'

    health_states = tables.Column(accessor='health_states', verbose_name=_('Related health states'))
    results = tables.Column(verbose_name=_('Related results'), empty_values=[])

    def before_render(self, request):
        self.render_helper = RenderHelper(user_permissions=list(filter(None, request.user.get_all_permissions())))

    def render_uuid(self, record, value):
        return Link(url=record.get_absolute_url(), content=value).render(safe=True)

    def render_resources_all(self, value):
        elements = []
        for resource in value:
            elements.append(Tag(tag='span', attrs={"class": ['mr-1']},
                                content=Link(url=resource.get_absolute_url(), content=resource).render() + ", "))
        return format_html(self.render_helper.render_list_coherent(items=elements))

    def render_results(self, record):
        return Link(url=record.result_view_uri, content=_('Results')).render(safe=True)

    def render_health_states(self, record):
        color = TextColorEnum.SUCCESS
        for health_state in record.health_states.all():
            if health_state.health_state_code == HealthStateEnum.CRITICAL.value:
                color = TextColorEnum.DANGER
                break
            elif health_state.health_state_code == HealthStateEnum.WARNING.value:
                color = TextColorEnum.WARNING
            elif health_state.health_state_code == HealthStateEnum.UNAUTHORIZED.value:
                color = TextColorEnum.WARNING
        return Link(url=record.health_state_view_uri, color=color, content=_('Health states')).render(safe=True)


class MonitoringResultTable(tables.Table):
    resource = tables.TemplateColumn(template_code=VALUE_ABSOLUTE_LINK,
                                     accessor="resource",
                                     verbose_name=_("Resource"))

    class Meta:
        model = MonitoringResult
        fields = ('uuid', 'monitoring_run', 'resource', 'timestamp', 'available', 'status_code', 'monitored_uri')
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
        fields = ('uuid', 'resource', 'health_state_code', 'monitoring_run')
        sequence = ('resource', 'health_state_code', 'monitoring_run', '...')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'health-state-table'

    def before_render(self, request):
        self.render_helper = RenderHelper(user_permissions=list(filter(None, request.user.get_all_permissions())))

    def render_uuid(self, record, value):
        return Link(url=record.get_absolute_url, content=value).render(safe=True)

    def render_resource(self, value):
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

    def render_results(self, record):
        return Link(url=record.result_view_uri, content=_('Results')).render(safe=True)


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
