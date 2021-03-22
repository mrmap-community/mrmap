"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 09.07.19

"""
from dal import autocomplete
from django.db.models import Q
from django.forms import ModelMultipleChoiceField, ModelForm
from django.forms import BaseModelFormSet
from django.forms.formsets import TOTAL_FORM_COUNT, INITIAL_FORM_COUNT
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django import forms
from leaflet.forms.widgets import LeafletWidget

from MrMap.cacher import PageCacher
from MrMap.forms import MrMapConfirmForm, MrMapForm
from MrMap.messages import METADATA_IS_ORIGINAL, \
    METADATA_RESTORING_SUCCESS, SERVICE_MD_RESTORED, SECURITY_PROXY_DEACTIVATING_NOT_ALLOWED
from api.settings import API_CACHE_KEY_PREFIX
from editor.helper import editor_helper
from editor.tasks import async_process_securing_access
from MrMap.forms import MrMapWizardForm
from MrMap.widgets import BootstrapDatePickerInput, LeafletGeometryInput
from service.helper.enums import MetadataEnum, ResourceOriginEnum
from service.models import Metadata, Keyword, Category, Dataset, ReferenceSystem, Licence, AllowedOperation
from service.settings import ISO_19115_LANG_CHOICES
from structure.models import Organization
from django.contrib import messages


class MetadataEditorForm(ModelForm):
    def __init__(self, *args, **kwargs):
        # first call parent's constructor
        super(MetadataEditorForm, self).__init__(*args, **kwargs)

        # there's a `fields` property now
        self.fields['licence'].required = False
        self.fields['categories'].required = False
        self.fields['keywords'].required = False
        self.has_autocomplete_fields = True

    class Meta:
        model = Metadata
        fields = [
            "title",
            "abstract",
            "language_code",
            "access_constraints",
            "licence",
            "keywords",
            "categories",
        ]
        labels = {
            "title": _("Title"),
            "abstract": _("Abstract"),
            "language_code": _("Language Code"),
            "access_constraints": _("Access Constraints"),
            "licence": _("Licence"),
            "keywords": _("Keywords"),
            "categories": _("Categories"),
        }
        help_texts = {
            "title": _("Edit the title."),
            "abstract": _("Edit the description. Keep it short and simple."),
            "language_code": _("Edit the language which the metadata is represented."),
            "access_constraints": _("Edit the access constraints."),
            "licence": Licence.get_descriptions_help_text(),
            "keywords": _(""),  # Since keywords are handled differently, this can be empty
            "categories": _("Select categories for this resource."),
        }
        widgets = {
            "categories": autocomplete.ModelSelect2Multiple(
                url='editor:category-autocomplete',
                attrs={
                    "select2-container-css-style": {
                        "height": "auto",
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

    def save(self, commit=True):
        custom_md = super().save(commit=False)
        if not self.instance.is_root():
            # this is for the case that we are working on a non root element which is not allowed to change the
            # inheritance setting for the whole service -> we act like it didn't change
            custom_md.use_proxy_uri = self.instance.use_proxy_uri

            # Furthermore we remove a possibly existing current_capability_document for this element, since the metadata
            # might have changed!
            self.instance.clear_cached_documents()

        editor_helper.resolve_iso_metadata_links(self.instance, self)
        editor_helper.overwrite_metadata(self.instance, custom_md, self)

        # Clear page cache for API, so the changes will be visible on the next cache
        p_cacher = PageCacher()
        p_cacher.remove_pages(API_CACHE_KEY_PREFIX)

        # todo: add last_changed_by_user field to Metadata model
        """
        if self.instance.is_root():
            parent_service = self.instance.service
        else:
            if self.instance.is_service_type(OGCServiceEnum.WMS):
                parent_service = self.instance.service.parent_service
            elif self.instance.is_service_type(OGCServiceEnum.WFS):
                parent_service = self.instance.featuretype.parent_service

        
        #user_helper.create_group_activity(self.instance.created_by, self.requesting_user, SERVICE_MD_EDITED,
        #                                 "{}: {}".format(parent_service.metadata.title, self.instance.title))
        """
        custom_md.save()


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
    date_stamp = forms.DateTimeField(label=_('Metadata creation date'),
                                 widget=BootstrapDatePickerInput())
    reference_system = ReferenceSystemModelMultipleChoiceField(
        queryset=ReferenceSystem.objects.none(),
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
        queryset=Metadata.objects.none(),
        widget=autocomplete.ModelSelect2Multiple(
            url='editor:metadata-autocomplete',

        ),
        required=False, )

    created_by = forms.ModelChoiceField(
        label=_("Create with organization"),
        widget=forms.Select(attrs={'class': 'auto_submit_item'}),
        queryset=Organization.objects.none(),
        to_field_name='id',
        initial=1
    )

    def __init__(self, *args, **kwargs):
        super(DatasetIdentificationForm, self).__init__(has_autocomplete_fields=True,
                                                        *args,
                                                        **kwargs)

        self.fields['additional_related_objects'].queryset = self.request.user.get_metadatas_as_qs(
            type=MetadataEnum.DATASET, inverse_match=True)
        self.fields['reference_system'].queryset = ReferenceSystem.objects.all()

        user = kwargs.pop("request").user
        user_groups = user.groups.filter(mrmapgroup__is_public_group=False)
        self.fields["created_by"].queryset = user_groups
        self.fields["created_by"].initial = user_groups.first()

        if self.instance_id:
            metadata = Metadata.objects.get(pk=self.instance_id)
            dataset = Dataset.objects.get(pk=metadata.dataset.id)
            self.fields['title'].initial = metadata.title
            self.fields['abstract'].initial = metadata.abstract
            self.fields['reference_system'].initial = metadata.reference_system.all()
            self.fields['date_stamp'].initial = dataset.date_stamp
            self.fields['language_code'].initial = dataset.language_code
            self.fields['character_set_code'].initial = dataset.character_set_code

            self.fields['additional_related_objects'].queryset = self.fields['additional_related_objects'].queryset.exclude(id=self.instance_id)

            exclusions = {'to_metadatas__origin': ResourceOriginEnum.CAPABILITIES.value}
            related_metadatas = metadata.get_related_metadatas(exclusions=exclusions)
            self.fields['additional_related_objects'].initial = related_metadatas


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
        queryset=Licence.objects.all(),
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
                                                                           geojson=metadata.allowed_area.geojson
                                                                           if data_for_bounding_geometry is None
                                                                           else data_for_bounding_geometry,
                                                                           request=self.request,)
            self.fields['bounding_geometry'].initial = metadata.allowed_area.geojson


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
        queryset=Organization.objects.none(),
        required=False,
        help_text=_('Select an other Organization to overwrite the original. You can select your organization and the ones you are allowed to publish for.')
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.get("request").user
        user_groups = user.groups.all()
        if 'instance_id' in kwargs and kwargs['instance_id'] is not None:
            metadata = Metadata.objects.get(id=kwargs['instance_id'])
            init_organization = Organization.objects.filter(id=metadata.contact.id)
            organizations = Organization.objects.filter(
                Q(is_auto_generated=False) &
                Q(publishers=user_groups) |
                Q(id=user.organization.id)
            ) | init_organization
        else:
            organizations = Organization.objects.filter(
                Q(is_auto_generated=False) &
                Q(publishers=user_groups) |
                Q(id=user.organization.id)
            )

        super(DatasetResponsiblePartyForm, self).__init__(*args, **kwargs)

        self.fields['organization'].queryset = organizations


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


class GeneralAccessSettingsForm(forms.ModelForm):

    class Meta:
        model = Metadata
        fields = ('use_proxy_uri', 'log_proxy_access', 'is_secured')
        labels = {
            'use_proxy_uri': _("Use proxy"),
            'log_proxy_access': _("Log proxy activity"),
            'is_secured': _("Restrict access"),
        }
        help_texts = {
            'use_proxy_uri': _('Activate to reroute all traffic for this service on MrMap.'),
            'log_proxy_access': _('Activate to log every traffic activity for this service.'),
            'is_secured': _('Activate to restrict access on this service')
        }
        widgets = {
            'is_secured': forms.CheckboxInput(attrs={'class': 'auto_submit_item', }),
        }

    def __init__(self, *args, **kwargs):
        super(GeneralAccessSettingsForm, self).__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        use_proxy = cleaned_data.get("use_proxy_uri")
        log_proxy = cleaned_data.get("log_proxy_access")
        restrict_access = cleaned_data.get("is_secured")

        # log_proxy and restrict_access can only be activated in combination with use_proxy!
        if log_proxy and not use_proxy or restrict_access and not use_proxy:
            self.add_error("use_proxy_uri", forms.ValidationError(_('Log proxy or restrict access without using proxy is\'nt possible!')))

        # raise Exception if user tries to deactivate an external authenticated service -> not allowed!
        if self.instance.has_external_authentication and not use_proxy:
            raise AssertionError(SECURITY_PROXY_DEACTIVATING_NOT_ALLOWED)

        return cleaned_data

    def save(self, commit=True):

        # todo: just save the fields and implement a signal which detects if one of the three fields become changed.
        #  the signal can then fire the async task.
        # todo: maybe we could merge the async_proccess from step 1 and two of the wizard
        use_proxy = self.cleaned_data.get("use_proxy_uri", False)
        log_proxy = self.cleaned_data.get("log_proxy_access", False)
        restrict_access = self.cleaned_data.get("is_secured", False)

        async_process_securing_access.delay(
            self.instance.id,
            use_proxy,
            log_proxy,
            restrict_access
        )


class AllowedOperationForm(forms.ModelForm):

    class Meta:
        model = AllowedOperation
        fields = ('operations', 'allowed_groups', 'allowed_area', 'root_metadata')

        widgets = {
            'operations': autocomplete.ModelSelect2Multiple(
                url='editor:operations-autocomplete',
                attrs={
                    "data-containerCss": {
                        "height": "3em",
                        "width": "3em",
                    }
                },
            ),
            'allowed_groups': autocomplete.ModelSelect2Multiple(
                url='editor:groups',
                attrs={
                    "data-containerCss": {
                        "height": "3em",
                        "width": "3em",
                    }
                },
            ),
            'allowed_area': LeafletWidget(attrs={
                                            'map_height': '500px',
                                            'map_width': '100%',
                                            #'display_raw': 'true',
                                            'map_srid': 4326,
                                        }),
            'root_metadata': forms.HiddenInput(),
        }
