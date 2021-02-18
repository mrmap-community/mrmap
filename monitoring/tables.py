from django.utils.html import format_html
from django_bootstrap_swt.components import Link, Badge
from django_bootstrap_swt.enums import BadgeColorEnum
import django_tables2 as tables
from MrMap.tables import MrMapTable
from django.utils.translation import gettext_lazy as _

from MrMap.utils import get_theme
from monitoring.enums import HealthStateEnum
from monitoring.models import HealthState, MonitoringResult, MonitoringRun


class MonitoringRunTable(tables.Table):
    class Meta:
        model = MonitoringRun
        fields = ('uuid', 'start', 'end', 'duration')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'monitoring-result-table'

    results = tables.Column(verbose_name=_('Results'), empty_values=[])

    def render_uuid(self, record, value):
        return Link(url=record.get_absolute_url(), content=value).render(safe=True)

    def render_results(self, record):
        if record.result_view_uri:
            return Link(url=record.result_view_uri, content=_('results')).render(safe=True)
        else:
            return ''


class MonitoringResultTable(tables.Table):
    class Meta:
        model = MonitoringResult
        fields = ('uuid', 'metadata', 'timestamp', 'available', 'status_code', 'monitored_uri')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'monitoring-result-table'

    def render_uuid(self, record, value):
        return Link(url=record.get_absolute_url(), content=value).render(safe=True)

    def render_metadata(self, value):
        return Link(url=value.detail_view_uri, content=value).render(safe=True)

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
        fields = ('error_msg', )
        sequence = ("...", "error_msg")
        template_name = "skeletons/django_tables2_vertical_table.html"
        prefix = 'monitoring-result-detail-table'
        orderable = False


class HealthStateTable(MrMapTable):
    class Meta:
        model = HealthState
        fields = ('metadata', 'health_state_code', 'reason', 'monitoring_run__monitoring_results')

    def render_health_state_code(self, value):
        icon = value
        if value == HealthStateEnum.WARNING.value:
            icon = self.get_icon(icon_color='text-warning',
                                 icon=get_theme(self.user)["ICONS"]["WARNING"],
                                 tooltip=_('This is a warning reason.'))
        elif value == HealthStateEnum.CRITICAL.value:
            icon = self.get_icon(icon_color='text-danger',
                                 icon=get_theme(self.user)["ICONS"]["CRITICAL"],
                                 tooltip=_('This is a critical reason.'))
        elif value == HealthStateEnum.UNAUTHORIZED.value:
            icon = self.get_icon(icon_color='text-info',
                                 icon=get_theme(self.user)["ICONS"]["PASSWORD"],
                                 tooltip=_('This check runs without getting state relevant results, cause the service needs an authentication for this request.'))
        return icon

    @staticmethod
    def render_reason(value):
        return format_html(value)

    @staticmethod
    def render_exception(record, value):
        if record.health_state_code == HealthStateEnum.CRITICAL.value:
            return value
        else:
            return ''
