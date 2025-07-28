from operator import itemgetter

from accounts.serializers.users import UserSerializer
from extras.serializers import SystemInfoSerializerMixin
from registry.models.service import (CatalogueService, FeatureType, Layer,
                                     WebFeatureService, WebMapService)
from rest_framework.fields import SerializerMethodField, UUIDField
from rest_framework_json_api.serializers import ModelSerializer


class HistorySerializerMixin(
        SystemInfoSerializerMixin,
        ModelSerializer):
    id = UUIDField(source='history_id')
    history_type = SerializerMethodField()
    delta = SerializerMethodField()

    class Meta:
        abstract = True
        exclude = ('history_id', )

    def get_history_type(self, obj):
        if obj.history_type == '+':
            return "created"
        elif obj.history_type == '~':
            return "updated"
        elif obj.history_type == '-':
            return "deleted"

    def get_delta(self, obj):
        return None
        if hasattr(obj, "prev_prefetched_record"):
            prev_record = obj.prev_prefetched_record
        else:
            prev_record = obj.prev_record
        if prev_record:
            model_delta = obj.diff_against(prev_record)
            changes = []
            for change in model_delta.changes:
                changes.append(
                    {"field": change.field, "old": change.old, "new": change.new})

            # otherwise the order is not fix and reproducible for test cases
            sorted_changes = sorted(changes, key=itemgetter('field'))
            return sorted_changes


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
        exclude = HistorySerializerMixin.Meta.exclude
