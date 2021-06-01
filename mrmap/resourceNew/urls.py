from django.urls import path
from resourceNew.views import service as service_views
from resourceNew.views import metadata as metadata_views

app_name = 'resourceNew'
urlpatterns = [

    path('service/add', service_views.RegisterServiceFormView.as_view(), name='service_add'),

    path("service/wms", service_views.WmsListView.as_view(), name="service_list"),
    path("service/wms/<pk>", service_views.ServiceTreeView.as_view(), name="service_view"),

    path("service/layers", service_views.LayerListView.as_view(), name="layer_list"),

    path("metadata/dataset", metadata_views.DatasetMetadataListView.as_view(), name="dataset_metadata_list"),

]

