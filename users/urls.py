"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.05.19

"""
from django.contrib.auth.views import LogoutView
from django.urls import path
from .views import *

urlpatterns = [
    path('', home_view, name="home"),
    path('accounts/login', MrMapLoginView.as_view(), name="login"),
    path('accounts/login', MrMapLoginView.as_view(), name="password_reset_done"),
    path('accounts/login', MrMapLoginView.as_view(), name="password_reset_complete"),
    path('accounts/logout', LogoutView.as_view(), name='logout'),
    path('accounts/password_reset', MrMapPasswordResetView.as_view(), name='password_reset'),
    path('accounts/reset/<uidb64>/<token>/',
         PasswordResetConfirmView.as_view(template_name='users/views/logged_out/password_reset_or_confirm.html'),
         name='password_reset_confirm'),
    path('accounts/signup', SignUpView.as_view(), name='signup'),
    # todo: refactor as class based view
    path('activate/<activation_hash>', activate_user, name='activate-user'),

    # user specific views of his profile
    path('accounts/profile', ProfileView.as_view(), name="profile"),
    path('accounts/profile', ProfileView.as_view(), name="password_change_done"),
    path('accounts/profile/password-change', MrMapPasswordChangeView.as_view(), name="password_change"),
    path('accounts/profile/edit', EditProfileView.as_view(), name="edit_profile"),

    # user subscriptions
    path('accounts/profile/subscriptions', SubscriptionTableView.as_view(), name='manage_subscriptions'),
    path('accounts/profile/subscriptions/add', AddSubscriptionView.as_view(), name='add_subscription'),
    path('accounts/profile/subscriptions/<pk>/edit', UpdateSubscriptionView.as_view(), name='edit_subscription'),
    path('accounts/profile/subscriptions/<pk>/delete', DeleteSubscriptionView.as_view(), name='delete_subscription'),
]
