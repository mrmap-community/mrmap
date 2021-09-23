"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.05.19

"""
from django.contrib.auth import views as django_views
from django.urls import path
from users.views import users as users_views
from users.views import groups as groups_views

urlpatterns = [
    # Dashboard
    path('', users_views.HomeView.as_view(), name="home"),

    path('login/', users_views.MrMapLoginView.as_view(), name="login"),
    path('login/', users_views.MrMapLoginView.as_view(), name="password_reset_done"),
    path('login/', users_views.MrMapLoginView.as_view(), name="password_reset_complete"),
    path('logout', django_views.LogoutView.as_view(), name='logout'),
    path('password_reset/', users_views.MrMapPasswordResetView.as_view(), name='password_reset'),
    path('reset/<uidb64>/<token>/',
         django_views.PasswordResetConfirmView.as_view(template_name='users/views/logged_out/password_reset_or_confirm.html'),
         name='password_reset_confirm'),
    path('signup/', users_views.SignUpView.as_view(), name='signup'),
    path('activate/<pk>', users_views.ActivateUser.as_view(), name='activate-user'),

    # user specific views of his profile
    path('profile', users_views.ProfileView.as_view(), name="profile"),
    path('profile', users_views.ProfileView.as_view(), name="password_change_done"),
    path('profile/password-change', users_views.MrMapPasswordChangeView.as_view(), name="password_change"),
    path('profile/edit', users_views.EditProfileView.as_view(), name="edit_profile"),

    # user subscriptions
    path('profile/subscriptions', users_views.SubscriptionTableView.as_view(), name='subscription_list'),
    path('profile/subscriptions/add', users_views.AddSubscriptionView.as_view(), name='subscription_add'),
    path('profile/subscriptions/<pk>/edit', users_views.UpdateSubscriptionView.as_view(), name='subscription_change'),
    path('profile/subscriptions/<pk>/delete', users_views.DeleteSubscriptionView.as_view(), name='subscription_delete'),

    # Organizations
    path('organizations', groups_views.OrganizationTableView.as_view(), name='organization_list'),
    path('organizations/<pk>', groups_views.OrganizationDetailView.as_view(), name='organization_view'),
    path('organizations/<pk>/change', groups_views.OrganizationUpdateView.as_view(), name='organization_change'),
    path('organizations/<pk>/publishers', groups_views.OrganizationPublishersTableView.as_view(), name='organization_publisher_list'),

    # PublishRequests
    path('publish-requests', groups_views.PublishRequestTableView.as_view(), name='publish_request_list'),
    path('publish-requests/new', groups_views.PublishRequestCreateView.as_view(), name='publish_request_add'),
    path('publish-requests/<pk>/change', groups_views.PublishRequestUpdateView.as_view(), name='publishrequest_change'),

    # users
    path('users', users_views.UserTableView.as_view(), name='users_list'),
]
