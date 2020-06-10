"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 09.07.19

"""
from dal import autocomplete
from django.forms import ModelMultipleChoiceField
from django.utils.translation import gettext_lazy as _
from django import forms
from MrMap.forms import MrMapModelForm, MrMapWizardForm, MrMapWizardModelForm
from MrMap.widgets import BootstrapDateTimePickerInput, BootstrapDatePickerInput
from service.helper.enums import MetadataEnum
from service.models import Metadata, MetadataRelation, Keyword, Category, Dataset, ReferenceSystem, TermsOfUse
from service.settings import ISO_19115_LANG_CHOICES
from users.helper import user_helper


class MetadataEditorForm(MrMapModelForm):
    def __init__(self, *args, **kwargs):
        # first call parent's constructor
        super(MetadataEditorForm, self).__init__(*args, **kwargs)

        # there's a `fields` property now
        self.fields['terms_of_use'].required = False
        self.fields['categories'].required = False
        self.fields['keywords'].required = False
        self.has_autocomplete = True

    class Meta:
        model = Metadata
        fields = [
            "title",
            "abstract",
            "access_constraints",
            "terms_of_use",
            "keywords",
            "categories",
        ]
        help_texts = {
            "title": _("Edit the title."),
            "abstract": _("Edit the description. Keep it short and simple."),
            "access_constraints": _("Edit the access constraints."),
            "terms_of_use": _("Select another licence."),
            "keywords": _(""),  # Since keywords are handled differently, this can be empty
            "categories": _("Select categories for this resource."),
        }
        widgets = {
            "categories": autocomplete.ModelSelect2Multiple(
                url='editor:category-autocomplete',
                attrs={
                    "data-containercss": {
                        "height": "3em",
                        "width": "3em",
                    },
                },
            ),
            'keywords': autocomplete.ModelSelect2Multiple(
                url='editor:keyword-autocomplete',
                attrs={
                    "data-containerCss": {
                        "height": "3em",
                        "width": "3em",
                    }
                },
            ),
        }


class MetadataModelMultipleChoiceField(ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        """
            we need to override this function to show the id of the metadata object,
            so the user can differentiate the results where title is equal.
        """
        return "{} #{}".format(obj.title, obj.id)


class ReferenceSystemModelMultipleChoiceField(ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        """
            we need to override this function to show the id of the metadata object,
            so the user can differentiate the results where title is equal.
        """
        return f"{obj.prefix}{obj.code}"


class DatasetIdentificationForm(MrMapWizardForm):
    title = forms.CharField(label=_('Title'),)
    abstract = forms.CharField(label=_('Abstract'), )
    language_code = forms.ChoiceField(label=_('Language'), choices=ISO_19115_LANG_CHOICES)
    character_set_code = forms.ChoiceField(label=_('Character Encoding'), choices=Dataset.CHARACTER_SET_CHOICES)
    date_stamp = forms.DateField(label=_('Metadata creation date'),
                                 widget=BootstrapDatePickerInput())
    reference_system = ReferenceSystemModelMultipleChoiceField(
        queryset=None,
        widget=autocomplete.ModelSelect2Multiple(
            url='editor:reference-system-autocomplete',
            attrs={
                "data-containercss": {
                    "height": "3em",
                    "width": "3em",
                }
            }
        ),
        required=False,)

    additional_related_objects = MetadataModelMultipleChoiceField(
        queryset=None,
        widget=autocomplete.ModelSelect2Multiple(
            url='editor:metadata-autocomplete',

        ),
        required=False, )

    def __init__(self, *args, **kwargs):
        super(DatasetIdentificationForm, self).__init__(
                                                        has_autocomplete_fields=True,
                                                        *args,
                                                        **kwargs)

        self.fields['additional_related_objects'].queryset = user_helper.get_user(self.request).get_metadatas_as_qs(
            type=MetadataEnum.DATASET, inverse_match=True)
        self.fields['reference_system'].queryset = ReferenceSystem.objects.all()

        if self.instance_id:
            metadata = Metadata.objects.get(id=self.instance_id)
            dataset = Dataset.objects.get(id=metadata.dataset.id)
            self.fields['title'].initial = metadata.title
            self.fields['abstract'].initial = metadata.abstract
            self.fields['reference_system'].initial = metadata.reference_system.all()
            self.fields['date_stamp'].initial = dataset.date_stamp
            self.fields['language_code'].initial = dataset.language_code
            self.fields['character_set_code'].initial = dataset.character_set_code

            # ToDo: initial all fields

            self.fields['additional_related_objects'].queryset = self.fields['additional_related_objects'].queryset.exclude(id=self.instance_id)
            metadata_relations = MetadataRelation.objects.filter(metadata_to=self.instance_id)
            additional_related_objects = []
            for metadata_relation in metadata_relations:
                if metadata_relation.origin.name != 'capabilities':
                    additional_related_objects.append(metadata_relation.metadata_from)
            self.fields['additional_related_objects'].initial = additional_related_objects


class DatasetClassificationForm(MrMapWizardForm):
    keywords = ModelMultipleChoiceField(
        label=_('Keywords'),
        queryset=Keyword.objects.all(),
        widget=autocomplete.ModelSelect2Multiple(
            url='editor:keyword-autocomplete',
            attrs={
                "data-containercss": {
                    "height": "3em",
                    "width": "3em",
                },
            },
        ),
        required=False, )
    categories = ModelMultipleChoiceField(
        label=_('Categories'),
        queryset=Category.objects.all(),
        widget=autocomplete.ModelSelect2Multiple(
            url='editor:category-autocomplete',
            attrs={
                "data-containercss": {
                    "height": "3em",
                    "width": "3em",
                },
            },
        ),
        required=False,)

    def __init__(self, *args, **kwargs):
        super(DatasetClassificationForm, self).__init__(
                                                        has_autocomplete_fields=True,
                                                        *args,
                                                        **kwargs,)

        if self.instance_id:
            metadata = Metadata.objects.get(id=self.instance_id)
            self.fields['keywords'].initial = metadata.keywords.all()
            self.fields['categories'].initial = metadata.categories.all()


class DatasetTemporalExtentForm(MrMapWizardForm):
    maintenance_and_update_frequency = forms.ChoiceField(label=_('Maintenance and update frequency'), choices=Dataset.UPDATE_FREQUENCY_CHOICES)

    def __init__(self, *args, **kwargs):
        super(DatasetTemporalExtentForm, self).__init__(*args, **kwargs)

        if self.instance_id:
            metadata = Metadata.objects.get(id=self.instance_id)
            dataset = Dataset.objects.get(id=metadata.dataset.id)
            self.fields['maintenance_and_update_frequency'].initial = dataset.update_frequency_code


class DatasetLicenseConstraintsForm(MrMapWizardForm):
    terms_of_use = forms.ChoiceField(label=_('Terms of use'),
                                     required=False,
                                     choices=TermsOfUse.objects.all())
    access_constraints = forms.CharField(label=_('Access constraints'),
                                         required=False)

    def __init__(self, *args, **kwargs):
        super(DatasetLicenseConstraintsForm, self).__init__(*args, **kwargs)

        if self.instance_id:
            metadata = Metadata.objects.get(id=self.instance_id)
            self.fields['terms_of_use'].initial = metadata.terms_of_use
            self.fields['access_constraints'].initial = metadata.access_constraints
