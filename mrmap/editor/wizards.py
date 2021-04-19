<<<<<<< HEAD
import json
from json import JSONDecodeError
from django.contrib.gis.geos import GEOSGeometry, GeometryCollection
from django.core.exceptions import ObjectDoesNotExist
from django.forms import modelformset_factory
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.html import format_html
from django_bootstrap_swt.components import Alert
from django_bootstrap_swt.enums import AlertEnum
from guardian.mixins import LoginRequiredMixin, PermissionRequiredMixin

=======
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.exceptions import ObjectDoesNotExist
from django.forms import modelformset_factory
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.html import format_html
>>>>>>> 6547e7f6ad710c8351a3ede267a054c17a44fa14
from MrMap.messages import NO_PERMISSION
from MrMap.wizards import MrMapWizard
from editor.forms import DatasetIdentificationForm, DatasetClassificationForm, \
    DatasetLicenseConstraintsForm, DatasetSpatialExtentForm, DatasetQualityForm, DatasetResponsiblePartyForm, \
    GeneralAccessSettingsForm, AllowedOperationForm
from django.utils.translation import gettext_lazy as _
from service.helper.enums import MetadataEnum, DocumentEnum, ResourceOriginEnum, MetadataRelationEnum
from service.helper.iso.iso_19115_metadata_builder import Iso19115MetadataBuilder
from service.models import Dataset, Metadata, MetadataRelation, Document, AllowedOperation
<<<<<<< HEAD
from service.settings import DEFAULT_SRS
from structure.models import Organization
=======
from structure.models import Organization, MrMapUser
>>>>>>> 6547e7f6ad710c8351a3ede267a054c17a44fa14
from structure.permissionEnums import PermissionEnum
from django.forms import BaseFormSet


ACCESS_EDITOR_STEP_2_NAME = _("restrict")
APPEND_FORM_LOOKUP_KEY = "APPEND_FORM"

ACCESS_EDITOR_WIZARD_FORMS = [(_("general"), GeneralAccessSettingsForm),
                              (ACCESS_EDITOR_STEP_2_NAME, modelformset_factory(AllowedOperation,
                                                                               can_delete=True,
                                                                               form=AllowedOperationForm,
                                                                               extra=2)), ]

DATASET_WIZARD_FORMS = [("identification", DatasetIdentificationForm),
                        ("classification", DatasetClassificationForm),
                        ("responsible party", DatasetResponsiblePartyForm),
                        ("spatial extent", DatasetSpatialExtentForm),
                        ("licenses/constraints", DatasetLicenseConstraintsForm),
                        ("Quality", DatasetQualityForm), ]

DATASET_WIZARD_FORMS_REQUIRED = ['identification', 'classification', 'responsible party']


def show_restrict_spatially_form_condition(wizard):
    # try to get the cleaned data of step 1
    cleaned_data = wizard.get_cleaned_data_for_step('general') or {}
    # check if the field ``is_secured`` was checked.
    return cleaned_data.get('is_secured', True)


