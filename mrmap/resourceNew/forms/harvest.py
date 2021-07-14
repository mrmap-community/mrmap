from django import forms

from main.forms import Form
from resourceNew.enums.service import OGCServiceEnum
from resourceNew.models import Service


class StartHarvest(Form):
    service = forms.ModelChoiceField(queryset=Service.objects.filter(service_type__name=OGCServiceEnum.CSW.value))
