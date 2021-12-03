from django.urls import path
from rest_framework_extensions.routers import ExtendedSimpleRouter

from auth.views import groups as group_views
from auth.views import users as user_views

app_name = 'auth'

nested_api_router = ExtendedSimpleRouter()
(
    nested_api_router.register(
        r'users', user_views.UserViewSet, basename='user')
    .register(r'groups', group_views.GroupViewSet, basename='user-groups', parents_query_lookups=['user']),
    nested_api_router.register(
        r'users', user_views.UserViewSet, basename='user')
    .register(r'organizations', group_views.OrganizationViewSet, basename='user-organizations', parents_query_lookups=['user']),
    nested_api_router.register(
        r'groups', group_views.GroupViewSet, basename='group'),
    nested_api_router.register(
        r'organizations', group_views.OrganizationViewSet, basename='organization'),
)

urlpatterns = nested_api_router.urls
urlpatterns.extend([
    path('login/', user_views.LoginView.as_view(), name='login'),
    path('logout/', user_views.LogoutView.as_view(), name='logout'),
    path('users/<pk>/relationships/<related_field>',
         user_views.UserRelationshipView.as_view(), name='user-relationships'),
])
