from django.urls import path

from service.views import *

app_name='service'
urlpatterns = [
    path('', index, name='index'),
    path('/<service_type>', index, name='index'),
    path('session', set_session, name='session'),
    path('activate/<id>', activate, name='activate'),

    path('metadata/<int:id>', get_service_metadata, name='get-service-metadata'),
    path('metadata/dataset/<int:id>', get_dataset_metadata, name='get-dataset-metadata'),
    path('metadata/dataset/check/<int:id>', get_dataset_metadata_button, name='get-dataset-metadata-button'),
    path('metadata/preview/<int:id>', get_service_metadata_preview, name='get-service-metadata-preview'),
    path('metadata/html/<int:id>', get_metadata_html, name='get-metadata-html'),

    #path('proxy/metadata/<int:id>', metadata_proxy, name='metadata-proxy'),  # this route seems not to be used - remove by time
    path('metadata/<int:id>/operation', get_metadata_operation, name='metadata-proxy-operation'),
    path('metadata/<int:id>/legend/<int:style_id>', get_metadata_legend, name='metadata-proxy-legend'),

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


