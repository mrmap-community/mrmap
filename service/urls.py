from django.urls import path
from service.views import *

app_name='service'
urlpatterns = [
    path('', index, name='index'),
    path('new/', new_service, name='wms'),
    path('new/register-form', register_form, name='wms'),
    path('wms/', wms, name='wms'),
    path('wfs/', wfs, name='wfs'),
]
