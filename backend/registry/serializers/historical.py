from accounts.serializers.users import UserSerializer
# HistorySerializerMixin moved to extras/serializers.py with #741, so the role
# tables of ``accounts`` can answer their changelog without importing this module
from extras.serializers import HistorySerializerMixin
from registry.models.metadata import DatasetMetadataRecord, ServiceMetadataRecord
from registry.models.service import (CatalogueService, FeatureType, Layer,
                                     WebFeatureService, WebMapService)


class WebMapServiceHistorySerializer(HistorySerializerMixin):

    included_serializers = {
        "history_user": UserSerializer,
        "history_relation": "registry.serializers.service.WebMapServiceSerializer"
    }

    class Meta:
        model = WebMapService.change_log.model
        exclude = HistorySerializerMixin.Meta.exclude


class LayerHistorySerializer(HistorySerializerMixin):

    included_serializers = {
        "history_user": UserSerializer,
        "history_relation": "registry.serializers.service.LayerSerializer"
    }

    class Meta:
        model = Layer.change_log.model
        exclude = HistorySerializerMixin.Meta.exclude


class WebFeatureServiceHistorySerializer(HistorySerializerMixin):

    included_serializers = {
        "history_user": UserSerializer,
        "history_relation": "registry.serializers.service.WebFeatureServiceSerializer"
    }

    class Meta:
        model = WebFeatureService.change_log.model
        exclude = HistorySerializerMixin.Meta.exclude


class FeatureTypeHistorySerializer(HistorySerializerMixin):
    included_serializers = {
        "history_user": UserSerializer,
        "history_relation": "registry.serializers.service.FeatureTypeSerializer"
    }

    class Meta:
        model = FeatureType.change_log.model
        exclude = HistorySerializerMixin.Meta.exclude


class CatalogueServiceHistorySerializer(HistorySerializerMixin):

    included_serializers = {
        "history_user": UserSerializer,
        "history_relation": "registry.serializers.service.CatalogueServiceSerializer"
    }

    class Meta:
        model = CatalogueService.change_log.model
        exclude = HistorySerializerMixin.Meta.exclude


class DatasetMetadataRecordHistorySerializer(HistorySerializerMixin):
    included_serializers = {"history_user": UserSerializer}

    class Meta:
        model = DatasetMetadataRecord.change_log.model
        exclude = HistorySerializerMixin.Meta.exclude


class ServiceMetadataRecordHistorySerializer(HistorySerializerMixin):
    included_serializers = {"history_user": UserSerializer}

    class Meta:
        model = ServiceMetadataRecord.change_log.model
        exclude = HistorySerializerMixin.Meta.exclude
