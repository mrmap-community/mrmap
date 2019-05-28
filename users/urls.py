"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.05.19

"""

from django.urls import path

from .views import *

urlpatterns = [
    path('', login, name="login"),
    path('account', account, name="account"),
    path('users/password/edit/', password_change, name="password-change"),
    path('users/edit/', account_edit, name="account-edit"),
    path('logout/', logout, name='logout'),
    path('password-reset/', password_reset, name='password-reset'),
    path('register/', register, name='register'),
    path('activate/<activation_hash>', activate_user, name='activate-user'),
]