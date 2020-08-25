from MrMap.columns import MrMapColumn
from MrMap.tables import MrMapTable
from django.utils.translation import gettext_lazy as _

from MrMap.utils import get_theme
from monitoring.enums import HealthStateEnum


class HealthStateReasonsTable(MrMapTable):

    type = MrMapColumn(
        verbose_name=_('Type'),
        empty_values=[],
    )

    reason = MrMapColumn(
        verbose_name=_('Reason'),
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
