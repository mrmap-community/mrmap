from django.urls import path
from structure.views import *

app_name = 'structure'
urlpatterns = [

    # PendingTask
    path('tasks/<pk>/remove', PendingTaskDelete.as_view(), name='remove-task'),
    # todo: refactor as generic view
    path('report/error/<report_id>', generate_error_report, name='generate-error-report'),

    # MrMapGroups
    path('groups', GroupTableView.as_view(), name='group_overview'),
    path('groups/new', GroupNewView.as_view(), name='group_new'),
    path('groups/<pk>', GroupDetailView.as_view(), name='group_details'),
    path('groups/<pk>/edit', GroupEditView.as_view(), name='group_edit'),
    path('groups/<pk>/remove', GroupDeleteView.as_view(), name='group_remove'),
    path('groups/<pk>/members', GroupMembersTableView.as_view(), name='group_members'),
    path('groups/<pk>/publish-rights-for', GroupPublishRightsForTableView.as_view(), name='group_publish_rights_overview'),

    # Organizations
    path('organizations', OrganizationTableView.as_view(), name='organization_overview'),
    path('organizations/new', OrganizationNewView.as_view(), name='organization_new'),
    path('organizations/<pk>', OrganizationDetailView.as_view(), name='organization_details'),
    path('organizations/<pk>/edit', OrganizationEditView.as_view(), name='organization_edit'),
    path('organizations/<pk>/remove', OrganizationDeleteView.as_view(), name='organization_remove'),
    path('organizations/<pk>/members', OrganizationMembersTableView.as_view(), name='organization_members'),
    path('organizations/<pk>/publishers', OrganizationPublishersTableView.as_view(), name='organization_publisher_overview'),

    # PublishRequests
    path('publish-requests', PublishRequestTableView.as_view(), name='publish_request_overview'),
    path('publish-requests/new', PublishRequestNewView.as_view(), name='publish_request_new'),
    path('publish-requests/<pk>/accept', PublishRequestAcceptView.as_view(), name='publish_request_accept'),

    # users
    path('users', UserTableView.as_view(), name='users_overview'),

    # todo: move to users app
    path('users/<object_id>/group-invitation/', user_group_invitation, name='invite-user-to-group'),
    path('group-invitation/<object_id>/', toggle_group_invitation, name='toggle-user-to-group'),
]

