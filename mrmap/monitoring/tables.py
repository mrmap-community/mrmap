import django_tables2 as tables
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from MrMap.icons import IconEnum
from extras.tables.template_code import VALUE_ABSOLUTE_LINK, VALUE_ABSOLUTE_LINK_LIST
from monitoring.enums import HealthStateEnum
from monitoring.models import HealthState, MonitoringResult, MonitoringRun


class MonitoringRunTable(tables.Table):
    id = tables.Column(linkify=True)
    resources_all = tables.TemplateColumn(template_code=VALUE_ABSOLUTE_LINK_LIST, verbose_name=_("Resources"))
    results = tables.TemplateColumn(template_code='<a href="{{record.result_view_uri}}">Results</a>',
                                    verbose_name=_('Related results'))

    class Meta:
        model = MonitoringRun
        fields = ('id', 'resources_all', 'start', 'end', 'duration', 'health_states', 'results')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'monitoring-result-table'

    @staticmethod
    def render_health_states(record):
        color = "text-success"
        for health_state in record.health_states.all():
            if health_state.health_state_code == HealthStateEnum.CRITICAL.value:
                color = "text-danger"
                break
            elif health_state.health_state_code == HealthStateEnum.WARNING.value:
                color = "text-warning"
            elif health_state.health_state_code == HealthStateEnum.UNAUTHORIZED.value:
                color = "text-warning"
        return format_html(f'<a class="{color}" href="{record.health_state_view_uri}">{_("Related health states")}</a>')


class MonitoringResultTable(tables.Table):
    monitoring_run = tables.Column(linkify=True)
    resource = tables.TemplateColumn(template_code=VALUE_ABSOLUTE_LINK,
                                     accessor="resource",
                                     verbose_name=_("Resource"))

    class Meta:
        model = MonitoringResult
        fields = ('id', 'monitoring_run', 'resource', 'timestamp', 'available', 'status_code', 'monitored_uri')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'monitoring-result-table'

    @staticmethod
    def render_id(record, value):
        if record.available:
            color = "text-success"
        else:
            color = "text-danger"
        return format_html(f'<a class="{color}" href="{record.get_absolute_url()}">{value}</a>')

    @staticmethod
    def render_status_code(value):
        if 200 <= value < 300:
            color = 'badge-success'
        elif 400 <= value < 500:
            color = 'badge-warning'
        elif 500 <= value < 600:
            color = 'badge-danger'
        else:
            color = 'badge-secondary'
        return format_html(f'<span class="badge {color}">{value}</span>')

    @staticmethod
    def render_monitored_uri(value):
        return format_html(f'<a target="_blank" href="{value}">{value}</a>')


class MonitoringResultDetailTable(MonitoringResultTable):
    class Meta:
        model = MonitoringResult
        fields = ('error_msg',)
        sequence = ("...", "error_msg")
        template_name = "skeletons/django_tables2_vertical_table.html"
        prefix = 'monitoring-result-detail-table'
        orderable = False


class HealthStateTable(tables.Table):
    id = tables.Column(linkify=True)
    resource = tables.Column(linkify=True)
    monitoring_run = tables.Column(linkify=True)
    reasons = tables.Column(accessor='reasons__all', verbose_name=_('Reasons'))
    results = tables.TemplateColumn(template_code='<a href="{{value.result_view_uri}}">Results</a>',
                                    accessor='monitoring_run',
                                    verbose_name=_('Monitoring results'))

    class Meta:
        model = HealthState
        fields = ('id', 'resource', 'health_state_code', 'monitoring_run')
        sequence = ('resource', 'health_state_code', 'monitoring_run', '...')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'health-state-table'

    @staticmethod
    def render_health_state_code(value):
        if value == HealthStateEnum.WARNING.value:
            css_class = 'text-warning ' + IconEnum.WARNING.value
            tooltip = 'This is a warning reason.'
        elif value == HealthStateEnum.CRITICAL.value:
            css_class = 'text-danger ' + IconEnum.CRITICAL.value
            tooltip = 'This is a critical reason.'
        elif value == HealthStateEnum.UNAUTHORIZED.value:
            css_class = 'text-info ' + IconEnum.PASSWORD.value
            tooltip = 'This check runs without getting state relevant results, cause the service needs an ' + \
                      'authentication for this request.'
        else:
            css_class = 'text-success ' + IconEnum.OK.value
            tooltip = 'Good standing health.'
        return format_html(f"<i class='{css_class}' title='{tooltip}'></i>")

    @staticmethod
    def render_reasons(value):
        string = ''
        for health_state_reason in value:
            string += health_state_reason.reason
        return format_html(string)


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
