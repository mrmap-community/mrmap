from django.urls import path

from service.views import *

app_name = 'service'
urlpatterns = [
    path('', index, name='index'),
    path('session', set_session, name='session'),
    path('activate/<id>', activate, name='activate'),

    path('metadata/<int:id>', get_service_metadata, name='get-service-metadata'),
    path('metadata/dataset/<int:id>', get_dataset_metadata, name='get-dataset-metadata'),
    path('metadata/dataset/check/<int:id>', check_for_dataset_metadata, name='check-for-dataset-metadata'),
    path('metadata/preview/<int:id>', get_service_metadata_preview, name='get-service-metadata-preview'),
    path('metadata/html/<int:id>', get_metadata_html, name='get-metadata-html'),

    path('metadata/<int:id>/operation', get_operation_result, name='metadata-proxy-operation'),
    path('metadata/<int:id>/legend/<int:style_id>', get_metadata_legend, name='metadata-proxy-legend'),

    path('update/register-form/<id>', update_service_form, name='register-form'),
    path('update/<id>', update_service, name='update-service'),
    path('update/discard/', discard_update, name='update-discard'),

    path('remove/<id>', remove, name='remove'),

    path('pending-tasks/', pending_tasks, name="pending-tasks"),

    path('wms/', wms_index, name='wms-index'),
    path('wfs/', wfs_index, name='wfs-index'),

    path('detail/<int:id>', detail, name='detail'),
]


