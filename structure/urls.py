from django.urls import path
from structure.views import *

app_name = 'structure'
urlpatterns = [

    # PendingTask
    path('tasks/<pk>/remove', PendingTaskDelete.as_view(), name='remove-task'),
    path('report/error/<report_id>', generate_error_report, name='generate-error-report'),

    path('', index, name='index'),

    # MrMapGroup
    path('groups', MrMapGroupTableView.as_view(), name='groups-index'),
    path('groups/<pk>', MrMapGroupDetailView.as_view(), name='detail-group'),
    path('groups/<pk>/edit', EditGroupView.as_view(), name='edit-group'),
    
    path('groups/<object_id>/leave', leave_group, name='leave-group'),
    path('groups/<object_id>/remove', remove_group, name='delete-group'),
    path('groups/new', new_group, name='new-group'),

    path('groups/<group_id>/publishers', list_publisher_group, name='publisher-group'),

    path('groups/<object_id>/user/<user_id>', remove_user_from_group, name='remove-user-from-group'),

    path('publish-request/<object_id>/', toggle_publish_request, name='toggle-publish-request'),

    # Organization
    path('organizations/', organizations_index, name='organizations-index'),
    path('organizations/detail/<object_id>', detail_organizations, name='detail-organization'),
    path('organizations/edit/<object_id>', edit_org, name='edit-organization'),
    path('organizations/delete/<object_id>', remove_org, name='delete-organization'),
    path('organizations/create-publish-request/<org_id>/', publish_request, name='publish-request'),
    path('organizations/<org_id>/remove-publisher/<group_id>/', remove_publisher, name='remove-publisher'),
    path('organizations/new/register-form/', new_org, name='new-organization'),

    path('users/', users_index, name='users-index'),
    path('users/<object_id>/group-invitation/', user_group_invitation, name='invite-user-to-group'),

    path('group-invitation/<object_id>/', toggle_group_invitation, name='toggle-user-to-group'),
]

