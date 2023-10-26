from django.db.models.query_utils import Q

LAYER_WITHOUT_RELATION = Q(
    layer=True, feature_type=False, csw=False,
    wms=False, wfs=False, dataset_metadata=False, service_metadata=False)
LAYER_WITH_DATASET_RELATION = Q(
    layer=True, feature_type=False, csw=False,
    wms=False, wfs=False, dataset_metadata=True, service_metadata=False)
LAYER_WITH_SERVICE_RELATION = Q(
    layer=True, feature_type=False, csw=False,
    wms=False, wfs=False, dataset_metadata=False, service_metadata=True)


FEATURE_TYPE_WITHOUT_RELATION = Q(
    layer=False, feature_type=True, csw=False,
    wms=False, wfs=False, dataset_metadata=False, service_metadata=False)
FEATURE_TYPE_WITH_DATASET_RELATION = Q(
    layer=False, feature_type=True, csw=False,
    wms=False, wfs=False, dataset_metadata=True, service_metadata=False)
FEATURE_TYPE_WITH_SERVICE_RELATION = Q(
    layer=False, feature_type=True, csw=False,
    wms=False, wfs=False, dataset_metadata=False, service_metadata=True)

CSW_WITHOUT_RELATION = Q(
    layer=False, feature_type=False, csw=True,
    wms=False, wfs=False, dataset_metadata=False, service_metadata=False)
CSW_WITH_SERVICE_RELATION = Q(
    layer=False, feature_type=False, csw=True,
    wms=False, wfs=False, dataset_metadata=False, service_metadata=True)

WMS_WITHOUT_RELATION = Q(
    layer=False, feature_type=False, csw=False,
    wms=True, wfs=False, dataset_metadata=False, service_metadata=False)
WMS_WITH_SERVICE_RELATION = Q(
    layer=False, feature_type=False, csw=False,
    wms=True, wfs=False, dataset_metadata=False, service_metadata=True)

WFS_WITHOUT_RELATION = Q(
    layer=True, feature_type=False, csw=False,
    wms=False, wfs=True, dataset_metadata=False, service_metadata=False)
WFS_WITH_SERVICE_RELATION = Q(
    layer=True, feature_type=False, csw=False,
    wms=False, wfs=True, dataset_metadata=False, service_metadata=True)

VALID_LAYER_RELATIONS = LAYER_WITH_SERVICE_RELATION | LAYER_WITH_DATASET_RELATION | LAYER_WITH_SERVICE_RELATION
VALID_FEATURE_TYPE_RELATIONS = FEATURE_TYPE_WITHOUT_RELATION | FEATURE_TYPE_WITH_DATASET_RELATION | FEATURE_TYPE_WITH_SERVICE_RELATION
VALID_CSW_RELATIONS = CSW_WITHOUT_RELATION | CSW_WITH_SERVICE_RELATION
VALID_WMS_RELATIONS = WMS_WITHOUT_RELATION | WMS_WITH_SERVICE_RELATION
VALID_WFS_RELATIONS = WFS_WITHOUT_RELATION | WFS_WITH_SERVICE_RELATION

VALID_RELATIONS = VALID_LAYER_RELATIONS | VALID_FEATURE_TYPE_RELATIONS | VALID_CSW_RELATIONS | VALID_WMS_RELATIONS | VALID_WFS_RELATIONS
