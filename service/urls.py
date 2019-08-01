from django.urls import path
from service.views import *

app_name='service'
urlpatterns = [
    path('', index, name='index'),
    path('/<service_type>', index, name='index'),
    path('session', session, name='session'),
    path('activate/', activate, name='activate'),
    path('capabilities/<int:id>', get_capabilities, name='get-capabilities'),

    path('new/register-form', register_form, name='register-form'),
    path('new/', new_service, name='wms'),

    path('update/register-form/<id>', update_service_form, name='register-form'),
    path('update/<id>', update_service, name='update-service'),
    path('update/discard/', discard_update, name='update-discard'),

    path('remove', remove, name='remove'),

    path('wms/', wms, name='wms'),
    path('wfs/', wfs, name='wfs'),
    path('detail/<int:id>', detail, name='detail'),
    path('detail-child/<int:id>', detail_child, name='detail-child'),
]
