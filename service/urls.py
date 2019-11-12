from django.urls import path
from service.views import *

app_name='service'
urlpatterns = [
    path('', index, name='index'),
    path('/<service_type>', index, name='index'),
    path('session', set_session, name='session'),
    path('activate/', activate, name='activate'),

    path('metadata/<int:id>', get_service_metadata, name='get-service-metadata'),
    path('metadata/dataset/<int:id>', get_dataset_metadata, name='get-dataset-metadata'),
    path('metadata/dataset/check/<int:id>', get_dataset_metadata_button, name='get-dataset-metadata-button'),
    path('metadata/proxy/<int:id>', metadata_proxy, name='metadata-proxy'),
    path('metadata/proxy/operation/<int:id>', metadata_proxy_operation, name='metadata-proxy-operation'),

    path('capabilities/<int:id>', get_capabilities, name='get-capabilities'),
    path('capabilities/<int:id>/original', get_capabilities_original, name='get-capabilities-original'),

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


