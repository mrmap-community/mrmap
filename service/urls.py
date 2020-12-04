from django.urls import path

from service.views import *

app_name = 'resource'
urlpatterns = [
    path('', index, name='index'),

    path('pending-tasks/', login_required(PendingTaskView.as_view()), name="pending-tasks"),
    path('wms/', login_required(WmsIndexView.as_view()), name='wms-index'),
    path('wfs/', login_required(WfsIndexView.as_view()), name='wfs-index'),
    path('csw/', login_required(CswIndexView.as_view()), name='csw-index'),
    path('datasets/', login_required(DatasetIndexView.as_view()), name='datasets-index'),


    path('metadata/<metadata_id>', get_service_metadata, name='get-service-metadata'),
    path('metadata/<metadata_id>/subscribe', metadata_subscription_new, name='subscription-new'),
    path('metadata/dataset/<metadata_id>', get_dataset_metadata, name='get-dataset-metadata'),
    path('metadata/html/<metadata_id>', get_metadata_html, name='get-metadata-html'),

    path('metadata/<metadata_id>/operation', get_operation_result, name='metadata-proxy-operation'),
    path('metadata/<metadata_id>/legend/<int:style_id>', get_metadata_legend, name='metadata-proxy-legend'),

    path('preview/<metadata_id>', get_service_preview, name='get-service-metadata-preview'),

    path('new-update/<metadata_id>', new_pending_update_service, name='new-pending-update'),
    path('pending-update/<metadata_id>', pending_update_service, name='pending-update'),
    path('dismiss-pending-update/<metadata_id>', dismiss_pending_update_service, name='dismiss-pending-update'),
    path('run-update/<metadata_id>', run_update_service, name='run-update'),

    path('remove/<metadata_id>', remove, name='remove'),
    path('activate/<metadata_id>', activate, name='activate'),
    path('add/', add, name='add'),

    path('detail/<object_id>', detail, name='detail'),

    path('logs/', logs_view, name='logs-view'),
    path('logs/download/', logs_download, name='logs-download'),
]

