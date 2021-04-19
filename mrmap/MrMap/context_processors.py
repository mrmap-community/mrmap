from django.contrib.auth import get_user_model
from celery import states
from django.db.models import Q
from django.http import HttpRequest
from django_celery_results.models import TaskResult

from MrMap.icons import get_all_icons
from monitoring.models import MonitoringRun
from service.helper.enums import OGCServiceEnum, MetadataEnum
from service.models import Metadata
from structure.models import PublishRequest, Organization
from django.conf import settings


def get_stats(user):
    if not user.is_anonymous:
        mr_map_organization_count = user.get_instances(klass=Organization).count()
        mr_map_user_count = get_user_model().objects.count()

        pending_publish_requests_count = user.get_instances(klass=PublishRequest).count()


        wms_filter = Q(service__service_type__name=OGCServiceEnum.WMS.value,
                       service__is_root=True,
                       is_deleted=False,
                       service__is_update_candidate_for=None)
        wms_count = user.get_instances(klass=Metadata, filter=wms_filter).count()
        pending_monitoring_count = user.get_instances(klass=MonitoringRun, filter=Q(end=None)).count()
        #todo: use get_instances
        pending_tasks_count = TaskResult.objects.filter(Q(status=states.PENDING)|
                                                        Q(status=states.STARTED)|
                                                        Q(status=states.RECEIVED)).count()

        wfs_filter = Q(service__service_type__name=OGCServiceEnum.WFS.value,
                       is_deleted=False,
                       service__is_update_candidate_for=None)
        wfs_count = user.get_instances(klass=Metadata, filter=wfs_filter).count()

        csw_filter = Q(service__service_type__name=OGCServiceEnum.CSW.value,
                       is_deleted=False,
                       service__is_update_candidate_for=None)
        csw_count = user.get_instances(klass=Metadata, filter=csw_filter).count()

        dataset_filter = Q(metadata_type=MetadataEnum.DATASET.value,
                           is_deleted=False,
                           service__is_update_candidate_for=None, )
        dataset_count = user.get_instances(klass=Metadata, filter=dataset_filter).count()
        return {
                "mr_map_organization_count": mr_map_organization_count,
                "mr_map_user_count": mr_map_user_count,
                "pending_publish_requests_count": pending_publish_requests_count,
                "pending_monitoring_count": pending_monitoring_count,
                "pending_tasks_count": pending_tasks_count,
                "wms_count": wms_count,
                "wfs_count": wfs_count,
                "csw_count": csw_count,
                "dataset_count": dataset_count,
            }
    else:
        return {}


def default_context(request: HttpRequest):
    context = {
        "PATH": request.path.split("/")[1],
        "FULL_PATH": request.path,
        "LANGUAGE_CODE": request.LANGUAGE_CODE,
        "GIT_REPO_URI": settings.GIT_REPO_URI,
        "GIT_GRAPH_URI": settings.GIT_GRAPH_URI,
        "ICONS": get_all_icons(),
    }
    context.update(get_stats(request.user))
    return context
