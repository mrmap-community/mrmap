from django import forms
from extras.forms import ModelForm
from registry.models import ServiceMetadata, Keyword, MetadataContact, DatasetMetadata, ReferenceSystem
from dal import autocomplete


class MetadataContactModelForm(ModelForm):
    class Meta:
        model = MetadataContact
        fields = '__all__'


class ServiceMetadataModelForm(ModelForm):
    keywords = forms.ModelMultipleChoiceField(queryset=Keyword.objects.all(),
                                              widget=autocomplete.ModelSelect2Multiple(url='registry.autocomplete:keyword_ac'),)
    metadata_contact = forms.ModelChoiceField(queryset=MetadataContact.objects.all(),
                                              widget=autocomplete.ModelSelect2(url="registry.autocomplete:metadata_contact_ac"))

    class Meta:
        model = ServiceMetadata
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["metadata_contact"].queryset = self.request.user.get_instances(klass=MetadataContact)


class DatasetMetadataModelForm(ModelForm):
    keywords = forms.ModelMultipleChoiceField(queryset=Keyword.objects.all(),
                                              widget=autocomplete.ModelSelect2Multiple(url='registry.autocomplete:keyword_ac'),)
    reference_systems = forms.ModelMultipleChoiceField(queryset=ReferenceSystem.objects.all(),
                                                       widget=autocomplete.ModelSelect2Multiple(url='registry.autocomplete:reference_system_ac'), )

    class Meta:
        model = DatasetMetadata
        fields = '__all__'
