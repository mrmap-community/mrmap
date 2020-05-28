"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 09.07.19

"""
from dal import autocomplete
from django.core.exceptions import ObjectDoesNotExist
from django.forms import ModelMultipleChoiceField, ModelChoiceField
from django.utils.translation import gettext_lazy as _

from MapSkinner.forms import MrMapModelForm
from MapSkinner.iso19115.md_metadata import create_gmd_md_metadata
from service.helper.enums import MetadataEnum
from service.models import Metadata, MetadataRelation, MetadataOrigin, MetadataType, Document


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


class MetadataModelMutlipleChoiceField(ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        """
            we need to override this function to show the id of the metadata object,
            so the user can differentiate the results where title is equal.
        """
        return "{} #{}".format(obj.title, obj.id)


class DatasetMetadataEditorForm(MrMapModelForm):
    additional_related_objects = MetadataModelMutlipleChoiceField(
                        queryset=None,
                        widget=autocomplete.ModelSelect2Multiple(
                               url='editor:metadata-autocomplete',
                               attrs={
                                        "data-containercss": {
                                            "height": "3em",
                                            "width": "3em",
                                        },
                               },
                        ),
                        required=False,)

    def __init__(self, *args, **kwargs):
        self.requesting_user = '' if 'requesting_user' not in kwargs else kwargs.pop('requesting_user')
        #self.instance_id = -1 if 'instance_id' not in kwargs else kwargs.pop('instance_id')
        # first call parent's constructor
        super(DatasetMetadataEditorForm, self).__init__(*args, **kwargs)

        # setup querysets
        self.fields['additional_related_objects'].queryset = self.requesting_user.get_metadatas_as_qs(type=MetadataEnum.DATASET, inverse_match=True)

        if 'instance' in kwargs:
            instance = kwargs['instance']
            self.fields['additional_related_objects'].queryset = self.fields['additional_related_objects'].queryset.exclude(id=instance.id)
            metadata_relations = MetadataRelation.objects.filter(metadata_to=instance)
            additional_related_objects = []
            for metadata_relation in metadata_relations:
                if metadata_relation.origin.name != 'capabilities':
                    additional_related_objects.append(metadata_relation.metadata_from)
            self.fields['additional_related_objects'].initial = additional_related_objects
        else:
            self.fields['additional_related_objects'].label = _('Related objects')
            self.fields['additional_related_objects'].required = True
            self.fields['created_by'] = ModelChoiceField(queryset=self.requesting_user.get_groups(), empty_label=None)

        self.fields['keywords'].required = False
        self.fields['languages'].required = False

        self.has_autocomplete = True

    class Meta:
        model = Metadata
        fields = [
            "title",
            "abstract",
            "keywords",
            "languages",
        ]
        help_texts = {
            "title": _("Edit the title."),
            "abstract": _("Edit the description. Keep it short and simple."),
            "keywords": _(""),  # Since keywords are handled differently, this can be empty
            "languages": _("Languages of the dataset")
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
            'languages': autocomplete.ModelSelect2Multiple(
                url='editor:language-autocomplete',
                attrs={
                    "data-containerCss": {
                        "height": "3em",
                        "width": "3em",
                    }
                },
            ),
        }

    def save(self, commit=True):
        # ToDo: is it possible to create save function without commit param?
        m = super(DatasetMetadataEditorForm, self).save(commit=False)
        is_new = False

        if self.instance.id is None:
            is_new = True
            m.created_by = self.cleaned_data['created_by']
            m.metadata_type = MetadataType.objects.get_or_create(type=MetadataEnum.DATASET.value)[0]

        # ToDo: we need to save it here anyway, cause we creating RelatedMetadata objects below
        if commit:
            # ToDo: if an error bellow occurs, we need to rollback()
            m.save()
            self.save_m2m()

        # 1: create new MetadataRelations for the instance, if the relation does not exist
        additional_related_objects = self.cleaned_data['additional_related_objects']
        for related_object in additional_related_objects:
            related_object = Metadata.objects.get(id=related_object.id)
            if is_new and related_object.service.is_active and m.is_active is False:
                m.is_active = True
            try:
                MetadataRelation.objects.get(metadata_to=self.instance, metadata_from=related_object)
                # no error; do nothing
            except ObjectDoesNotExist:
                # if object does not exist, we need to create it new
                origin = MetadataOrigin.objects.get_or_create(name='MrMap')[0]
                new_metadata_relation = MetadataRelation()
                new_metadata_relation.metadata_from = related_object
                new_metadata_relation.metadata_to = self.instance
                new_metadata_relation.origin = origin
                new_metadata_relation.relation_type = 'describedBy'
                # ToDo: if an error occurs we need to rollback
                new_metadata_relation.save()

        # 2: remove all metadata relations which we don't need anymore
        remove_candidates = MetadataRelation.objects.filter(metadata_to=self.instance)\
                                                    .exclude(metadata_from__id__in=additional_related_objects)\
                                                    .exclude(origin__name='capabilities')
        for remove_candidate in remove_candidates:
            # ToDo: if an error occurs we need to rollback
            remove_candidate.delete()

        # 3: generate Document object
        if is_new:
            orga = self.requesting_user.organization

            dataset_metadata_document = create_gmd_md_metadata(m, orga)

            doc = Document()
            doc.related_metadata = m
            doc.original_dataset_metadata_document = dataset_metadata_document
            doc.current_dataset_metadata_document = dataset_metadata_document
            doc.save()

        m.save()
        return m
