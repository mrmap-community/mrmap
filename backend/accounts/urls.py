from django.urls import path
from rest_framework_extensions.routers import ExtendedSimpleRouter

from accounts.views import auth as auth_views
from accounts.views import groups as group_views
from accounts.views import users as user_views

app_name = 'accounts'

router = ExtendedSimpleRouter()
(
    router.register(r'users', user_views.UserViewSet, basename='user')
          .register(r'groups', group_views.NestedGroupViewSet, basename='user-groups', parents_query_lookups=['user']),
    router.register(r'users', user_views.UserViewSet, basename='user')
          .register(r'organizations', group_views.NestedOrganizationViewSet, basename='user-organizations', parents_query_lookups=['user']),
    router.register(r'groups', group_views.NestedGroupViewSet, basename='group'),
    router.register(r'organizations', group_views.OrganizationViewSet, basename='organization'),
    router.register(r'permissions', auth_views.PermissionViewSet, basename='permission'),

)

urlpatterns = router.urls
urlpatterns.extend([
    path('login/', auth_views.LoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout')
])
