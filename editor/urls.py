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
    # todo: all autocomplete views should be moved to the service (resource) app
    path('keyword-autocomplete/', KeywordAutocomplete.as_view(create_field="keyword"), name="keyword-autocomplete"),
    path('category-autocomplete/', CategoryAutocomplete.as_view(), name="category-autocomplete"),
    path('metadata-autocomplete/', DatasetMetadataAutocomplete.as_view(), name="metadata-autocomplete"),
    path('service-autocomplete/', ServiceMetadataAutocomplete.as_view(), name="service-autocomplete"),
    path('reference-system-autocomplete/', ReferenceSystemAutocomplete.as_view(), name="reference-system-autocomplete"),

    path('metadata/<pk>/edit', EditMetadata.as_view(), name='edit'),
    path('dataset/<pk>/delete', DatasetDelete.as_view(), name='remove-dataset-metadata'),
    path('metadata/<pk>/restore', RestoreMetadata.as_view(), name='restore'),
    # todo refactor this as generic view
    path('access/<pk>/general', GeneralAccessSettingsView.as_view(), name='general-access-settings'),
    path('access/<pk>/table', GroupAccessTable.as_view(), name='edit-group-table'),
    path('access/<pk>/<group_pk>/restrict', RestrictAccessSpatiallyView.as_view(), name='restrict-access-spatially'),
    path('access/<pk>', AccessEditorView.as_view(), name='edit-access'),

    #path('access/<pk>', edit_access, name='edit_access'),
    #path('access/<metadata_id>/<group_id>/geometry-form/', access_geometry_form, name='access_geometry_form'),

    # wizards
    path('dataset/add',
         NewDatasetWizard.as_view(form_list=DATASET_WIZARD_FORMS, ignore_uncomitted_forms=True),
         name="dataset-metadata-wizard-new"),
    path('dataset/<pk>/edit',
         EditDatasetWizard.as_view(form_list=DATASET_WIZARD_FORMS, ignore_uncomitted_forms=True),
         name="dataset-metadata-wizard-instance"),

]
