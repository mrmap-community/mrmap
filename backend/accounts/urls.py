from accounts.views import auth as auth_views
from accounts.views import groups as group_views
from accounts.views import roles as role_views
from accounts.views import users as user_views
from django.urls import path
from extras.routers import NestedDefaultRouter

app_name = 'accounts'

router = NestedDefaultRouter(trailing_slash=False)

users_routes = router.register(
    r'users', user_views.UserViewSet, basename='user')
users_routes.register(r'groups', group_views.NestedGroupViewSet,
                      basename='user-groups', parents_query_lookups=['user'])
users_routes.register(r'organizations', group_views.NestedOrganizationViewSet,
                      basename='user-organizations', parents_query_lookups=['user'])
# the roles one user holds, following the rows of ``RoleMembership`` (#736)
users_routes.register(r'roles', role_views.NestedUserRolesViewSet,
                      basename='user-roles',
                      parents_query_lookups=['memberships__user'])

router.register(r'groups', group_views.GroupViewSet,
                basename='group')
orgs_routes = router.register(r'organizations',
                              group_views.OrganizationViewSet,
                              basename='organization')
# the roles of one organization, and its members with their roles in that
# organization (#736)
orgs_routes.register(r'roles', role_views.NestedOrganizationRolesViewSet,
                     basename='organization-roles',
                     parents_query_lookups=['organization'])
# an Organization *is* a Group, so "members of the organization" is the
# plain ``groups`` lookup on the users
orgs_routes.register(r'members', role_views.NestedOrganizationMemberViewSet,
                     basename='organization-members',
                     parents_query_lookups=['groups'])
router.register(r'permissions', auth_views.PermissionViewSet,
                basename='permission')

# the role API of #736: the catalogue, the roles, and the memberships both
# under a role and by their own id
roles_routes = router.register(r'roles', role_views.RoleViewSet,
                               basename='role')
roles_routes.register(r'memberships', role_views.NestedRoleMembershipViewSet,
                      basename='role-memberships',
                      parents_query_lookups=['role'])
router.register(r'roledefinitions', role_views.RoleDefinitionViewSet,
                basename='roledefinition')
router.register(r'memberships', role_views.RoleMembershipViewSet,
                basename='rolemembership')

urlpatterns = router.urls
urlpatterns.extend([
    path('who-am-i/', auth_views.WhoAmIView.as_view(), name='whoami'),
])
