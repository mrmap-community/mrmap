"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 09.07.19

"""
from django.urls import path
from editor.autocompletes import KeywordAutocomplete, CategoryAutocomplete, DatasetMetadataAutocomplete, \
    ReferenceSystemAutocomplete, ServiceMetadataAutocomplete, OperationsAutocomplete, GroupsAutocomplete, \
    UsersAutocomplete, MetadataAutocomplete
from editor.views import *
from editor.wizards import NewDatasetWizard, EditDatasetWizard, DATASET_WIZARD_FORMS, AccessEditorWizard, \
    ACCESS_EDITOR_WIZARD_FORMS

app_name = 'editor'
urlpatterns = [
    # todo: all autocomplete views should be moved to the service (resource) app
    path('keyword-autocomplete/', KeywordAutocomplete.as_view(create_field="keyword"), name="keyword-autocomplete"),
    path('category-autocomplete/', CategoryAutocomplete.as_view(), name="category-autocomplete"),
    path('metadata-autocomplete/', DatasetMetadataAutocomplete.as_view(), name="metadata-autocomplete"),
    path('service-autocomplete/', ServiceMetadataAutocomplete.as_view(), name="service-autocomplete"),
    path('autocomplete-metadata/', MetadataAutocomplete.as_view(), name="autocomplete_metadata"),
    path('reference-system-autocomplete/', ReferenceSystemAutocomplete.as_view(), name="reference-system-autocomplete"),
    path('operations/', OperationsAutocomplete.as_view(), name="operations-autocomplete"),
    path('groups/', GroupsAutocomplete.as_view(), name="groups"),
    path('users/', UsersAutocomplete.as_view(), name="users"),

    # was moved to the service app
    # path('metadata/<pk>/edit', EditMetadata.as_view(), name='edit'),
    path('dataset/<pk>/delete', DatasetDelete.as_view(), name='remove-dataset-metadata'),
    path('metadata/<pk>/restore', RestoreMetadata.as_view(), name='restore'),

    path('access/<pk>/table', AllowedOperationTableView.as_view(), name='allowed-operations'),

    # access editor wizard
    path('access/<pk>/edit', AccessEditorWizard.as_view(form_list=ACCESS_EDITOR_WIZARD_FORMS),
         name='access-editor-wizard'),

    # dataset wizard
    path('dataset/add',
         NewDatasetWizard.as_view(form_list=DATASET_WIZARD_FORMS, ignore_uncomitted_forms=True),
         name="dataset-metadata-wizard-new"),
    path('dataset/<pk>/edit',
         EditDatasetWizard.as_view(form_list=DATASET_WIZARD_FORMS, ignore_uncomitted_forms=True),
         name="dataset-metadata-wizard-instance"),

]
