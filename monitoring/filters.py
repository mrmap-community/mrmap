import django_filters

from monitoring.enums import HealthStateEnum
from monitoring.models import HealthStateReason
from django.utils.translation import gettext_lazy as _


class HealthReasonFilter(django_filters.FilterSet):
    health_state_code = django_filters.ChoiceFilter(field_name='health_state_code',
                                                    choices=HealthStateEnum.as_choices(drop_empty_choice=True),
                                                    lookup_expr='icontains',
                                                    label=_('Select health state code')
                                                    )
    reason = django_filters.CharFilter(field_name='reason',
                                       lookup_expr='icontains',
                                       label=_('Select health state code'))

    class Meta:
        model = HealthStateReason
        fields = []