from django.urls import path

from guardian_roles.views.views import OrganizationBasedTemplateRoleView, OrganizationBasedTemplateRoleDetailView, \
    OrganizationBasedTemplateRoleMembersTableView, OrganizationBasedTemplateRoleChangeView

app_name = 'guardian_roles'
urlpatterns = [
    # Organization Roles
    path('', OrganizationBasedTemplateRoleView.as_view(), name='organization_roles_overview'),
    path('<pk>', OrganizationBasedTemplateRoleDetailView.as_view(), name='organization_role_detail'),
    path('<pk>/edit', OrganizationBasedTemplateRoleChangeView.as_view(), name='organization_role_edit'),
    path('<pk>/members', OrganizationBasedTemplateRoleMembersTableView.as_view(), name='organization_role_detail_members'),
]

