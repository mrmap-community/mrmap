from django.urls import path
from user.views import *

app_name='user'
urlpatterns = [
    path('', login, name='login'),
    path('logout/', logout, name='logout'),
    path('index/', index, name='index'),
    path('groups/', groups, name='groups'),
    path('organizations/', organizations, name='organizations'),
]
