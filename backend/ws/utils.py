from celery import states
from django.db.models import Q
from jobs.models import Task
from registry.models import WebMapService, WebFeatureService, CatalougeService, Layer, FeatureType, FeatureTypeElement, DatasetMetadata
from registry.models.security import AllowedOperation, ServiceAccessGroup, AnalyzedResponseLog, ServiceAuthentication, \
    ProxySetting


def get_object_counts(user):
    # todo:
    #  jobs_count = user.get_instances(klass=Job).filter(tasks__status__in=[states.STARTED, states.PENDING]).count()
    tasks_count = user.get_instances(klass=Task, filter=Q(status__in=[states.STARTED, states.PENDING])).count()
    wms_count = user.get_instances(klass=WebMapService).count()
    wfs_count = user.get_instances(klass=WebFeatureService).count()
    csw_count = user.get_instances(klass=CatalougeService).count()
    layers_count = user.get_instances(klass=Layer).count()
    feature_types_count = user.get_instances(klass=FeatureType).count()
    feature_type_elements_count = user.get_instances(klass=FeatureTypeElement).count()
    dataset_metadata_count = user.get_instances(klass=DatasetMetadata).count()
    service_authentication_count = user.get_instances(klass=ServiceAuthentication).count()
    allowed_operations_count = user.get_instances(klass=AllowedOperation).count()
    service_access_groups_count = user.get_instances(klass=ServiceAccessGroup).count()
    proxy_log_count = user.get_instances(klass=AnalyzedResponseLog).count()
    proxy_settings_count = user.get_instances(klass=ProxySetting).count()

    response = {
        "jobsCount": 0,  # todo
        "tasksCount": tasks_count,
        "wmsCount": wms_count,
        "wfsCount": wfs_count,
        "cswCount": csw_count,
        "layersCount": layers_count,
        "featureTypesCount": feature_types_count,
        "featureTypeElementsCount": feature_type_elements_count,
        "datasetMetadataCount": dataset_metadata_count,
        "serviceAuthenticationCount": service_authentication_count,
        "allowedOperationsCount": allowed_operations_count,
        "serviceAccessGroupsCount": service_access_groups_count,
        "proxyLogCount": proxy_log_count,
        "proxySettingsCount": proxy_settings_count,
    }
    return response
