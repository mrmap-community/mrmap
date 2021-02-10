"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 08.09.20

"""
import django_filters
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from structure.models import MrMapUser


class MrMapUserFilter(django_filters.FilterSet):
    class Meta:
        model = MrMapUser
        fields = ['username', ]
