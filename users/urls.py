"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.05.19

"""

from django.urls import path

from .views import *
urlpatterns = [
    path('', login_view, name="login"),
    path('home', home_view, name="home"),
    path('account', account, name="account"),
    path('users/password/edit/', password_change, name="password-change"),
    path('users/edit/', account_edit, name="account-edit"),
    path('logout/', logout_view, name='logout'),
    path('password-reset/', password_reset, name='password-reset'),
    path('register/', register, name='register'),
    path('activate/<activation_hash>', activate_user, name='activate-user'),

    path('subscription', subscription_index_view, name='subscription-index'),
    path('subscription/new', subscription_new_view, name='subscription-new'),
    path('subscription/<subscription_id>/edit', subscription_edit_view, name='subscription-edit'),
    path('subscription/<subscription_id>/remove', subscription_remove, name='subscription-remove'),
]