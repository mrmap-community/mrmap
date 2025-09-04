from extras.serializers import SystemInfoSerializerMixin
from rest_framework.fields import DateField, IntegerField
from rest_framework_json_api.serializers import Serializer


class StatisticalSerializer(SystemInfoSerializerMixin, Serializer):
    id = DateField(source="history_day")
    day = DateField(source="history_day")

    class Meta:
        resource_name = 'StatisticalSerializer'


class HistoricalRecordDependingMixin:
    new = IntegerField()
    deleted = IntegerField()
    updated = IntegerField()


class StatisticalDatasetMetadataRecordSerializer(HistoricalRecordDependingMixin, StatisticalSerializer):

    class Meta:
        resource_name = 'StatisticalDatasetMetadataRecord'


class StatisticalServiceMetadataRecordSerializer(HistoricalRecordDependingMixin, StatisticalSerializer):

    class Meta:
        resource_name = 'StatisticalServiceMetadataRecord'


class StatisticalWebMapServiceSerializer(HistoricalRecordDependingMixin, StatisticalSerializer):

    class Meta:
        resource_name = 'StatisticalWebMapService'


class StatisticalLayerSerializer(HistoricalRecordDependingMixin, StatisticalSerializer):

    class Meta:
        resource_name = 'StatisticalLayer'


class StatisticalWebFeatureServiceSerializer(HistoricalRecordDependingMixin, StatisticalSerializer):

    class Meta:
        resource_name = 'StatisticalWebFeatureService'


class StatisticalFeatureTypeSerializer(HistoricalRecordDependingMixin, StatisticalSerializer):

    class Meta:
        resource_name = 'StatisticalFeatureType'


class StatisticalCatalogueServiceSerializer(HistoricalRecordDependingMixin, StatisticalSerializer):

    class Meta:
        resource_name = 'StatisticalCatalogueService'


class StatisticalHarvestedMetadataRelationSerializer(StatisticalSerializer):
    new = IntegerField()
    updated = IntegerField()
    existed = IntegerField()

    class Meta:
        resource_name = 'StatisticalHarvestedMetadataRelation'
