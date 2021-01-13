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
from editor.wizards import NewDatasetWizard, EditDatasetWizard, DATASET_WIZARD_FORMS

app_name = 'editor'
urlpatterns = [
    path('keyword-autocomplete/', KeywordAutocomplete.as_view(create_field="keyword"), name="keyword-autocomplete"),
    path('category-autocomplete/', CategoryAutocomplete.as_view(), name="category-autocomplete"),
    path('metadata-autocomplete/', DatasetMetadataAutocomplete.as_view(), name="metadata-autocomplete"),
    path('service-autocomplete/', ServiceMetadataAutocomplete.as_view(), name="service-autocomplete"),
    path('reference-system-autocomplete/', ReferenceSystemAutocomplete.as_view(), name="reference-system-autocomplete"),

    # todo refactor this as generic view
    path('metadata/<metadata_id>', edit, name='edit'),

    # wizards
    path('dataset/add',
         NewDatasetWizard.as_view(form_list=DATASET_WIZARD_FORMS, ignore_uncomitted_forms=True),
         name="dataset-metadata-wizard-new"),
    path('dataset/<pk>/edit',
         EditDatasetWizard.as_view(form_list=DATASET_WIZARD_FORMS, ignore_uncomitted_forms=True),
         name="dataset-metadata-wizard-instance"),

    # todo refactor this as generic view
    path('dataset/remove/<metadata_id>', remove_dataset, name='remove-dataset-metadata'),
    path('access/<object_id>', edit_access, name='edit_access'),
    path('access/<metadata_id>/<group_id>/geometry-form/', access_geometry_form, name='access_geometry_form'),
    path('restore/<metadata_id>', restore, name='restore'),
    path('restore-dataset-metadata/<metadata_id>', restore_dataset_metadata, name='restore-dataset-metadata'),
]
