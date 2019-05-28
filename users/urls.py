"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.05.19

"""

from django.contrib import admin
from django.urls import path, include

from .views import *
urlpatterns = [
    path('', login, name="login"),
    path('logout/', logout, name='logout'),
    path('password-reset/', password_reset, name='password-reset'),
    path('register/', register, name='register'),
    path('activate/<activation_hash>', activate_user, name='activate-user'),
]