from django.urls import path
from resourceNew.views import MapContextCreateView

app_name = 'resourceNew'
urlpatterns = [
    # actions
    path('service/add', MapContextCreateView.as_view(), name='add_service'),
]

