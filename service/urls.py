from django.urls import path
from service.views import *

app_name='service'
urlpatterns = [
    path('', index, name='index'),
    path('/<service_type>', index, name='index'),
    path('session', session, name='session'),
    path('activate/', activate, name='activate'),

    path('new/register-form', register_form, name='register-form'),
    path('new/', new_service, name='wms'),

    path('update/register-form/<id>', update_service_form, name='register-form'),
    path('update/<id>', update_service, name='update-service'),

    path('remove', remove, name='remove'),

    path('wms/', wms, name='wms'),
    path('wfs/', wfs, name='wfs'),
    path('wms/detail/<int:id>', detail, name='detail-wms'),
    path('wfs/detail/<int:id>', detail, name='detail-wfs'),
]
