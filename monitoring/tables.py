from django.utils.html import format_html

from MrMap.columns import MrMapColumn
from MrMap.tables import MrMapTable
from django.utils.translation import gettext_lazy as _

from MrMap.utils import get_theme
from monitoring.enums import HealthStateEnum


class HealthStateReasonsTable(MrMapTable):

    type = MrMapColumn(
        accessor='health_state_code',
        verbose_name=_('Type'),
        empty_values=[],
    )

    reason = MrMapColumn(
        accessor='reason',
        verbose_name=_('Reason'),
        empty_values=[],
    )

    exception = MrMapColumn(
        accessor='monitoring_result__error_msg',
        verbose_name=_('Remote error message'),
        empty_values=[],
    )

    def render_type(self, value):
        icon = value
        if value == HealthStateEnum.WARNING.value:
            icon = self.get_icon(icon_color='text-warning',
                                 icon=get_theme(self.user)["ICONS"]["WARNING"],
                                 tooltip=_('This is a warning reason.'))
        elif value == HealthStateEnum.CRITICAL.value:
            icon = self.get_icon(icon_color='text-danger',
                                 icon=get_theme(self.user)["ICONS"]["CRITICAL"],
                                 tooltip=_('This is a critical reason.'))
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
