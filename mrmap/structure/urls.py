from django.urls import path

from structure.views.pending_task import *
from structure.views.error_report import *
from structure.views.organization import *
from structure.views.publish_request import *
from structure.views.auth_user import *
from structure.views.role import *

app_name = 'structure'
urlpatterns = [

    # TaskResult
    path('tasks/<pk>/revoke', PendingTaskDelete.as_view(), name='remove-task'),
    path('error-reports/<pk>', ErrorReportDetailView.as_view(), name='generate-error-report'),

    # Organizations
    path('organizations', OrganizationTableView.as_view(), name='organization_overview'),
    path('organizations/<pk>', OrganizationDetailView.as_view(), name='organization_view'),
    path('organizations/<pk>/change', OrganizationUpdateView.as_view(), name='organization_change'),
    path('organizations/<pk>/members', OrganizationMembersTableView.as_view(), name='organization_members'),
    path('organizations/<pk>/publishers', OrganizationPublishersTableView.as_view(), name='organization_publisher_overview'),
    path('organizations/<pk>/roles', OrganizationRolesTableView.as_view(), name='organization_roles_overview'),

    # PublishRequests
    path('publish-requests', PublishRequestTableView.as_view(), name='publish_request_overview'),
    path('publish-requests/new', PublishRequestNewView.as_view(), name='publish_request_new'),
    path('publish-requests/<pk>/change', PublishRequestUpdateView.as_view(), name='publishrequest_change'),

    # users
    path('users', UserTableView.as_view(), name='users_overview'),

    path('roles/<pk>', RoleUpdateView.as_view(), name='ownerbasedtemplaterole_change')
]

