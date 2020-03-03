"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 09.07.19

"""
from django.urls import path

from editor.views import *

app_name = 'editor'
urlpatterns = [
    path('', index, name='index'),
    path('wms/', index_wms, name='wms-index'),
    path('wfs/', index_wfs, name='wfs-index'),
    path('metadata/<id>', edit, name='edit'),
    path('access/<id>', edit_access, name='edit_access'),
    path('access/<id>/geometry-form/', access_geometry_form, name='access_geometry_form'),
    path('restore/<id>', restore, name='restore'),
]
