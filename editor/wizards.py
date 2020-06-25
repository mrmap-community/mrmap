import json
import uuid
from json import JSONDecodeError

from django.contrib.gis.geos import GEOSGeometry, GeometryCollection
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponseRedirect
from django.urls import reverse
from MrMap.wizards import MrMapWizard
from editor.forms import DatasetIdentificationForm, DatasetClassificationForm, \
    DatasetLicenseConstraintsForm, DatasetSpatialExtentForm, DatasetQualityForm, DatasetResponsiblePartyForm
from django.utils.translation import gettext_lazy as _

from editor.helper.editor_helper import overwrite_dataset_metadata_document
from editor.settings import MR_MAP_DATASET_EDITOR_ORIGIN_NAME
from service.helper.enums import MetadataEnum
from service.helper.iso.iso_19115_metadata_builder import Iso19115MetadataBuilder
from service.models import Dataset, Metadata, MetadataRelation, MetadataOrigin, MetadataType, Document
from service.settings import MD_RELATION_TYPE_DESCRIBED_BY, DEFAULT_SRS
from structure.models import Organization, MrMapUser
from users.helper import user_helper

DATASET_WIZARD_FORMS = [(_("identification"), DatasetIdentificationForm),
                        (_("classification"), DatasetClassificationForm),
                        (_("responsible party"), DatasetResponsiblePartyForm),
                        (_("spatial extent"), DatasetSpatialExtentForm),
                        (_("licenses/constraints"), DatasetLicenseConstraintsForm),
                        (_("Quality"), DatasetQualityForm), ]


class DatasetWizard(MrMapWizard):

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
        if self.instance_id is not None:
            # Update
            metadata = Metadata.objects.get(id=self.instance_id)
            dataset = Dataset.objects.get(metadata=metadata)
        else:
            # New
            # Create instances
            metadata = Metadata()
            metadata.uuid = uuid.uuid4()
            metadata.identifier = metadata.uuid
            metadata.metadata_type = MetadataType.objects.get_or_create(
                type=MetadataEnum.DATASET.value
            )[0]
            metadata.is_active = True

            dataset = Dataset()
            dataset.is_active = True
            dataset.md_identifier_code = metadata.identifier
            dataset.metadata_standard_name = "ISO 19115 Geographic information - Metadata"
            dataset.metadata_standard_version = "ISO 19115:2003(E)"

            # Pre-save objects to be able to add M2M relations
            metadata.save()
            dataset.metadata = metadata
            dataset.save()
            metadata.metadata_url = reverse("service:get-dataset-metadata", args=(dataset.id,))

        user = user_helper.get_user(request=self.request)
        self._fill_form_list(form_list, metadata, dataset, user)

        return HttpResponseRedirect(reverse(self.current_view, ), status=303)

    @staticmethod
    def _fill_form_list(form_list, metadata: Metadata, dataset: Dataset, user: MrMapUser):
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
            doc = Document.objects.get(related_metadata__id=metadata.id)
            DatasetWizard._overwrite_dataset_document(metadata, doc)
        except ObjectDoesNotExist:
            DatasetWizard._create_dataset_document(metadata)

    @staticmethod
    def _fill_metadata_dataset_identification_form(data: dict, metadata: Metadata, dataset: Dataset, user: MrMapUser):
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
        metadata.related_metadata.filter(origin__name=MR_MAP_DATASET_EDITOR_ORIGIN_NAME).delete()
        for additional_object in additional_related_objects:
            md_relation = MetadataRelation()
            md_relation.metadata_to = metadata
            md_relation.metadata_from = additional_object
            md_relation.relation_type = MD_RELATION_TYPE_DESCRIBED_BY
            md_relation.internal = True
            md_relation.origin = MetadataOrigin.objects.get_or_create(
                name=MR_MAP_DATASET_EDITOR_ORIGIN_NAME
            )[0]
            md_relation.save()
            additional_object.related_metadata.add(md_relation)
            metadata.related_metadata.add(md_relation)

    @staticmethod
    def _fill_metadata_dataset_classification_form(data: dict, metadata: Metadata, dataset: Dataset, user: MrMapUser):
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
    def _fill_metadata_dataset_spatial_extent_form(data: dict, metadata: Metadata, dataset: Dataset, user: MrMapUser):
        """ Fills form data into Metadata/Dataset records

        Args:
            data (dict): Cleaned form data
            metadata (dict): The metadata record
            dataset (dict): The dataset record
            user: The performing user
        Returns:

        """
        try:
            bounding_geometry = json.loads(data.get("bounding_geometry", "{}"))
        except JSONDecodeError:
            bounding_geometry = {}
        if bounding_geometry.get("features", None) is not None:
            # A list of features
            geoms = [GEOSGeometry(str(feature["geometry"]), srid=DEFAULT_SRS) for feature in bounding_geometry.get("features")]
            geom = GeometryCollection(geoms, srid=DEFAULT_SRS).unary_union
        elif bounding_geometry.get("feature", None) is not None:
            geom = GEOSGeometry(str(bounding_geometry.get("feature")["geometry"]), srid=DEFAULT_SRS)
        else:
            try:
                geom = GEOSGeometry(str(bounding_geometry), srid=DEFAULT_SRS)
            except Exception:
                # No features provided
                geom = None
        metadata.bounding_geometry = geom

    @staticmethod
    def _fill_metadata_dataset_licence_form(data: dict, metadata: Metadata, dataset: Dataset, user: MrMapUser):
        """ Fills form data into Metadata/Dataset records

        Args:
            data (dict): Cleaned form data
            metadata (dict): The metadata record
            dataset (dict): The dataset record
            user: The performing user
        Returns:

        """
        metadata.terms_of_use = data.get("terms_of_use", None) or None
        metadata.access_constraints = data.get("access_constraints", None)

    @staticmethod
    def _fill_metadata_dataset_quality_form(data: dict, metadata: Metadata, dataset: Dataset, user: MrMapUser):
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
    def _fill_metadata_dataset_responsible_party_form(data:dict, metadata: Metadata, dataset: Dataset, user: MrMapUser):
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
                is_auto_generated=True,
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
        document_obj = Document.objects.get_or_create(
            related_metadata=metadata
        )[0]
        doc_builder = Iso19115MetadataBuilder(metadata.id, MetadataEnum.DATASET)
        dataset_doc_string = doc_builder.generate_service_metadata()
        document_obj.original_dataset_metadata_document = dataset_doc_string.decode("UTF-8")
        document_obj.current_dataset_metadata_document = document_obj.original_dataset_metadata_document
        document_obj.save()

    @staticmethod
    def _overwrite_dataset_document(metadata: Metadata, doc: Document = None):
        """ Overwrites a Document record for an existing Dataset entry

        Args:
            metadata (Metadata): The metadata record
            doc (Document): The document record
        Returns:

        """
        if doc is None:
            doc = Document.objects.get(related_metadata=metadata)
        doc_builder = Iso19115MetadataBuilder(metadata.id, MetadataEnum.DATASET)
        dataset_doc_string = doc_builder.overwrite_dataset_metadata(doc.current_dataset_metadata_document or doc.original_dataset_metadata_document)
        doc.current_dataset_metadata_document = dataset_doc_string.decode("UTF-8")
        doc.save()