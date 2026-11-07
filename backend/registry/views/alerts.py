from camel_converter import to_snake
from django.db.models import F
from django.db.models.functions import Collate
from drf_spectacular.utils import OpenApiParameter, extend_schema
from registry.querys.alerts import ALERT_CATEGORIES, collect_service_alerts
from registry.serializers.alerts import ServiceAlertSerializer
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework_json_api.filters import OrderingFilter
from rest_framework_json_api.utils import format_field_name
from rest_framework_json_api.views import generics

FILTERS = {
    'severity': ('error', 'warning'),
    'category': tuple(ALERT_CATEGORIES) + (
        'monitoring_overdue', 'update_overdue', 'harvest_overdue',
        'harvest_schedule_too_tight'),
    'serviceType': ('WebMapService', 'WebFeatureService', 'CatalogueService'),
    'service': None,
}

#: filters whose value may name more than one of its choices at once, comma
#: separated; the queues of the dashboard count the states of the harvesting
#: with one request and the schedules tab of a catalogue asks its two schedule
#: states the same way (#1086)
MULTI_VALUE_FILTERS = ('category',)

#: sort fields the hand-written ordering in filter_queryset accepts; the
#: schema documents exactly these terms, so enum and whitelist cannot drift
SORT_FIELDS = ('id', 'severity', 'occurred_at')
SORT_TERMS = tuple(
    term for field in SORT_FIELDS
    for term in (format_field_name(field), f'-{format_field_name(field)}'))


def ordering(fields):
    """The database ordering which answers the sort terms of a request.

    The rows of the alerts are answered straight out of the table of the
    alerts, so the sort of a request is answered by the database and not by a
    python sort over the whole materialised projection (#1030). Two details
    keep the order which the python sort answered before:

    - a row without a moment is the oldest one - the python path replaced the
      missing moment by `datetime.min`, which puts nulls first when ascending
      and last when descending, the opposite of the database default;
    - the identifier breaks every tie, because the python path sorted by it
      before it applied the requested fields - and it breaks them byte for
      byte, which is the collation `C` and not the collation of the table.

    Args:
        fields: the sort terms of the request, the primary one first

    Returns:
        list: the orderings to answer the terms by, tie-breaker last

    Raises:
        ValidationError: if a term names a field an alert does not have
    """
    order = []
    for field in fields:
        name = to_snake(field.lstrip('-'))
        if name not in SORT_FIELDS:
            raise ValidationError('Invalid alert sort field.')
        descending = field.startswith('-')
        if name == 'id':
            expression = Collate(F(name), 'C')
        elif name == 'occurred_at':
            expression = F(name).asc(nulls_first=True) if not descending \
                else F(name).desc(nulls_last=True)
            order.append(expression)
            continue
        else:
            expression = F(name)
        order.append(expression.desc() if descending else expression.asc())
    return order + [Collate(F('id'), 'C').asc()]


class ServiceAlertListView(generics.ListAPIView):
    """Read-only attention across the services the caller may view."""
    serializer_class = ServiceAlertSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = []

    @extend_schema(parameters=[
        OpenApiParameter(
            f'filter[{name}]', str, enum=choices,
            description=(
                'Multiple categories may be separated by commas; the answer '
                'holds the alerts of every one of them.'
                if name in MULTI_VALUE_FILTERS else None))
        for name, choices in FILTERS.items()
    ] + [OpenApiParameter(
        OrderingFilter.ordering_param, str,
        description=OrderingFilter.ordering_description,
        many=True, enum=list(SORT_TERMS), explode=False)])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return []
        return collect_service_alerts(self.request.user)

    def filter_queryset(self, queryset):
        for parameter, value in self.request.query_params.items():
            if not parameter.startswith('filter['):
                continue
            name = parameter[7:-1]
            if name not in FILTERS:
                raise ValidationError('Unknown alert filter.')
            choices = FILTERS[name]
            lookup = to_snake(name)
            if not choices:
                queryset = queryset.filter(**{lookup: value})
                continue
            # the value of a multi value filter names more than one of the
            # choices comma separated; the answer holds the alerts which are
            # in any one of them - one request per queue of the dashboard
            # (#1086)
            values = (value.split(',') if name in MULTI_VALUE_FILTERS
                      else [value])
            if any(choice not in choices for choice in values):
                raise ValidationError('Invalid alert filter value.')
            if len(values) > 1:
                queryset = queryset.filter(**{f'{lookup}__in': values})
            else:
                queryset = queryset.filter(**{lookup: values[0]})
        fields = self.request.query_params.get(
            'sort', 'severity,-occurredAt').split(',')
        return queryset.order_by(*ordering(fields))