class AccessEditorWizard(LoginRequiredMixin, PermissionRequiredMixin, MrMapWizard):
    # template_name = "generic_views/generic_wizard_form.html"
    action_url = ""
    object = None
    condition_dict = {ACCESS_EDITOR_STEP_2_NAME: show_restrict_spatially_form_condition}
    permission_required = PermissionEnum.CAN_SECURE_RESOURCE.value
    raise_exception = True
    permission_denied_message = NO_PERMISSION
    success_url = reverse_lazy('resource:pending-tasks')

    def dispatch(self, request, *args, **kwargs):
        pk = kwargs.get('pk', None)
        self.object = get_object_or_404(klass=Metadata, id=pk)
        allowed_operations = AllowedOperation.objects.filter(secured_metadata=self.object)
        self.instance_dict = {"general": self.object,
                              ACCESS_EDITOR_STEP_2_NAME: allowed_operations, }
        self.initial_dict = {ACCESS_EDITOR_STEP_2_NAME: [{"root_metadata": self.object}]}

        # if we got existing SecuredOperation objects for the requested metadata object, we do not serve extra empty
        # forms in our formset. The user can add some if he want with the add button which will post the APPEND_FORMSET
        # field.
        if allowed_operations:
            extra = 0
        else:
            extra = 1

        self.form_list[ACCESS_EDITOR_STEP_2_NAME] = modelformset_factory(AllowedOperation,
                                                                         can_delete=True,
                                                                         form=AllowedOperationForm,
                                                                         extra=extra)

        self.action_url = reverse('resource:access-editor-wizard', args=[self.object.pk, ])

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form, **kwargs)
        context.update({'action_url': self.action_url,
                        'APPEND_FORM_LOOKUP_KEY': APPEND_FORM_LOOKUP_KEY})
        return context

    def get_form(self, step=None, data=None, files=None):
        form = super().get_form(step=step, data=data, files=files)
        if issubclass(form.__class__, BaseFormSet) and form.can_delete:
            for _form in form.forms:
                _form.accordion_title = _('Allowed operation')
        return form

    def done(self, form_list, **kwargs):
        for form in form_list:
            form.save()
        return super().done(form_list, **kwargs)


