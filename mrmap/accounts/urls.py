from accounts.views import auth as auth_views
from accounts.views import groups as group_views
from accounts.views import users as user_views
from django.urls import path
from rest_framework_extensions.routers import ExtendedSimpleRouter

app_name = 'accounts'

router = ExtendedSimpleRouter(trailing_slash=False)
(
    router.register(r'users', user_views.UserViewSet, basename='user')
          .register(r'groups', group_views.NestedGroupViewSet, basename='user-groups', parents_query_lookups=['user']),
    router.register(r'users', user_views.UserViewSet, basename='user')
          .register(r'organizations', group_views.NestedOrganizationViewSet, basename='user-organizations', parents_query_lookups=['user']),
    router.register(r'groups', group_views.GroupViewSet,
                    basename='group'),
    router.register(r'organizations',
                    group_views.OrganizationViewSet, basename='organization'),
    router.register(r'permissions', auth_views.PermissionViewSet,
                    basename='permission'),

)

urlpatterns = router.urls
urlpatterns.extend([
    path('who-am-i/', auth_views.WhoAmIView.as_view(), name='whoami'),
])
