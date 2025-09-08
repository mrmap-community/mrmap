from registry.models.materialized_views import \
    MaterializedHarvestingStatsPerDay
from registry.models.metadata import (DatasetMetadataRecord,
                                      ServiceMetadataRecord)
from registry.models.service import (CatalogueService, FeatureType, Layer,
                                     WebFeatureService, WebMapService)
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
    filterset_fields = ('history_change_reason',)
    queryset = DatasetMetadataRecord.history.stats_per_day()
    serializer_class = StatisticalDatasetMetadataRecordSerializer


class StatisticalServiceMetadataRecordListView(StatisticalListView):
    queryset = ServiceMetadataRecord.history.stats_per_day()
    serializer_class = StatisticalServiceMetadataRecordSerializer


class StatisticalWebMapServiceListView(StatisticalListView):
    queryset = WebMapService.history.stats_per_day()
    serializer_class = StatisticalWebMapServiceSerializer


class StatisticalLayerListView(StatisticalListView):
    queryset = Layer.history.stats_per_day()
    serializer_class = StatisticalLayerSerializer


class StatisticalWebFeatureServiceListView(StatisticalListView):
    queryset = WebFeatureService.history.stats_per_day()
    serializer_class = StatisticalWebFeatureServiceSerializer


class StatisticalFeatureTypeListView(StatisticalListView):
    queryset = FeatureType.history.stats_per_day()
    serializer_class = StatisticalFeatureTypeSerializer


class StatisticalCatalogueServiceListView(StatisticalListView):
    queryset = CatalogueService.history.stats_per_day()
    serializer_class = StatisticalCatalogueServiceSerializer


class StatisticalHarvestedMetadataRelationListView(StatisticalListView):
    filterset_fields = ('service', 'harvesting_job')
    queryset = MaterializedHarvestingStatsPerDay.objects.all()
    serializer_class = StatisticalHarvestedMetadataRelationSerializer
