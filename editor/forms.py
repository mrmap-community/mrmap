"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 09.07.19

"""
import json

from dal import autocomplete
from django.db.models import Q
from django.forms import ModelMultipleChoiceField
from django.http import HttpResponseRedirect
from django.urls import reverse, NoReverseMatch
from django.utils.translation import gettext_lazy as _
from django import forms
from MrMap.cacher import PageCacher
from MrMap.forms import MrMapConfirmForm, MrMapForm
from MrMap.messages import METADATA_EDITING_SUCCESS, SERVICE_MD_EDITED, METADATA_IS_ORIGINAL, \
    METADATA_RESTORING_SUCCESS, SERVICE_MD_RESTORED, SECURITY_PROXY_DEACTIVATING_NOT_ALLOWED
from api.settings import API_CACHE_KEY_PREFIX
from editor.helper import editor_helper
from editor.tasks import async_process_securing_access
from service.helper.enums import OGCServiceEnum, OGCOperationEnum
from MrMap.forms import MrMapModelForm, MrMapWizardForm
from MrMap.widgets import BootstrapDatePickerInput, LeafletGeometryInput
from service.helper.enums import MetadataEnum, ResourceOriginEnum
from service.models import Metadata, MetadataRelation, Keyword, Category, Dataset, ReferenceSystem, Licence, \
    SecuredOperation
from service.settings import ISO_19115_LANG_CHOICES
from service.tasks import async_secure_service_task
from structure.models import Organization, MrMapGroup
from users.helper import user_helper
from django.contrib import messages


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
        label=_("Create with group"),
        widget=forms.Select(attrs={'class': 'auto_submit_item'}),
        queryset=MrMapGroup.objects.none(),
        to_field_name='id',
        initial=1
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
            metadata_relations = MetadataRelation.objects.filter(
                metadata_to=self.instance_id
            ).exclude(
                origin=ResourceOriginEnum.CAPABILITIES.value
            )
            self.fields['additional_related_objects'].initial = metadata_relations


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
        queryset=Organization.objects.none(),
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
        if service_type == OGCServiceEnum.WMS.value:
            children_md = Metadata.objects.filter(service__parent_service__metadata=self.instance, is_custom=True)
        elif service_type == OGCServiceEnum.WFS.value:
            children_md = Metadata.objects.filter(featuretype__parent_service__metadata=self.instance, is_custom=True)

        if not self.instance.is_custom and len(children_md) == 0:
            messages.add_message(self.request, messages.INFO, METADATA_IS_ORIGINAL)
            try:
                redirect = HttpResponseRedirect(
                    reverse(
                        self.request.GET.get('current-view', 'home'),
                        args=(
                            self.request.GET.get('current-view-arg', ""),
                        ),
                    ),
                    status=303
                )
            except NoReverseMatch:
                redirect = HttpResponseRedirect(reverse(self.request.GET.get('current-view', 'home')), status=303)
            return redirect

        if self.instance.is_custom:
            self.instance.restore(self.instance.identifier, external_auth=ext_auth)
            self.instance.save()

        for md in children_md:
            md.restore(md.identifier)
            md.save()
        messages.add_message(self.request, messages.SUCCESS, METADATA_RESTORING_SUCCESS)
        if not self.instance.is_root():
            if service_type == OGCServiceEnum.WMS.value:
                parent_metadata = self.instance.service.parent_service.metadata
            elif service_type == OGCServiceEnum.WFS.value:
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


class RestrictAccessForm(MrMapForm):
    use_proxy = forms.BooleanField(
        required=False,
        label=_("Use proxy"),
        help_text=_(
            "Activate to reroute all traffic for this service on MrMap"
        )
    )
    log_proxy = forms.BooleanField(
        required=False,
        label=_("Log proxy activity"),
        help_text=_(
            "Activate to log every traffic activity for this service"
        )
    )
    restrict_access = forms.BooleanField(
        required=False,
        label=_("Restrict access"),
        help_text=_(
            "Activate to restrict access on this service"
        )
    )

    def __init__(self, metadata: Metadata, *args, **kwargs):
        super(RestrictAccessForm, self).__init__(*args, **kwargs)
        self.metadata = metadata
        self.fields["use_proxy"].initial = metadata.use_proxy_uri
        self.fields["log_proxy"].initial = metadata.log_proxy_access
        self.fields["restrict_access"].initial = metadata.is_secured

        is_root = metadata.is_root()
        self.fields["use_proxy"].disabled = not is_root
        self.fields["log_proxy"].disabled = not is_root
        self.fields["restrict_access"].disabled = not is_root

    def clean(self):
        cleaned_data = super(RestrictAccessForm, self).clean()
        use_proxy = cleaned_data.get("use_proxy")
        log_proxy = cleaned_data.get("log_proxy")
        restrict_access = cleaned_data.get("restrict_access")

        # log_proxy and restrict_access can only be activated in combination with use_proxy!
        if log_proxy and not use_proxy or restrict_access and not use_proxy:
            self.add_error("use_proxy", forms.ValidationError(_('Log proxy or restrict access without using proxy is\'nt possible!')))

        # raise Exception if user tries to deactivate an external authenticated service -> not allowed!
        if self.metadata.has_external_authentication and not use_proxy:
            raise AssertionError(SECURITY_PROXY_DEACTIVATING_NOT_ALLOWED)

        return cleaned_data

    def process_securing_access(self, metadata: Metadata):
        """ Call the metadata functions for proxying, logging and securing (access restricting)

        Args:
            metadata (Metadata):
        Returns:

        """
        use_proxy = self.cleaned_data.get("use_proxy", False)
        log_proxy = self.cleaned_data.get("log_proxy", False)
        restrict_access = self.cleaned_data.get("restrict_access", False)

        async_process_securing_access.delay(
            metadata.id,
            use_proxy,
            log_proxy,
            restrict_access
        )


class RestrictAccessSpatially(MrMapForm):
    HELP_TXT_TEMPLATE = _("Activate to allow <strong>{}</strong> in the area defined in the map viewer below.\nIf you want to allow {} without spatial restriction (everywhere), just remove any restriction below.")
    get_map = forms.BooleanField(
        required=False,
        label=OGCOperationEnum.GET_MAP.value,
        help_text=HELP_TXT_TEMPLATE.format(OGCOperationEnum.GET_MAP.value, OGCOperationEnum.GET_MAP.value)
    )
    get_feature_info = forms.BooleanField(
        required=False,
        label=OGCOperationEnum.GET_FEATURE_INFO.value,
        help_text=HELP_TXT_TEMPLATE.format(OGCOperationEnum.GET_MAP.value, OGCOperationEnum.GET_MAP.value)
    )
    get_feature = forms.BooleanField(
        required=False,
        label=OGCOperationEnum.GET_FEATURE.value,
        help_text=HELP_TXT_TEMPLATE.format(OGCOperationEnum.GET_MAP.value, OGCOperationEnum.GET_MAP.value)
    )
    spatial_restricted_area = forms.CharField(
        label=_('Allowed area'),
        required=False,
        widget=LeafletGeometryInput(),
        help_text=_('Unfold the leaflet client by clicking on the polygon icon.'),
    )

    def __init__(self, metadata_id: int, group_id: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.metadata_id = metadata_id
        self.group_id = group_id

        self.metadata = Metadata.objects.get(
            id=metadata_id
        )
        md_is_root = self.metadata.is_root()

        # Read initial data for fields
        secured_operations = SecuredOperation.objects.filter(
            secured_metadata__id=metadata_id,
            allowed_group__id=group_id
        )
        secured_operation_get_map = secured_operations.filter(
            operation=OGCOperationEnum.GET_MAP.value
        ).exists()
        secured_operation_get_feature_info = secured_operations.filter(
            operation=OGCOperationEnum.GET_FEATURE_INFO.value
        ).exists()
        secured_operation_get_feature = secured_operations.filter(
            operation=OGCOperationEnum.GET_FEATURE.value
        ).exists()

        # Since we persist geometries in GeometryCollections, containing Polygon obejcts, we need to use a little hack
        # to force Leaflet to read this artifical FeatureCollection, which is filled by the persisted Polygon objects
        feature_geojson = {
            "type": "FeatureCollection",
            "features": [],
        }

        # If the metadata is not root, we are not allowed to create own geometries but we need to inherit the ones from
        # the parent. Therefore we read it from the root in this case
        if not md_is_root:
            secured_operations_bounding_geometry = self.metadata.get_root_metadata().secured_operations.all().first()
        else:
            secured_operations_bounding_geometry = secured_operations.first()
        if secured_operations_bounding_geometry is not None:
            secured_operations_bounding_geometry = secured_operations_bounding_geometry.bounding_geometry
            if secured_operations_bounding_geometry is not None:
                for geom in secured_operations_bounding_geometry:
                    feature = {
                        "type": "Feature",
                        "properties": "{}",
                        "geometry": json.loads(geom.geojson),
                    }
                    feature_geojson["features"].append(feature)
                feature_geojson = json.dumps(feature_geojson)
            else:
                # If no bounding geometry exists, we need to set feature_geojson to None,
                # so it will be interpreted as empty geometry input
                feature_geojson = None
        else:
            feature_geojson = None

        # restricting via geometry is only allowed for root metadata, not for every single subelement
        if not md_is_root:
            self.fields["spatial_restricted_area"].widget = forms.HiddenInput()

        # Set initial fields
        if self.metadata.service.is_wms:
            self.fields["get_map"].initial = secured_operation_get_map
            self.fields["get_feature_info"].initial = secured_operation_get_feature_info
            del self.fields["get_feature"]
        elif self.metadata.service.is_wfs:
            self.fields["get_feature"].initial = secured_operation_get_feature
            del self.fields["get_map"]
            del self.fields["get_feature_info"]
        else:
            raise AssertionError("Wrong service type for spatial access form!")
        self.fields["spatial_restricted_area"].initial = feature_geojson

    def process_restict_access_spatially(self):
        """ Create SecuredOperations for metadata, according to form data

        Returns:

        """
        # Check if the metadata is already secured. If not, secure it!
        if not self.metadata.is_secured:
            self.metadata.set_secured(True)

        bounding_geometry = self.cleaned_data.get("spatial_restricted_area", None)
        try:
            del self.cleaned_data["spatial_restricted_area"]
        except KeyError:
            # happens on a non-root service
            pass

        ogc_operation_map = {
            "get_map": OGCOperationEnum.GET_MAP.value,
            "get_feature_info": OGCOperationEnum.GET_FEATURE_INFO.value,
            "get_feature": OGCOperationEnum.GET_FEATURE.value,
        }
        operation_map = {
            "get_map": None,
            "get_feature_info": None,
            "get_feature": None,
        }
        for k, v in self.cleaned_data.items():
            try:
                operation_map[k] = v
            except KeyError:
                pass
        # Reduce operation_map on valid data
        operations = [v for k, v in ogc_operation_map.items() if k in operation_map and operation_map[k] is True]

        # Call persisting of new settings in background process
        async_secure_service_task.delay(
            self.metadata_id,
            self.group_id,
            operations,
            bounding_geometry
        )
