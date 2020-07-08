"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 09.07.19

"""
from dal import autocomplete
from django.db.models import Q
from django.forms import ModelMultipleChoiceField
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django import forms

from MrMap.cacher import PageCacher
from MrMap.forms import MrMapModelForm, MrMapWizardForm, MrMapConfirmForm
from MrMap.messages import METADATA_EDITING_SUCCESS, SERVICE_MD_EDITED, METADATA_IS_ORIGINAL, \
    METADATA_RESTORING_SUCCESS, SERVICE_MD_RESTORED
from MrMap.widgets import BootstrapDatePickerInput, LeafletGeometryInput
from api.settings import API_CACHE_KEY_PREFIX
from editor.helper import editor_helper
from service.helper.enums import MetadataEnum, OGCServiceEnum
from service.models import Metadata, MetadataRelation, Keyword, Category, Dataset, ReferenceSystem, TermsOfUse
from service.settings import ISO_19115_LANG_CHOICES
from structure.models import Organization
from users.helper import user_helper
from django.contrib import messages


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

    def process_edit_metadata(self):
        custom_md = self.save(commit=False)
        if not self.instance.is_root():
            # this is for the case that we are working on a non root element which is not allowed to change the
            # inheritance setting for the whole service -> we act like it didn't change
            custom_md.use_proxy_uri = self.instance.use_proxy_uri

            # Furthermore we remove a possibly existing current_capability_document for this element, since the metadata
            # might have changed!
            self.instance.clear_cached_documents()

        editor_helper.resolve_iso_metadata_links(self.request, self.instance, self)
        editor_helper.overwrite_metadata(self.instance, custom_md, self)

        # Clear page cache for API, so the changes will be visible on the next cache
        p_cacher = PageCacher()
        p_cacher.remove_pages(API_CACHE_KEY_PREFIX)

        messages.add_message(self.request, messages.SUCCESS, METADATA_EDITING_SUCCESS)

        if self.instance.is_root():
            parent_service = self.instance.service
        else:
            if self.instance.is_service_type(OGCServiceEnum.WMS):
                parent_service = self.instance.service.parent_service
            elif self.instance.is_service_type(OGCServiceEnum.WFS):
                parent_service = self.instance.featuretype.parent_service

        user_helper.create_group_activity(self.instance.created_by, self.requesting_user, SERVICE_MD_EDITED,
                                          "{}: {}".format(parent_service.metadata.title, self.instance.title))


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


class DatasetLicenseConstraintsForm(MrMapWizardForm):
    terms_of_use = forms.ChoiceField(label=_('Terms of use'),
                                     required=False,
                                     choices=TermsOfUse.objects.all())
    access_constraints = forms.CharField(
        label=_('Access constraints'),
        required=False,
        widget=forms.Textarea()
    )

    def __init__(self, *args, **kwargs):
        super(DatasetLicenseConstraintsForm, self).__init__(*args, **kwargs)

        if self.instance_id:
            metadata = Metadata.objects.get(id=self.instance_id)
            self.fields['terms_of_use'].initial = metadata.terms_of_use
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


class RemoveDatasetForm(MrMapConfirmForm):
    def __init__(self, instance, *args, **kwargs):
        self.instance = instance
        super(RemoveDatasetForm, self).__init__(*args, **kwargs)

    def process_remove_dataset(self):
        self.instance.delete(force=True)
        messages.success(self.request, message=_("Dataset successfully deleted."))


class RestoreMetadataForm(MrMapConfirmForm):
    def __init__(self, instance, *args, **kwargs):
        self.instance = instance
        super(RestoreMetadataForm, self).__init__(*args, **kwargs)

    def process_restore_metadata(self):
        ext_auth = self.instance.get_external_authentication_object()
        service_type = self.instance.get_service_type()
        if service_type == 'wms':
            children_md = Metadata.objects.filter(service__parent_service__metadata=self.instance, is_custom=True)
        elif service_type == 'wfs':
            children_md = Metadata.objects.filter(featuretype__parent_service__metadata=self.instance, is_custom=True)

        if not self.instance.is_custom and len(children_md) == 0:
            messages.add_message(self.request, messages.INFO, METADATA_IS_ORIGINAL)
            return HttpResponseRedirect(reverse(self.request.GET.get('current-view', 'home')), status=303)

        if self.instance.is_custom:
            self.instance.restore(self.instance.identifier, external_auth=ext_auth)
            self.instance.save()

        for md in children_md:
            md.restore(md.identifier)
            md.save()
        messages.add_message(self.request, messages.SUCCESS, METADATA_RESTORING_SUCCESS)
        if not self.instance.is_root():
            if service_type == 'wms':
                parent_metadata = self.instance.service.parent_service.metadata
            elif service_type == 'wfs':
                parent_metadata = self.instance.featuretype.parent_service.metadata
            else:
                # This case is not important now
                pass
        else:
            parent_metadata = self.instance
        user_helper.create_group_activity(self.instance.created_by, self.requesting_user, SERVICE_MD_RESTORED,
                                          "{}: {}".format(parent_metadata.title, self.instance.title))


class RestoreDatasetMetadata(MrMapConfirmForm):
    def __init__(self, instance, *args, **kwargs):
        self.instance = instance
        super(RestoreDatasetMetadata, self).__init__(*args, **kwargs)

    def process_restore_dataset_metadata(self):
        ext_auth = self.instance.get_external_authentication_object()

        if not self.instance.is_custom:
            messages.add_message(self.request, messages.INFO, METADATA_IS_ORIGINAL)
            return HttpResponseRedirect(reverse(self.request.GET.get('current-view', 'home')), status=303)

        if self.instance.is_custom:
            self.instance.restore(self.instance.identifier, external_auth=ext_auth)
            self.instance.save()

        messages.add_message(self.request, messages.SUCCESS, METADATA_RESTORING_SUCCESS)
        user_helper.create_group_activity(self.instance.created_by, self.requesting_user, SERVICE_MD_RESTORED,
                                          "{}".format(self.instance.title, ))