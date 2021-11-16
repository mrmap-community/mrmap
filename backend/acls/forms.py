from django import forms
from dal import autocomplete
from acls.models.acls import AccessControlList
from django.contrib.auth import get_user_model


class AccessControlListChangeForm(forms.ModelForm):
    users = forms.ModelMultipleChoiceField(
        queryset=get_user_model().objects.all(),
        required=False,
        # Use the pretty 'filter_horizontal widget'.
        widget=autocomplete.ModelSelect2(url='users.autocomplete:mrmapuser_ac'),
    )

    class Meta:
        model = AccessControlList
        fields = ('name', 'description', )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            # Populate the users field with the current Group users.
            self.fields['users'].initial = self.instance.user_set.all()

    def save_m2m(self):
        # Add the users to the Group.
        self.instance.user_set.set(self.cleaned_data['users'])

    def save(self, *args, **kwargs):
        # Default save
        instance = super().save()
        # Save many-to-many data
        self.save_m2m()
        return instance
