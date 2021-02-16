from django.db.models import Q
from django.http import HttpRequest

from MrMap.settings import GIT_REPO_URI, GIT_GRAPH_URI
from MrMap.sub_settings.dev_settings import ROOT_URL
from MrMap.utils import get_theme
from structure.models import MrMapGroup, MrMapUser, PublishRequest, GroupInvitationRequest, Organization


def default_context(request: HttpRequest):
    if request.user is not None and not request.user.is_anonymous:
        permissions = request.user.get_permissions()
    else:
        permissions = []

    mr_map_group_count = MrMapGroup.objects.filter(Q(is_permission_group=False) | Q(is_public_group=True)).count()
    mr_map_organization_count = Organization.objects.filter().count()
    mr_map_user_count = MrMapUser.objects.count()

    if request.user.is_anonymous:
        pending_publish_requests_count = None
        pending_group_invitation_requests_count = None
    else:
        if not request.user.is_superuser:
            # show only requests for groups or organization where the user is member of
            # superuser can see all pending requests
            pending_publish_requests_count = PublishRequest.objects.filter(Q(group__in=request.user.get_groups()) |
                                                                           Q(organization=request.user.organization)).count
        else:
            pending_publish_requests_count = PublishRequest.objects.count()
        pending_group_invitation_requests_count = GroupInvitationRequest.objects.filter(Q(user=request.user)|
                                                                                        Q(group__in=request.user.get_groups())).count()

    return {
        "ROOT_URL": ROOT_URL,
        "PATH": request.path.split("/")[1],
        "FULL_PATH": request.path,
        "LANGUAGE_CODE": request.LANGUAGE_CODE,
        "user_permissions": permissions,
        "GIT_REPO_URI": GIT_REPO_URI,
        "GIT_GRAPH_URI": GIT_GRAPH_URI,
        "THEME": get_theme(request.user),
        "mr_map_group_count": mr_map_group_count,
        "mr_map_organization_count": mr_map_organization_count,
        "mr_map_user_count": mr_map_user_count,
        "pending_publish_requests_count": pending_publish_requests_count,
        "pending_group_invitation_requests_count": pending_group_invitation_requests_count,

    }
