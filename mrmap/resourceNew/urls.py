from django.urls import path
from resourceNew.views import service as service_views

app_name = 'resourceNew'
urlpatterns = [

    path('service/add', service_views.RegisterServiceFormView.as_view(), name='service_add'),

    path("service/wms", service_views.WmsIndexView.as_view(), name="service_list"),
    path("service/wms/<pk>", service_views.ServiceTreeView.as_view(), name="service_view")
]

