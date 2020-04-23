from django.urls import path

from service.views import *

app_name = 'service'
urlpatterns = [
    path('', index, name='index'),

    path('metadata/<metadata_id>', get_service_metadata, name='get-service-metadata'),
    path('metadata/dataset/<metadata_id>', get_dataset_metadata, name='get-dataset-metadata'),
    path('metadata/preview/<metadata_id>', get_service_metadata_preview, name='get-service-metadata-preview'),
    path('metadata/html/<metadata_id>', get_metadata_html, name='get-metadata-html'),

    path('metadata/<metadata_id>/operation', get_operation_result, name='metadata-proxy-operation'),
    path('metadata/<metadata_id>/legend/<int:style_id>', get_metadata_legend, name='metadata-proxy-legend'),

    path('update/new/<metadata_id>', new_update_service, name='new-update'),
    path('update/pending/<metadata_id>', pending_update_service, name='pending-update'),

    path('remove/<metadata_id>', remove, name='remove'),
    path('activate/<service_id>', activate, name='activate'),
    path('add/', add, name='add'),

    path('pending-tasks/', pending_tasks, name="pending-tasks"),

    path('wms/', wms_index, name='wms-index'),
    path('wfs/', wfs_index, name='wfs-index'),

    path('detail/<metadata_id>', detail, name='detail'),
]


