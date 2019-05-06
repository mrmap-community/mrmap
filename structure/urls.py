from django.urls import path
from structure.views import *

app_name='structure'
urlpatterns = [
    path('', login, name='login'),
    path('logout/', logout, name='logout'),
    path('index/', index, name='index'),
    path('groups/', groups, name='groups'),
    path('organizations/', organizations, name='organizations'),
]
