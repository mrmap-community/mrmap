"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 09.07.19

"""
from django.urls import path
from editor.views import *
from editor.wizards import NewDatasetWizard, EditDatasetWizard, DATASET_WIZARD_FORMS, AccessEditorWizard, \
    ACCESS_EDITOR_WIZARD_FORMS

app_name = 'editor'
urlpatterns = [

    # was moved to the service app
    # path('metadata/<pk>/edit', EditMetadata.as_view(), name='edit'),
    # path('metadata/<pk>/restore', RestoreMetadata.as_view(), name='restore'),
    # path('dataset/<pk>/delete', DatasetDelete.as_view(), name='remove-dataset-metadata'),

    path('access/<pk>/table', AllowedOperationTableView.as_view(), name='allowed-operations'),

    # access editor wizard moved to the service app
    # path('access/<pk>/edit', AccessEditorWizard.as_view(form_list=ACCESS_EDITOR_WIZARD_FORMS),
    #     name='access-editor-wizard'),

    # dataset wizard
    path('dataset/add',
         NewDatasetWizard.as_view(form_list=DATASET_WIZARD_FORMS, ignore_uncomitted_forms=True),
         name="dataset-metadata-wizard-new"),
    #path('dataset/<pk>/edit',
    #     EditDatasetWizard.as_view(form_list=DATASET_WIZARD_FORMS, ignore_uncomitted_forms=True),
    #     name="dataset-metadata-wizard-instance"),

]
