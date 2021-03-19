from django.urls import path

from guardian_roles.wizards import CreateOrganizationWizard, CREATE_ORGANIZATION_WIZARD_FORMS
from structure.views import *

app_name = 'structure'
urlpatterns = [

    # PendingTask
    path('tasks/<pk>/remove', PendingTaskDelete.as_view(), name='remove-task'),
    path('error-reports/<pk>', ErrorReportDetailView.as_view(), name='generate-error-report'),

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
    path('organizations/new', CreateOrganizationWizard.as_view(form_list=CREATE_ORGANIZATION_WIZARD_FORMS,), name='organization_new'),
    path('organizations/<pk>', OrganizationDetailView.as_view(), name='organization_details'),
    path('organizations/<pk>/edit', OrganizationEditView.as_view(), name='organization_edit'),
    path('organizations/<pk>/remove', OrganizationDeleteView.as_view(), name='organization_remove'),
    path('organizations/<pk>/members', OrganizationMembersTableView.as_view(), name='organization_members'),
    path('organizations/<pk>/publishers', OrganizationPublishersTableView.as_view(), name='organization_publisher_overview'),

    # PublishRequests
    path('publish-requests', PublishRequestTableView.as_view(), name='publish_request_overview'),
    path('publish-requests/new', PublishRequestNewView.as_view(), name='publish_request_new'),
    path('publish-requests/<pk>/accept', PublishRequestAcceptView.as_view(), name='publish_request_accept'),

    # GroupInvitationRequests
    path('group-invitation-request', GroupInvitationRequestTableView.as_view(), name='group_invitation_request_overview'),
    path('group-invitation-request/new', GroupInvitationRequestNewView.as_view(), name='group_invitation_request_new'),
    path('group-invitation-request/<pk>/accept', GroupInvitationRequestAcceptView.as_view(), name='group_invitation_request_accept'),

    # users
    path('users', UserTableView.as_view(), name='users_overview'),
]