class DatasetWizard(LoginRequiredMixin, PermissionRequiredMixin, MrMapWizard):
    metadata = None
    dataset = None
    success_url = reverse_lazy('resource:datasets-index')

    def get_permission_object(self):
        return self.metadata

    def __init__(self, *args, **kwargs):
        super(MrMapWizard, self).__init__(
            required_forms=DATASET_WIZARD_FORMS_REQUIRED,
            *args,
            **kwargs)

    def get_form_kwargs(self, step=None):
        if step == 'spatial extent':
            return {'instance': self.metadata}
        return {'request': self.request}

    def get_form_initial(self, step):
        initial = self.initial_dict.get(step, {})
        if step == "responsible party" and self.instance_id:
            metadata = Metadata.objects.get(id=self.instance_id)
            init_organization = Organization.objects.get(id=metadata.contact.id)
            initial.update({'organization': init_organization.id})
        return initial

    def done(self, form_list, **kwargs):
        """ Iterates over all forms and fills the Metadata/Dataset records accordingly

        Args:
            form_list (FormList): An iterable list of forms
            kwargs:
        Returns:

        """
        self._fill_form_list(form_list, self.metadata, self.dataset, self.request.user)
        return super().done(form_list, **kwargs)

    @staticmethod
    def _fill_form_list(form_list, metadata: Metadata, dataset: Dataset, user):
        """ Iterates over all forms and applies the metadata changes on the objects

        Args:
            form_list: The list of forms
            metadata: The metadata record
            dataset: The dataset record
            user: The performing user
        Returns:

        """
        function_map = {
            "DatasetIdentificationForm": DatasetWizard._fill_metadata_dataset_identification_form,
            "DatasetResponsiblePartyForm": DatasetWizard._fill_metadata_dataset_responsible_party_form,
            "DatasetClassificationForm": DatasetWizard._fill_metadata_dataset_classification_form,
            "DatasetSpatialExtentForm": DatasetWizard._fill_metadata_dataset_spatial_extent_form,
            "DatasetLicenseConstraintsForm": DatasetWizard._fill_metadata_dataset_licence_form,
            "DatasetQualityForm": DatasetWizard._fill_metadata_dataset_quality_form,
        }

        for form in form_list:
            form_class = type(form).__name__
            function_map[form_class](form.cleaned_data, metadata, dataset, user)

        dataset.save()
        metadata.is_custom = True
        metadata.save()

        try:
            doc = Document.objects.get(
                metadata__id=metadata.id,
                document_type=DocumentEnum.METADATA.value,
                is_original=False,
            )
            doc.is_active = metadata.is_active
            DatasetWizard._overwrite_dataset_document(metadata, doc)
        except ObjectDoesNotExist:
            DatasetWizard._create_dataset_document(metadata)

    @staticmethod
    def _fill_metadata_dataset_identification_form(data: dict, metadata: Metadata, dataset: Dataset, user):
        """ Fills form data into Metadata/Dataset records

        Args:
            data (dict): Cleaned form data
            metadata (dict): The metadata record
            dataset (dict): The dataset record
            user: The performing user
        Returns:

        """
        metadata.title = data.get("title", None)
        metadata.abstract = data.get("abstract", None)
        metadata.created = data.get("date_stamp", None)
        metadata.created_by = data.get("created_by", None)

        dataset.language_code = data.get("language_code", None)
        dataset.character_set_code = data.get("character_set_code", None)
        dataset.date_stamp = data.get("date_stamp", None)

        ref_systems = data.get("reference_system", [])
        metadata.reference_system.clear()
        for ref_system in ref_systems:
            metadata.reference_system.add(ref_system)

        additional_related_objects = data.get("additional_related_objects", [])
        MetadataRelation.objects.filter(to_metadata=metadata, origin=ResourceOriginEnum.EDITOR.value).delete()
        for additional_object in additional_related_objects:
            additional_object.add_metadata_relation(to_metadata=metadata,
                                                    relation_type=MetadataRelationEnum.DESCRIBES.value,
                                                    internal=True,
                                                    origin=ResourceOriginEnum.EDITOR.value)

    @staticmethod
    def _fill_metadata_dataset_classification_form(data: dict, metadata: Metadata, dataset: Dataset, user):
        """ Fills form data into Metadata/Dataset records

        Args:
            data (dict): Cleaned form data
            metadata (dict): The metadata record
            dataset (dict): The dataset record
            user: The performing user
        Returns:

        """
        metadata.keywords.clear()
        keywords = data.get("keywords", [])
        for kw in keywords:
            metadata.keywords.add(kw)

        metadata.categories.clear()
        categories = data.get("categories", [])
        for cat in categories:
            metadata.categories.add(cat)

    @staticmethod
    def _fill_metadata_dataset_spatial_extent_form(data: dict, metadata: Metadata, dataset: Dataset, user):
        """ Fills form data into Metadata/Dataset records

        Args:
            data (dict): Cleaned form data
            metadata (dict): The metadata record
            dataset (dict): The dataset record
            user: The performing user
        Returns:

        """
        metadata.bounding_geometry = data.get("bounding_geometry", None)

    @staticmethod
    def _fill_metadata_dataset_licence_form(data: dict, metadata: Metadata, dataset: Dataset, user):
        """ Fills form data into Metadata/Dataset records

        Args:
            data (dict): Cleaned form data
            metadata (dict): The metadata record
            dataset (dict): The dataset record
            user: The performing user
        Returns:

        """
        metadata.licence = data.get("licence", None)
        metadata.access_constraints = data.get("access_constraints", None)

    @staticmethod
    def _fill_metadata_dataset_quality_form(data: dict, metadata: Metadata, dataset: Dataset, user):
        """ Fills form data into Metadata/Dataset records

        Args:
            data (dict): Cleaned form data
            metadata (dict): The metadata record
            dataset (dict): The dataset record
            user: The performing user
        Returns:

        """
        dataset.update_frequency_code = data.get("maintenance_and_update_frequency", None)
        dataset.lineage_statement = data.get("lineage_statement", None)

    @staticmethod
    def _fill_metadata_dataset_responsible_party_form(data: dict, metadata: Metadata, dataset: Dataset,
                                                      user):
        """ Fills form data into Metadata/Dataset records

        Args:
            data (dict): Cleaned form data
            metadata (dict): The metadata record
            dataset (dict): The dataset record
            user: The performing user
        Returns:

        """
        # Check on an existing organization
        org = data.get("organization")
        if org is None:
            # A new org has to be created with minimal contact details
            org = Organization.objects.get_or_create(
                organization_name=data.get("organization_name"),
                person_name=data.get("person_name"),
                phone=data.get("phone"),
                email=data.get("mail"),
                facsimile=data.get("facsimile"),
                created_by=user,
            )[0]
        metadata.contact = org

    @staticmethod
    def _create_dataset_document(metadata: Metadata):
        """ Creates a Document record for the new Dataset entry

        Args:
            metadata (Metadata): The metadata record
        Returns:

        """
        doc_builder = Iso19115MetadataBuilder(metadata.id, MetadataEnum.DATASET)
        dataset_doc_string = doc_builder.generate_service_metadata()
        dataset_doc_string = dataset_doc_string.decode("UTF-8")

        curr_document_obj = Document.objects.get_or_create(
            metadata=metadata,
            is_original=False,
            document_type=DocumentEnum.METADATA.value
        )[0]
        curr_document_obj.is_active = metadata.is_active
        curr_document_obj.content = dataset_doc_string
        curr_document_obj.save()

    @staticmethod
    def _overwrite_dataset_document(metadata: Metadata, doc: Document = None):
        """ Overwrites a Document record for an existing Dataset entry

        Args:
            metadata (Metadata): The metadata record
            doc (Document): The document record
        Returns:

        """
        doc_builder = Iso19115MetadataBuilder(metadata.id, MetadataEnum.DATASET)
        dataset_doc_string = doc_builder.overwrite_dataset_metadata(doc.content)
        doc.content = dataset_doc_string.decode("UTF-8")
        doc.save()


