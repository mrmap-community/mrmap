from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from users.models.groups import Organization
from extras.forms import ModelForm


class OrganizationChangeForm(ModelForm):
    """
    ModelForm that adds handling for reverse relation `publishers` for the given `Organization`.
    """
    publishers = forms.ModelMultipleChoiceField(
        queryset=Organization.objects.none(),
        required=False,
        help_text=_('All organizations which can publish for this organization')
    )

    class Meta:
        model = Organization
        fields = '__all__'
        exclude = ('can_publish_for', )

    def __init__(self, *args, **kwargs):
        super(OrganizationChangeForm, self).__init__(*args, **kwargs)
        if self.instance.pk:
            publishers = Organization.objects.filter(can_publish_for=self.instance).values_list('pk', flat=True)
            self.initial['publishers'] = publishers
            self.fields['publishers'].queryset = Organization.objects.filter(~Q(pk=self.instance.pk))

    def save(self, *args, **kwargs):
        saved_object = super(OrganizationChangeForm, self).save(*args, **kwargs)
        init_publishers = Organization.objects.filter(id__in=self.initial['publishers'])

        removed_publishers = init_publishers.exclude(id__in=self.cleaned_data['publishers'])
        added_publishers = self.cleaned_data['publishers'].exclude(id__in=self.initial['publishers'])

        for publisher in removed_publishers:
            publisher.can_publish_for.remove(self.instance)

        for publisher in added_publishers:
            publisher.can_publish_for.add(self.instance)

        return saved_object
