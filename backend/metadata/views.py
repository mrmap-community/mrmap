from django.shortcuts import render
from django.views.generic import DetailView
from registry.models.metadata import DatasetMetadataRecord

class DatasetMetadataDetailView(DetailView):
    model = DatasetMetadataRecord
    context_object_name = "metadata"
