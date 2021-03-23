from django.urls import path

from guardian_roles.views.views import OwnerBasedTemplateRoleView, OwnerBasedTemplateRoleDetailView, \
    OwnerBasedTemplateRoleMembersTableView, OwnerBasedTemplateRoleChangeView

app_name = 'guardian_roles'
urlpatterns = [
    # Owner Roles
    path('', OwnerBasedTemplateRoleView.as_view(), name='owner_roles_overview'),
    path('<pk>', OwnerBasedTemplateRoleDetailView.as_view(), name='owner_role_detail'),
    path('<pk>/edit', OwnerBasedTemplateRoleChangeView.as_view(), name='owner_role_edit'),
    path('<pk>/members', OwnerBasedTemplateRoleMembersTableView.as_view(), name='owner_role_detail_members'),
]

