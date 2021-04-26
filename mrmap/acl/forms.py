from django import forms

from acl.models.acl import AccessControlList


class AccessControlListChangeForm(forms.ModelForm):

    class Meta:
        model = AccessControlList
        fields = '__all__'
        #exclude = ('can_publish_for', )
