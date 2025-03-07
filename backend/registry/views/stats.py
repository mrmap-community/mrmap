from registry.models.metadata import DatasetMetadataRecord
from rest_framework.fields import DateTimeField, IntegerField
from rest_framework_json_api.serializers import Serializer
from rest_framework_json_api.views import generics


class StatisticalDatasetMetadataRecordSerializer(Serializer):
    id = DateTimeField(source="day")
    day = DateTimeField()
    new = IntegerField()
    deleted = IntegerField()
    updated = IntegerField()

    class Meta:
        resource_name = 'StatisticalDatasetMetadataRecord'


class StatisticalDatasetMetadataRecordListView(generics.ListAPIView):
    queryset = DatasetMetadataRecord.history.stats_per_day()
    serializer_class = StatisticalDatasetMetadataRecordSerializer
    ordering_fields = ["id"]
