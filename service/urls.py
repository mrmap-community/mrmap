from django.urls import path
from service.views import *

app_name='service'
urlpatterns = [
    path('', index, name='index'),
    path('wms/', wms, name='wms'),
    path('wfs/', wfs, name='wfs'),
]
