"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 09.07.19

"""
from django.urls import path

from editor.autocompletes import KeywordAutocomplete, CategoryAutocomplete
from editor.views import *

app_name = 'editor'
urlpatterns = [
    path('', index, name='index'),
    path('keyword-autocomplete/', KeywordAutocomplete.as_view(create_field="keyword"), name="keyword-autocomplete"),
    path('category-autocomplete/', CategoryAutocomplete.as_view(), name="category-autocomplete"),
    path('wms/', index_wms, name='wms-index'),
    path('wfs/', index_wfs, name='wfs-index'),
    path('datasets/', index_datasets, name='datasets-index'),
    path('metadata/<metadata_id>', edit, name='edit'),
    path('dataset/<metadata_id>', edit_dataset, name='edit-dataset-metadata'),
    path('access/<id>', edit_access, name='edit_access'),
    path('access/<id>/geometry-form/', access_geometry_form, name='access_geometry_form'),
    path('restore/<id>', restore, name='restore'),
]
