from MrMap.columns import MrMapColumn
from MrMap.tables import MrMapTable
from django.utils.translation import gettext_lazy as _


class WarningReasonsTable(MrMapTable):

    warning_reason = MrMapColumn(
        verbose_name=_('Reason'),
        empty_values=[],
    )


class CriticalReasonsTable(MrMapTable):

    critical_reason = MrMapColumn(
        verbose_name=_('Reason'),
        empty_values=[],
    )
