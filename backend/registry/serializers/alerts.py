from rest_framework.fields import CharField, ChoiceField, DateTimeField
from rest_framework_json_api.serializers import Serializer


class ServiceAlertSerializer(Serializer):
    id = CharField(read_only=True)
    severity = ChoiceField(choices=('error', 'warning'), read_only=True)
    category = CharField(read_only=True)
    message = CharField(read_only=True)
    service_type = CharField(read_only=True)
    service = CharField(read_only=True)
    service_title = CharField(read_only=True)
    resource_type = CharField(read_only=True)
    resource_id = CharField(read_only=True)
    occurred_at = DateTimeField(read_only=True, allow_null=True)
    target_path = CharField(read_only=True)

    class Meta:
        resource_name = 'ServiceAlert'
