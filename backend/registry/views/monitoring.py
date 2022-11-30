
from extras.openapi import CustomAutoSchema
from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
from extras.viewsets import (AsyncCreateMixin, NestedModelViewSet,
                             SerializerClassesMixin)
from registry.models.monitoring import (LayerGetFeatureInfoResult,
                                        LayerGetMapResult,
                                        WMSGetCapabilitiesResult)
from registry.serializers.monitoring import (
    LayerGetFeatureInfoResultCreateSerializer,
    LayerGetFeatureInfoResultSerializer, LayerGetMapResultCreateSerializer,
    LayerGetMapResultSerializer, WMSGetCapabilitiesResultCreateSerializer,
    WMSGetCapabilitiesResultSerializer)
from registry.tasks.monitoring import (check_get_feature_info_operation,
                                       check_get_map_operation,
                                       check_wms_get_capabilities_operation)
from rest_framework_json_api.views import ModelViewSet


class WMSGetCapabilitiesResultViewSetMixin():
    schema = CustomAutoSchema(
        tags=["Monitoring"],
    )
    queryset = WMSGetCapabilitiesResult.objects.all()
    serializer_classes = {
        "default": WMSGetCapabilitiesResultSerializer,
        "create": WMSGetCapabilitiesResultCreateSerializer
    }
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    task_function = check_wms_get_capabilities_operation

    def get_task_kwargs(self, request, serializer):
        return {
            "service_pk": serializer.data["service"]["id"]
        }


class WMSGetCapabilitiesResultViewSet(
    WMSGetCapabilitiesResultViewSetMixin,
    AsyncCreateMixin,
    SerializerClassesMixin,
    ModelViewSet,
):
    pass


class NestedWMSGetCapabilitiesResultViewSet(
    WMSGetCapabilitiesResultViewSetMixin,
    SerializerClassesMixin,
    NestedModelViewSet,
):
    pass


class LayerGetMapResultViewSetMixin():
    schema = CustomAutoSchema(
        tags=["Monitoring"],
    )
    queryset = LayerGetMapResult.objects.all()
    serializer_classes = {
        "default": LayerGetMapResultSerializer,
        "create": LayerGetMapResultCreateSerializer
    }
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    task_function = check_get_map_operation

    def get_task_kwargs(self, request, serializer):
        return {
            "layer_pk": serializer.data["layer"]["id"]
        }


class LayerGetMapResultViewSet(
    LayerGetMapResultViewSetMixin,
    AsyncCreateMixin,
    SerializerClassesMixin,
    ModelViewSet,
):
    pass


class NestedLayerGetMapResultViewSet(
    LayerGetMapResultViewSetMixin,
    SerializerClassesMixin,
    NestedModelViewSet,
):
    pass


class LayerGetFeatureInfoResultViewSetMixin():
    schema = CustomAutoSchema(
        tags=["Monitoring"],
    )
    queryset = LayerGetFeatureInfoResult.objects.all()
    serializer_classes = {
        "default": LayerGetFeatureInfoResultSerializer,
        "create": LayerGetFeatureInfoResultCreateSerializer
    }
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    task_function = check_get_feature_info_operation

    def get_task_kwargs(self, request, serializer):
        return {
            "layer_pk": serializer.data["layer"]["id"]
        }


class LayerGetFeatureInfoResultViewSet(
    LayerGetFeatureInfoResultViewSetMixin,
    AsyncCreateMixin,
    SerializerClassesMixin,
    ModelViewSet,
):
    pass


class NestedLayerGetFeatureInfoResultViewSet(
    LayerGetFeatureInfoResultViewSetMixin,
    SerializerClassesMixin,
    NestedModelViewSet,
):
    pass
