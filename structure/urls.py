from django.urls import path
from structure.views import *

app_name = 'structure'
urlpatterns = [
    path('', index, name='index'),
    path('remove', remove, name='remove'),
    path('detail-group/<id>', detail_group, name='detail-group'),
]
