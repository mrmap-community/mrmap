from dal import autocomplete
from django import forms
from django.utils.translation import gettext_lazy as _
from guardian_roles.models.core import TemplateRole, OrganizationBasedTemplateRole
from structure.models import Organization, MrMapUser


class UserSetChangeForm(forms.ModelForm):
    user_set = forms.ModelMultipleChoiceField(queryset=MrMapUser.objects.all(),
                                              label=_('Members'),
                                              widget=autocomplete.ModelSelect2Multiple(url='editor:users'))

    class Meta:
        model = OrganizationBasedTemplateRole
        fields = ['name']

    def __init__(self, request, *args, **kwargs):
        self.request = request
        super(UserSetChangeForm, self).__init__(*args, **kwargs)
        self.fields['name'].widget = forms.HiddenInput()
        if kwargs.get('instance', None):
            self.fields['user_set'].initial = kwargs.get('instance').user_set.all()

    def save(self, commit=True):
        self.instance.user_set.clear()
        self.instance.user_set.add(*self.cleaned_data['user_set'])
        return self.instance


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
