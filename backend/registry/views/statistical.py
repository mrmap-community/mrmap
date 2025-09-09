from registry.models.materialized_views import (
    MaterializedCatalogueServiceStatsPerDay,
    MaterializedDatasetMetadataRecordStatsPerDay,
    MaterializedFeatureTypeStatsPerDay, MaterializedHarvestingStatsPerDay,
    MaterializedLayerStatsPerDay, MaterializedServiceMetadataRecordStatsPerDay,
    MaterializedWebFeatureServiceStatsPerDay,
    MaterializedWebMapServiceStatsPerDay)
from registry.serializers.statistical import (
    StatisticalCatalogueServiceSerializer,
    StatisticalDatasetMetadataRecordSerializer,
    StatisticalFeatureTypeSerializer,
    StatisticalHarvestedMetadataRelationSerializer, StatisticalLayerSerializer,
    StatisticalServiceMetadataRecordSerializer,
    StatisticalWebFeatureServiceSerializer, StatisticalWebMapServiceSerializer)
from rest_framework_json_api.views import generics


class StatisticalListView(generics.ListAPIView):
    ordering_fields = ["id"]


class StatisticalDatasetMetadataRecordListView(StatisticalListView):
    queryset = MaterializedDatasetMetadataRecordStatsPerDay.objects.all()
    serializer_class = StatisticalDatasetMetadataRecordSerializer


class StatisticalServiceMetadataRecordListView(StatisticalListView):
    queryset = MaterializedServiceMetadataRecordStatsPerDay.objects.all()
    serializer_class = StatisticalServiceMetadataRecordSerializer


class StatisticalWebMapServiceListView(StatisticalListView):
    queryset = MaterializedWebMapServiceStatsPerDay.objects.all()
    serializer_class = StatisticalWebMapServiceSerializer


class StatisticalLayerListView(StatisticalListView):
    queryset = MaterializedLayerStatsPerDay.objects.all()
    serializer_class = StatisticalLayerSerializer


class StatisticalWebFeatureServiceListView(StatisticalListView):
    queryset = MaterializedWebFeatureServiceStatsPerDay.objects.all()
    serializer_class = StatisticalWebFeatureServiceSerializer


class StatisticalFeatureTypeListView(StatisticalListView):
    queryset = MaterializedFeatureTypeStatsPerDay.objects.all()
    serializer_class = StatisticalFeatureTypeSerializer


class StatisticalCatalogueServiceListView(StatisticalListView):
    queryset = MaterializedCatalogueServiceStatsPerDay.objects.all()
    serializer_class = StatisticalCatalogueServiceSerializer


class StatisticalHarvestedMetadataRelationListView(StatisticalListView):
    filterset_fields = ('service', 'harvesting_job')
    queryset = MaterializedHarvestingStatsPerDay.objects.all()
    serializer_class = StatisticalHarvestedMetadataRelationSerializer
