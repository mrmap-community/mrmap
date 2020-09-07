"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 09.07.19

"""
from django.urls import path
from editor.autocompletes import KeywordAutocomplete, CategoryAutocomplete, DatasetMetadataAutocomplete, \
    ReferenceSystemAutocomplete, ServiceMetadataAutocomplete
from editor.views import *

app_name = 'editor'
urlpatterns = [
    # ToDo: move the autocomplete paths behind view to secure them
    path('keyword-autocomplete/', KeywordAutocomplete.as_view(create_field="keyword"), name="keyword-autocomplete"),
    path('category-autocomplete/', CategoryAutocomplete.as_view(), name="category-autocomplete"),
    path('metadata-autocomplete/', DatasetMetadataAutocomplete.as_view(), name="metadata-autocomplete"),
    path('service-autocomplete/', ServiceMetadataAutocomplete.as_view(), name="service-autocomplete"),
    path('reference-system-autocomplete/', ReferenceSystemAutocomplete.as_view(), name="reference-system-autocomplete"),

    path('metadata/<metadata_id>', edit, name='edit'),

    path('dataset/wizard', add_new_dataset_wizard, name="dataset-metadata-wizard-new"),
    path('dataset/wizard/<metadata_id>', edit_dataset_wizard, name="dataset-metadata-wizard-instance"),

    path('dataset/remove/<metadata_id>', remove_dataset, name='remove-dataset-metadata'),
    path('access/<object_id>', edit_access, name='edit_access'),
    path('access/<metadata_id>/<group_id>/geometry-form/', access_geometry_form, name='access_geometry_form'),
    path('restore/<metadata_id>', restore, name='restore'),
    path('restore-dataset-metadata/<metadata_id>', restore_dataset_metadata, name='restore-dataset-metadata'),
]
