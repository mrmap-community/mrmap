"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 05.05.20

"""
from django.apps import AppConfig


class CswConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'csw'
