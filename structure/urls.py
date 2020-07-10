from django.urls import path
from structure.views import *

app_name = 'structure'
urlpatterns = [
    path('', index, name='index'),

    path('task/remove/<task_id>', remove_task, name='remove-task'),

    path('groups/', groups_index, name='groups-index'),
    path('groups/detail/<object_id>', detail_group, name='detail-group'),
    path('groups/edit/<object_id>', edit_group, name='edit-group'),
    path('groups/delete/<object_id>', remove_group, name='delete-group'),
    path('groups/new/register-form/', new_group, name='new-group'),
    path('groups/publisher/<group_id>', list_publisher_group, name='publisher-group'),

    path('publish-request/<request_id>/accept/', accept_publish_request, name='accept-publish-request'),

    path('organizations/', organizations_index, name='organizations-index'),
    path('organizations/detail/<object_id>', detail_organizations, name='detail-organization'),
    path('organizations/edit/<object_id>', edit_org, name='edit-organization'),
    path('organizations/delete/<object_id>', remove_org, name='delete-organization'),
    path('organizations/create-publish-request/<org_id>/', publish_request, name='publish-request'),
    path('organizations/<org_id>/remove-publisher/<group_id>/', remove_publisher, name='remove-publisher'),
    path('organizations/new/register-form/', new_org, name='new-organization'),

]

