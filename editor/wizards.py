import json
import uuid
from json import JSONDecodeError

from django.contrib.gis.geos import GEOSGeometry, Polygon, GeometryCollection
from django.http import HttpResponseRedirect
from django.urls import reverse
from MrMap.wizards import MrMapWizard
from editor.forms import DatasetIdentificationForm, DatasetClassificationForm, \
    DatasetLicenseConstraintsForm, DatasetSpatialExtentForm, DatasetQualityForm
from django.utils.translation import gettext_lazy as _

from service.helper.enums import MetadataEnum
from service.helper.iso.iso_19115_metadata_builder import Iso19115MetadataBuilder
from service.models import Dataset, Metadata, MetadataRelation, MetadataOrigin, MetadataType, Document
from service.settings import MD_RELATION_TYPE_DESCRIBED_BY, DEFAULT_SRS

DATASET_WIZARD_FORMS = [(_("identification"), DatasetIdentificationForm),
                        (_("classification"), DatasetClassificationForm),
                        (_("spatial extent"), DatasetSpatialExtentForm),
                        (_("licenses/constraints"), DatasetLicenseConstraintsForm),
                        (_("Quality"), DatasetQualityForm), ]


class DatasetWizard(MrMapWizard):

    def done(self, form_list, **kwargs):
        """ Iterates over all forms and fills the Metadata/Dataset records accordingly

        Args:
            form_list (FormList): An iterable list of forms
            kwargs:
        Returns:

        """
        instance_id = kwargs.pop("instance_id", None)
        if instance_id is not None:
            # Update
            metadata = Metadata.objects.get(id=instance_id)
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

        self._fill_form_list(form_list, metadata, dataset)

        return HttpResponseRedirect(reverse(self.kwargs['current_view'], ), status=303)

    @staticmethod
    def _fill_form_list(form_list, metadata: Metadata, dataset: Dataset):
        """ Iterates over all forms and applies the metadata changes on the objects

        Args:
            form_list: The list of forms
            metadata: The metadata record
            dataset: The dataset record
        Returns:

        """
        function_map = {
            "DatasetIdentificationForm": DatasetWizard._fill_metadata_dataset_identification_form,
            "DatasetClassificationForm": DatasetWizard._fill_metadata_dataset_classification_form,
            "DatasetSpatialExtentForm": DatasetWizard._fill_metadata_dataset_spatial_extent_form,
            "DatasetLicenseConstraintsForm": DatasetWizard._fill_metadata_dataset_licence_form,
            "DatasetQualityForm": DatasetWizard._fill_metadata_dataset_quality_form,
        }

        for form in form_list:
            form_class = type(form).__name__
            function_map[form_class](form.cleaned_data, metadata, dataset)

        DatasetWizard._create_dataset_document(metadata, dataset)

        dataset.save()
        metadata.save()

    @staticmethod
    def _fill_metadata_dataset_identification_form(data: dict, metadata: Metadata, dataset: Dataset):
        """ Fills form data into Metadata/Dataset records

        Args:
            data (dict): Cleaned form data
            metadata (dict): The metadata record
            dataset (dict): The dataset record
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
        metadata.related_metadata.all().delete()
        for additional_object in additional_related_objects:
            md_relation = MetadataRelation()
            md_relation.metadata_to = metadata
            md_relation.metadata_from = additional_object
            md_relation.relation_type = MD_RELATION_TYPE_DESCRIBED_BY
            md_relation.internal = True
            md_relation.origin = MetadataOrigin.objects.get_or_create(
                name="MrMap Dataset Editor"
            )[0]
            md_relation.save()
            additional_object.related_metadata.add(md_relation)
            metadata.related_metadata.add(md_relation)

    @staticmethod
    def _fill_metadata_dataset_classification_form(data: dict, metadata: Metadata, dataset: Dataset):
        """ Fills form data into Metadata/Dataset records

        Args:
            data (dict): Cleaned form data
            metadata (dict): The metadata record
            dataset (dict): The dataset record
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
    def _fill_metadata_dataset_spatial_extent_form(data: dict, metadata: Metadata, dataset: Dataset):
        """ Fills form data into Metadata/Dataset records

        Args:
            data (dict): Cleaned form data
            metadata (dict): The metadata record
            dataset (dict): The dataset record
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
            # No features provided
            geom = None
        metadata.bounding_geometry = geom

    @staticmethod
    def _fill_metadata_dataset_licence_form(data: dict, metadata: Metadata, dataset: Dataset):
        """ Fills form data into Metadata/Dataset records

        Args:
            data (dict): Cleaned form data
            metadata (dict): The metadata record
            dataset (dict): The dataset record
        Returns:

        """
        metadata.terms_of_use = data.get("terms_of_use", None) or None
        metadata.access_constraints = data.get("access_constraints", None)

    @staticmethod
    def _fill_metadata_dataset_quality_form(data: dict, metadata: Metadata, dataset: Dataset):
        """ Fills form data into Metadata/Dataset records

        Args:
            data (dict): Cleaned form data
            metadata (dict): The metadata record
            dataset (dict): The dataset record
        Returns:

        """
        dataset.update_frequency_code = data.get("maintenance_and_update_frequency", None)
        dataset.lineage_statement = data.get("lineage_statement", None)

    @staticmethod
    def _create_dataset_document(metadata: Metadata, dataset: Dataset):
        """ Creates a Document record for the new Dataset entry

        Args:
            metadata (Metadata): The metadata record
            dataset (Dataset): The dataset record
        Returns:

        """
        document_obj = Document.objects.get_or_create(
            related_metadata=metadata
        )[0]
        doc_builder = Iso19115MetadataBuilder(metadata.id, MetadataEnum.DATASET.value)
        dataset_doc_string = doc_builder.generate_service_metadata()
        document_obj.current_dataset_metadata_document = dataset_doc_string
        document_obj.save()
