from django import forms

from main.forms import Form
from registry.enums.service import OGCServiceEnum
from registry.models import Service


class StartHarvest(Form):
    service = forms.ModelChoiceField(queryset=Service.objects.filter(service_type__name=OGCServiceEnum.CSW.value))
