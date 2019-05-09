from django.urls import path
from structure.views import *

app_name = 'structure'
urlpatterns = [
    path('', index, name='index'),
    path('new/', new, name='new'),
    path('remove/', remove, name='remove'),
    path('edit/<id>', edit, name='edit-group'),
    path('detail/<id>', detail_group, name='detail-group'),
]
