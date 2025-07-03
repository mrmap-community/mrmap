from rest_framework.fields import DateTimeField, IntegerField
from rest_framework_json_api.serializers import Serializer


class StatisticalSerializer(Serializer):
    id = DateTimeField(source="day")
    day = DateTimeField()
    new = IntegerField()
    deleted = IntegerField()
    updated = IntegerField()

    class Meta:
        resource_name = 'StatisticalSerializer'


class StatisticalDatasetMetadataRecordSerializer(StatisticalSerializer):

    class Meta:
        resource_name = 'StatisticalDatasetMetadataRecord'


class StatisticalWebMapServiceSerializer(StatisticalSerializer):

    class Meta:
        resource_name = 'StatisticalWebMapService'


class StatisticalLayerSerializer(StatisticalSerializer):

    class Meta:
        resource_name = 'StatisticalLayer'


class StatisticalWebFeatureServiceSerializer(StatisticalSerializer):

    class Meta:
        resource_name = 'StatisticalWebFeatureService'


class StatisticalFeatureTypeSerializer(StatisticalSerializer):

    class Meta:
        resource_name = 'StatisticalFeatureType'


class StatisticalCatalogueServiceSerializer(StatisticalSerializer):

    class Meta:
        resource_name = 'StatisticalCatalogueService'
