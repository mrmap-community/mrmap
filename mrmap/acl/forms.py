from django import forms
from dal import autocomplete
from acl.models.acl import AccessControlList


class AccessControlListChangeForm(forms.ModelForm):
    class Meta:
        model = AccessControlList
        fields = '__all__'
        widgets = {
            'permissions': autocomplete.ModelSelect2Multiple(url='autocompletes:permissions'),
            'owned_by_org': autocomplete.ModelSelect2(url='autocompletes:organizations'),
            'accessible_metadata': autocomplete.ModelSelect2Multiple(url='autocompletes:metadata')
        }
        exclude = ('accessible_accesscontrollist',)
