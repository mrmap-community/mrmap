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
    path('login', MrMapLoginView.as_view(), name="login"),
    path('logout/', LogoutView.as_view(), name='logout'),
    # todo: refactor as class based view
    path('register/', register, name='register'),
    path('password-reset/', password_reset, name='password-reset'),
    path('activate/<activation_hash>', activate_user, name='activate-user'),

    path('accounts/profile', ProfileView.as_view(), name="password_change_done"),
    path('accounts/profile/password-change', MrMapPasswordChangeView.as_view(), name="password_change"),
    path('accounts/profile/edit', EditProfileView.as_view(), name="edit_profile"),

    # user subscriptions
    path('accounts/profile/subscriptions', SubscriptionTableView.as_view(), name='manage_subscriptions'),
    path('accounts/profile/subscriptions/add', AddSubscriptionView.as_view(), name='add_subscription'),
    path('accounts/profile/subscriptions/<pk>/edit', UpdateSubscriptionView.as_view(), name='edit_subscription'),
    path('accounts/profile/subscriptions/<pk>/delete', DeleteSubscriptionView.as_view(), name='delete_subscription'),
]
