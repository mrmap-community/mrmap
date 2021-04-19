<<<<<<< HEAD
from django.contrib.auth import get_user_model
=======
from celery import states
>>>>>>> 6547e7f6ad710c8351a3ede267a054c17a44fa14
from django.db.models import Q
from django.http import HttpRequest
from django_celery_results.models import TaskResult

from MrMap.icons import get_all_icons
from monitoring.models import MonitoringRun
from service.helper.enums import OGCServiceEnum, MetadataEnum
from service.models import Metadata
<<<<<<< HEAD
from structure.models import Organization, PendingTask, PublishRequest
=======
from structure.models import MrMapGroup, MrMapUser, PublishRequest, GroupInvitationRequest, Organization
from django.conf import settings
>>>>>>> 6547e7f6ad710c8351a3ede267a054c17a44fa14


def get_stats(user):
    if not user.is_anonymous:
        mr_map_organization_count = user.get_instances(klass=Organization).count()
        mr_map_user_count = get_user_model().objects.count()

        pending_publish_requests_count = user.get_instances(klass=PublishRequest).count()

        pending_monitoring_count = user.get_instances(klass=MonitoringRun, filter=Q(end=None)).count()
        pending_tasks_count = user.get_instances(klass=PendingTask).count()

<<<<<<< HEAD
        wms_filter = Q(service__service_type__name=OGCServiceEnum.WMS.value,
                       service__is_root=True,
                       is_deleted=False,
                       service__is_update_candidate_for=None)
        wms_count = user.get_instances(klass=Metadata, filter=wms_filter).count()
=======
        pending_monitoring_count = MonitoringRun.objects.filter(end=None).count()
        pending_tasks_count = TaskResult.objects.filter(Q(status=states.PENDING)|
                                                        Q(status=states.STARTED)|
                                                        Q(status=states.RECEIVED)).count()
>>>>>>> 6547e7f6ad710c8351a3ede267a054c17a44fa14

        wfs_filter = Q(service__service_type__name=OGCServiceEnum.WFS.value,
                       is_deleted=False,
                       service__is_update_candidate_for=None)
        wfs_count = user.get_instances(klass=Metadata, filter=wfs_filter).count()

<<<<<<< HEAD
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
        "ROOT_URL": ROOT_URL,
=======
    return {
        "ROOT_URL": settings.ROOT_URL,
        "HOST_NAME": settings.HOST_NAME,
>>>>>>> 6547e7f6ad710c8351a3ede267a054c17a44fa14
        "PATH": request.path.split("/")[1],
        "FULL_PATH": request.path,
        "LANGUAGE_CODE": request.LANGUAGE_CODE,
        "GIT_REPO_URI": settings.GIT_REPO_URI,
        "GIT_GRAPH_URI": settings.GIT_GRAPH_URI,
        "ICONS": get_all_icons(),
<<<<<<< HEAD
=======
        "mr_map_group_count": mr_map_group_count,
        "mr_map_organization_count": mr_map_organization_count,
        "mr_map_user_count": mr_map_user_count,
        "pending_publish_requests_count": pending_publish_requests_count,
        "pending_group_invitation_requests_count": pending_group_invitation_requests_count,
        "pending_monitoring_count": pending_monitoring_count,
        "pending_tasks_count": pending_tasks_count,
        "wms_count": wms_count,
        "wfs_count": wfs_count,
        "csw_count": csw_count,
        "dataset_count": dataset_count,
>>>>>>> 6547e7f6ad710c8351a3ede267a054c17a44fa14
    }
    context.update(get_stats(request.user))
    return context
