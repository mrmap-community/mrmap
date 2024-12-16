from django.urls import path

from metadata.views import DatasetMetadataDetailView

app_name = 'metadata'

urlpatterns = [
    path("dataset/<uuid:pk>", DatasetMetadataDetailView.as_view(template_name="metadata/dataset.html"), name="datasetmetadata"),
    # path("dataset/<uuid:pk>", views.home, name="home"),
]

