from django import forms
from django.utils.translation import gettext_lazy as _
from guardian_roles.models.core import TemplateRole
from structure.models import Organization


class OrganizationModelForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = '__all__'


class TemplateRoleSelection(forms.Form):
    based_templates = forms.ModelMultipleChoiceField(
        queryset=TemplateRole.objects.all(),
        label=_("Based templates"),
        help_text=_("Choice which templates should be used to configure administration roles in your Organization"),
    )
