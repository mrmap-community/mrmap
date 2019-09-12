"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 09.07.19

"""
from django.urls import path

from editor.views import *

app_name='editor'
urlpatterns = [
    path('', index, name='index'),
    path('edit/<id>', edit, name='edit'),
    path('edit/featuretype/<id>', edit_featuretype, name='edit-featuretype'),
    path('restore/<id>', restore, name='restore'),
    #path('restore/featuretype/<id>', restore_featuretype, name='restore-featuretype'),
]
