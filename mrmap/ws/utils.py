from celery import states
from django.db.models import Q
from job.models import Task, Job
from resourceNew.enums.service import OGCServiceEnum
from resourceNew.models import Service, Layer, FeatureType, FeatureTypeElement, ServiceMetadata, LayerMetadata, \
    FeatureTypeMetadata, DatasetMetadata
from resourceNew.models.security import AllowedOperation, ServiceAccessGroup, ProxyLog


def get_app_view_model(user):
    # todo:
    #  jobs_count = user.get_instances(klass=Job).filter(tasks__status__in=[states.STARTED, states.PENDING]).count()
    tasks_count = user.get_instances(klass=Task, filter=Q(status__in=[states.STARTED, states.PENDING])).count()
    wms_count = user.get_instances(klass=Service).filter(service_type__name=OGCServiceEnum.WMS.value).count()
    wfs_count = user.get_instances(klass=Service).filter(service_type__name=OGCServiceEnum.WFS.value).count()
    csw_count = user.get_instances(klass=Service).filter(service_type__name=OGCServiceEnum.CSW.value).count()
    layers_count = user.get_instances(klass=Layer).count()
    feature_types_count = user.get_instances(klass=FeatureType).count()
    feature_type_elements_count = user.get_instances(klass=FeatureTypeElement).count()
    service_metadata_count = user.get_instances(klass=ServiceMetadata).count()
    layer_metadata_count = user.get_instances(klass=LayerMetadata).count()
    feature_type_metadata_count = user.get_instances(klass=FeatureTypeMetadata).count()
    dataset_metadata_count = user.get_instances(klass=DatasetMetadata).count()
    allowed_operations_count = user.get_instances(klass=AllowedOperation).count()
    service_access_groups_count = user.get_instances(klass=ServiceAccessGroup).count()
    proxy_log_count = user.get_instances(klass=ProxyLog).count()

    response = {
        "jobsCount": 0,
        "tasksCount": tasks_count,
        "wmsCount": wms_count,
        "wfsCount": wfs_count,
        "cswCount": csw_count,
        "layersCount": layers_count,
        "featureTypesCount": feature_types_count,
        "featureTypeElementsCount": feature_type_elements_count,
        "serviceMetadataCount": service_metadata_count,
        "layerMetadataCount": layer_metadata_count,
        "featureTypeMetadataCount": feature_type_metadata_count,
        "datasetMetadataCount": dataset_metadata_count,
        "allowedOperationsCount": allowed_operations_count,
        "serviceAccessGroupsCount": service_access_groups_count,
        "proxyLogCount": proxy_log_count,
    }
    return response
