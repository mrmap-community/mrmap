"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 09.07.19

"""
from dal import autocomplete
from django.db.models import Q
from django.forms import ModelMultipleChoiceField
from django.utils.translation import gettext_lazy as _
from django import forms
from MrMap.forms import MrMapModelForm, MrMapWizardForm, MrMapWizardModelForm
from MrMap.widgets import BootstrapDateTimePickerInput, BootstrapDatePickerInput, LeafletGeometryInput
from service.helper.enums import MetadataEnum, ResourceOriginEnum
from service.models import Metadata, MetadataRelation, Keyword, Category, Dataset, ReferenceSystem, Licence
from service.settings import ISO_19115_LANG_CHOICES, DEFAULT_SERVICE_BOUNDING_BOX
from structure.models import Organization
from users.helper import user_helper


class MetadataEditorForm(MrMapModelForm):
    def __init__(self, *args, **kwargs):
        # first call parent's constructor
        super(MetadataEditorForm, self).__init__(*args, **kwargs)

        # there's a `fields` property now
        self.fields['licence'].required = False
        self.fields['categories'].required = False
        self.fields['keywords'].required = False
        self.has_autocomplete = True

    class Meta:
        model = Metadata
        fields = [
            "title",
            "abstract",
            "access_constraints",
            "licence",
            "keywords",
            "categories",
        ]
        help_texts = {
            "title": _("Edit the title."),
            "abstract": _("Edit the description. Keep it short and simple."),
            "access_constraints": _("Edit the access constraints."),
            "licence": Licence.get_descriptions_help_text(),
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

    created_by = forms.ModelChoiceField(
        label=_("Create with group"),
        widget=forms.Select(attrs={'class': 'auto_submit_item'}),
        queryset=None, to_field_name='id', initial=1
    )

    def __init__(self, *args, **kwargs):
        super(DatasetIdentificationForm, self).__init__(has_autocomplete_fields=True,
                                                        *args,
                                                        **kwargs)

        self.fields['additional_related_objects'].queryset = user_helper.get_user(self.request).get_metadatas_as_qs(
            type=MetadataEnum.DATASET, inverse_match=True)
        self.fields['reference_system'].queryset = ReferenceSystem.objects.all()

        user = user_helper.get_user(request=kwargs.pop("request"))
        user_groups = user.get_groups({"is_public_group": False})
        self.fields["created_by"].queryset = user_groups
        self.fields["created_by"].initial = user_groups.first()

        if self.instance_id:
            metadata = Metadata.objects.get(id=self.instance_id)
            dataset = Dataset.objects.get(id=metadata.dataset.id)
            self.fields['title'].initial = metadata.title
            self.fields['abstract'].initial = metadata.abstract
            self.fields['reference_system'].initial = metadata.reference_system.all()
            self.fields['date_stamp'].initial = dataset.date_stamp
            self.fields['language_code'].initial = dataset.language_code
            self.fields['character_set_code'].initial = dataset.character_set_code

            self.fields['additional_related_objects'].queryset = self.fields['additional_related_objects'].queryset.exclude(id=self.instance_id)
            metadata_relations = MetadataRelation.objects.filter(metadata_to=self.instance_id)
            additional_related_objects = []
            for metadata_relation in metadata_relations:
                if metadata_relation.origin != ResourceOriginEnum.CAPABILITIES.value:
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


class DatasetLicenseConstraintsForm(MrMapWizardForm):
    licence = forms.ModelChoiceField(
        label=_('Terms of use'),
        required=False,
        queryset=Licence.objects.filter(is_active=True),
        help_text=Licence.get_descriptions_help_text()
    )
    access_constraints = forms.CharField(
        label=_('Access constraints'),
        required=False,
        widget=forms.Textarea()
    )

    def __init__(self, *args, **kwargs):
        super(DatasetLicenseConstraintsForm, self).__init__(*args, **kwargs)

        if self.instance_id:
            metadata = Metadata.objects.get(id=self.instance_id)
            self.fields['licence'].initial = metadata.licence
            self.fields['access_constraints'].initial = metadata.access_constraints


class DatasetSpatialExtentForm(MrMapWizardForm):
    bounding_geometry = forms.CharField(label=_('Bounding box'),
                                        required=False,
                                        widget=LeafletGeometryInput(),
                                        help_text=_('Unfold the leaflet client by clicking on the polygon icon.'),)

    def __init__(self, *args, **kwargs):
        super(DatasetSpatialExtentForm, self).__init__(*args, **kwargs)

        data_for_bounding_geometry = None
        for key, value in self.data.items():
            if 'bounding_geometry' in key.lower():
                data_for_bounding_geometry = value

        self.fields['bounding_geometry'].widget = LeafletGeometryInput(geojson=data_for_bounding_geometry,
                                                                       request=self.request,)

        if self.instance_id:
            metadata = Metadata.objects.get(id=self.instance_id)
            bbox = metadata.find_max_bounding_box()

            self.fields['bounding_geometry'].widget = LeafletGeometryInput(bbox=bbox,
                                                                           geojson=metadata.bounding_geometry.geojson
                                                                           if data_for_bounding_geometry is None
                                                                           else data_for_bounding_geometry,
                                                                           request=self.request,)
            self.fields['bounding_geometry'].initial = metadata.bounding_geometry.geojson


class DatasetQualityForm(MrMapWizardForm):
    maintenance_and_update_frequency = forms.ChoiceField(
        label=_('Maintenance and update frequency'),
        choices=Dataset.UPDATE_FREQUENCY_CHOICES
    )
    lineage_statement = forms.CharField(
        label=_('Lineage Statement'),
        required=False,
        widget=forms.Textarea()
    )

    def __init__(self, *args, **kwargs):
        super(DatasetQualityForm, self).__init__(*args, **kwargs)

        if self.instance_id:
            metadata = Metadata.objects.get(id=self.instance_id)
            dataset = Dataset.objects.get(id=metadata.dataset.id)
            self.fields['lineage_statement'].initial = dataset.lineage_statement
            self.fields['maintenance_and_update_frequency'].initial = dataset.update_frequency_code


class DatasetResponsiblePartyForm(MrMapWizardForm):
    organization = forms.ModelChoiceField(
        label=_('Organization'),
        queryset=None,
        required=False,
        help_text=_('Select an other Organization to overwrite the original. You can select your organization and the ones you are allowed to publish for.')
    )

    def __init__(self, *args, **kwargs):
        user = user_helper.get_user(kwargs.get("request"))
        user_groups = user.get_groups()
        if 'instance_id' in kwargs and kwargs['instance_id'] is not None:
            metadata = Metadata.objects.get(id=kwargs['instance_id'])
            init_organization = Organization.objects.filter(id=metadata.contact.id)
            organizations = Organization.objects.filter(
                Q(is_auto_generated=False) &
                Q(can_publish_for__in=user_groups) |
                Q(id=user.organization.id)
            ) | init_organization
        else:
            organizations = Organization.objects.filter(
                Q(is_auto_generated=False) &
                Q(can_publish_for__in=user_groups) |
                Q(id=user.organization.id)
            )

        super(DatasetResponsiblePartyForm, self).__init__(*args, **kwargs)

        self.fields['organization'].queryset = organizations
