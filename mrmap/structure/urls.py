from django.urls import path

from structure.views import *

app_name = 'structure'
urlpatterns = [

    # PendingTask
    path('tasks/<pk>/remove', PendingTaskDelete.as_view(), name='remove-task'),
    path('error-reports/<pk>', ErrorReportDetailView.as_view(), name='generate-error-report'),

    # Organizations
    path('organizations', OrganizationTableView.as_view(), name='organization_overview'),
    path('organizations/<pk>', OrganizationDetailView.as_view(), name='organization_details'),
    path('organizations/<pk>/members', OrganizationMembersTableView.as_view(), name='organization_members'),
    path('organizations/<pk>/publishers', OrganizationPublishersTableView.as_view(), name='organization_publisher_overview'),

    # PublishRequests
    path('publish-requests', PublishRequestTableView.as_view(), name='publish_request_overview'),
    path('publish-requests/new', PublishRequestNewView.as_view(), name='publish_request_new'),
    path('publish-requests/<pk>/accept', PublishRequestAcceptView.as_view(), name='publish_request_accept'),

    # users
    path('users', UserTableView.as_view(), name='users_overview'),
]

