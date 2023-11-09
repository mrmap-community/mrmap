from django.db.models.query_utils import Q

LAYER_WITHOUT_RELATION = Q(
    layer__isnull=False, feature_type__isnull=True, csw__isnull=True,
    wms__isnull=True, wfs__isnull=True, dataset_metadata__isnull=True, service_metadata__isnull=True)
LAYER_WITH_DATASET_RELATION = Q(
    layer__isnull=False, feature_type__isnull=True, csw__isnull=True,
    wms__isnull=True, wfs__isnull=True, dataset_metadata__isnull=False, service_metadata__isnull=True)
LAYER_WITH_SERVICE_RELATION = Q(
    layer__isnull=False, feature_type__isnull=True, csw__isnull=True,
    wms__isnull=True, wfs__isnull=True, dataset_metadata__isnull=True, service_metadata__isnull=False)


FEATURE_TYPE_WITHOUT_RELATION = Q(
    layer__isnull=True, feature_type__isnull=False, csw__isnull=True,
    wms__isnull=True, wfs__isnull=True, dataset_metadata__isnull=True, service_metadata__isnull=True)
FEATURE_TYPE_WITH_DATASET_RELATION = Q(
    layer__isnull=True, feature_type__isnull=False, csw__isnull=True,
    wms__isnull=True, wfs__isnull=True, dataset_metadata__isnull=False, service_metadata__isnull=True)
FEATURE_TYPE_WITH_SERVICE_RELATION = Q(
    layer__isnull=True, feature_type__isnull=False, csw__isnull=True,
    wms__isnull=True, wfs__isnull=True, dataset_metadata__isnull=True, service_metadata__isnull=False)

CSW_WITHOUT_RELATION = Q(
    layer__isnull=True, feature_type__isnull=True, csw__isnull=False,
    wms__isnull=True, wfs__isnull=True, dataset_metadata__isnull=True, service_metadata__isnull=True)
CSW_WITH_SERVICE_RELATION = Q(
    layer__isnull=True, feature_type__isnull=True, csw__isnull=False,
    wms__isnull=True, wfs__isnull=True, dataset_metadata__isnull=True, service_metadata__isnull=False)

WMS_WITHOUT_RELATION = Q(
    layer__isnull=True, feature_type__isnull=True, csw__isnull=True,
    wms__isnull=False, wfs__isnull=True, dataset_metadata__isnull=True, service_metadata__isnull=True)
WMS_WITH_SERVICE_RELATION = Q(
    layer__isnull=True, feature_type__isnull=True, csw__isnull=True,
    wms__isnull=False, wfs__isnull=True, dataset_metadata__isnull=True, service_metadata__isnull=False)

WFS_WITHOUT_RELATION = Q(
    layer__isnull=True, feature_type__isnull=True, csw__isnull=True,
    wms__isnull=True, wfs__isnull=False, dataset_metadata__isnull=True, service_metadata__isnull=True)
WFS_WITH_SERVICE_RELATION = Q(
    layer__isnull=True, feature_type__isnull=True, csw__isnull=True,
    wms__isnull=True, wfs__isnull=False, dataset_metadata__isnull=True, service_metadata__isnull=False)

DATASET_WITHOUT_RELATION = Q(
    layer__isnull=True, feature_type__isnull=True, csw__isnull=True,
    wms__isnull=True, wfs__isnull=True, dataset_metadata__isnull=False, service_metadata__isnull=True)
SERVICE_WITHOUT_RELATION = Q(
    layer__isnull=True, feature_type__isnull=True, csw__isnull=True,
    wms__isnull=True, wfs__isnull=True, dataset_metadata__isnull=True, service_metadata__isnull=False)


VALID_LAYER_RELATIONS = LAYER_WITH_SERVICE_RELATION | LAYER_WITH_DATASET_RELATION | LAYER_WITH_SERVICE_RELATION
VALID_FEATURE_TYPE_RELATIONS = FEATURE_TYPE_WITHOUT_RELATION | FEATURE_TYPE_WITH_DATASET_RELATION | FEATURE_TYPE_WITH_SERVICE_RELATION
VALID_CSW_RELATIONS = CSW_WITHOUT_RELATION | CSW_WITH_SERVICE_RELATION
VALID_WMS_RELATIONS = WMS_WITHOUT_RELATION | WMS_WITH_SERVICE_RELATION
VALID_WFS_RELATIONS = WFS_WITHOUT_RELATION | WFS_WITH_SERVICE_RELATION

VALID_RELATIONS = VALID_LAYER_RELATIONS | VALID_FEATURE_TYPE_RELATIONS | VALID_CSW_RELATIONS | VALID_WMS_RELATIONS | VALID_WFS_RELATIONS | DATASET_WITHOUT_RELATION | SERVICE_WITHOUT_RELATION
