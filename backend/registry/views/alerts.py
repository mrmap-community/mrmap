from datetime import datetime, timezone

from camel_converter import to_snake
from drf_spectacular.utils import OpenApiParameter, extend_schema
from registry.querys.alerts import ALERT_CATEGORIES, collect_service_alerts
from registry.serializers.alerts import ServiceAlertSerializer
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework_json_api.views import generics

FILTERS = {
    'severity': ('error', 'warning'),
    'category': tuple(ALERT_CATEGORIES) + (
        'monitoring_overdue', 'update_overdue', 'harvest_overdue',
        'harvest_schedule_too_tight'),
    'serviceType': ('WebMapService', 'WebFeatureService', 'CatalogueService'),
    'service': None,
}


class ServiceAlertListView(generics.ListAPIView):
    """Read-only attention across the services the caller may view."""
    serializer_class = ServiceAlertSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = []

    @extend_schema(parameters=[
        OpenApiParameter(f'filter[{name}]', str, enum=choices)
        for name, choices in FILTERS.items()
    ] + [OpenApiParameter('sort', str)])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return []
        return collect_service_alerts(self.request.user)

    def filter_queryset(self, rows):
        for parameter, value in self.request.query_params.items():
            if not parameter.startswith('filter['):
                continue
            name = parameter[7:-1]
            if name not in FILTERS:
                raise ValidationError('Unknown alert filter.')
            choices = FILTERS[name]
            if choices and value not in choices:
                raise ValidationError('Invalid alert filter value.')
            rows = [row for row in rows if row[to_snake(name)] == value]
        fields = self.request.query_params.get('sort', 'severity,-occurredAt').split(',')
        rows = sorted(rows, key=lambda row: row['id'])
        for field in reversed(fields):
            name = to_snake(field.lstrip('-'))
            if name not in ('severity', 'occurred_at'):
                raise ValidationError('Invalid alert sort field.')
            default = datetime.min.replace(tzinfo=timezone.utc) if name == 'occurred_at' else ''
            rows.sort(key=lambda row: row[name] or default, reverse=field.startswith('-'))
        return rows