class NewDatasetWizard(DatasetWizard):
    permission_required = PermissionEnum.CAN_ADD_DATASET_METADATA.value
    raise_exception = True
    permission_denied_message = NO_PERMISSION

    def __init__(self, *args, **kwargs):
        super().__init__(
            action_url=reverse('editor:dataset-metadata-wizard-new', ),
            title=_(format_html('<b>Add New Dataset</b>')),
            *args,
            **kwargs)

    def get_form_kwargs(self, step=None):
        return {'request': self.request}

    def done(self, form_list, **kwargs):
        """ Iterates over all forms and fills the Metadata/Dataset records accordingly

        Args:
            form_list (FormList): An iterable list of forms
            kwargs:
        Returns:

        """
        # Create instances
        self.metadata = Metadata()
        self.metadata.metadata_type = MetadataEnum.DATASET.value
        self.metadata.is_active = True

        self.dataset = Dataset()
        self.dataset.is_active = True
        self.dataset.md_identifier_code = self.metadata.identifier
        self.dataset.metadata_standard_name = "ISO 19115 Geographic information - Metadata"
        self.dataset.metadata_standard_version = "ISO 19115:2003(E)"

        # Pre-save objects to be able to add M2M relations
        self.metadata.save()
        self.metadata.identifier = self.metadata.id
        self.dataset.metadata = self.metadata
        self.dataset.save()
        self.metadata.metadata_url = reverse("resource:get-dataset-metadata", args=(self.dataset.id,))

        return super().done(form_list=form_list, **kwargs)


class EditDatasetWizard(DatasetWizard):
    permission_required = PermissionEnum.CAN_EDIT_METADATA.value
    raise_exception = True
    permission_denied_message = NO_PERMISSION

    def __init__(self, *args, **kwargs):
        super().__init__(
            title=_(format_html('<b>Edit Dataset</b>')),
            *args,
            **kwargs)

    def get_form_kwargs(self, step=None):
        if step == 'spatial extent':
            return {'instance': self.metadata}
        kws = super().get_form_kwargs()
        kws.update({'instance_id': self.instance_id})
        return kws

    def dispatch(self, request, *args, **kwargs):
        self.instance_id = request.resolver_match.kwargs.get('pk')
        self.metadata = Metadata.objects.get(id=self.instance_id)
        self.dataset = Dataset.objects.get(metadata=self.metadata)

        self.action_url = reverse('resource:dataset-metadata-wizard-instance', args=(self.instance_id,))
        return super().dispatch(request=request, args=args, kwargs=kwargs)

    def done(self, form_list, **kwargs):
        """ Iterates over all forms and fills the Metadata/Dataset records accordingly

        Args:
            form_list (FormList): An iterable list of forms
            kwargs:
        Returns:

        """
        return super().done(form_list=form_list, **kwargs)
