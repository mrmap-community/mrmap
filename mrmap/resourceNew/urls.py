from django.urls import path
from resourceNew import views

app_name = 'resourceNew'
urlpatterns = [

    path('service/add', views.RegisterServiceFormView.as_view(), name='add_service'),

    path("service/wms", views.WmsIndexView.as_view(), name="view_wms_service"),
]

