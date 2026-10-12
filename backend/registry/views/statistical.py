from registry.filters.statistical import StatisticalFeatureTypePerServiceFilterSet
from registry.models.materialized_views import (
    MaterializedCatalogueServiceStatsPerDay,
    MaterializedDatasetMetadataRecordStatsPerDay,
    MaterializedFeatureTypeStatsPerDay, MaterializedHarvestingStatsPerDay,
    MaterializedLayerStatsPerDay, MaterializedLayerStatsPerDayAndService,
    MaterializedServiceMetadataRecordStatsPerDay,
    MaterializedWebFeatureServiceStatsPerDay,
    MaterializedWebMapServiceStatsPerDay)
from registry.models.service import FeatureType
from registry.serializers.statistical import (
    StatisticalCatalogueServiceSerializer,
    StatisticalDatasetMetadataRecordSerializer,
    StatisticalFeatureTypePerServiceSerializer, StatisticalFeatureTypeSerializer,
    StatisticalHarvestedMetadataRelationSerializer,
    StatisticalLayerPerServiceSerializer, StatisticalLayerSerializer,
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


class StatisticalLayerPerServiceListView(StatisticalListView):
    queryset = MaterializedLayerStatsPerDayAndService.objects.all()
    serializer_class = StatisticalLayerPerServiceSerializer
    filterset_fields = ('service',)


class StatisticalWebFeatureServiceListView(StatisticalListView):
    queryset = MaterializedWebFeatureServiceStatsPerDay.objects.all()
    serializer_class = StatisticalWebFeatureServiceSerializer


class StatisticalFeatureTypeListView(StatisticalListView):
    queryset = MaterializedFeatureTypeStatsPerDay.objects.all()
    serializer_class = StatisticalFeatureTypeSerializer


class StatisticalFeatureTypePerServiceListView(StatisticalListView):
    queryset = FeatureType.history.stats_per_day_per_service()
    serializer_class = StatisticalFeatureTypePerServiceSerializer
    filterset_class = StatisticalFeatureTypePerServiceFilterSet


class StatisticalCatalogueServiceListView(StatisticalListView):
    queryset = MaterializedCatalogueServiceStatsPerDay.objects.all()
    serializer_class = StatisticalCatalogueServiceSerializer


class StatisticalHarvestedMetadataRelationListView(StatisticalListView):
    filterset_fields = ('service', 'harvesting_job')
    queryset = MaterializedHarvestingStatsPerDay.objects.all()
    serializer_class = StatisticalHarvestedMetadataRelationSerializer
