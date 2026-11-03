""" Tests for the derived coupling index of service metadata records.

    The index answers which harvested service records name a dataset, see
    :class:`registry.managers.metadata.MetadataCouplingReferenceManager` and
    :class:`registry.models.metadata.MetadataCouplingReference`.
"""

from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase

from registry.enums.metadata import MetadataCouplingKindEnum
from registry.models.metadata import (DatasetMetadataRecord, MetadataContact,
                                      MetadataCouplingReference,
                                      ServiceMetadataRecord)

TEST_DATA = Path(__file__).resolve().parents[2] / "test_data"
SERVICE_XML = (TEST_DATA / "wms-service-metadata.xml").read_bytes()

#: the values which the service fixture advertises in srv:operatesOn and in
#: its three srv:coupledResource elements
UUIDREF = "19A39B3A-2D9E-4805-A5E6-56A5CA3EC8CB"
RESOURCE_ID = ("https://registry.gdi-de.org/id/de.hh/"
               "72796D51-86BC-4343-AE77-85ECAFFACF15")
CODE_SPACE = "https://registry.gdi-de.org/id/de.hh/"
CODE = "72796D51-86BC-4343-AE77-85ECAFFACF15"


class MetadataCouplingReferenceTests(TestCase):
    """ The rows of the index, their lifecycle and the inverse lookup. """

    @classmethod
    def setUpTestData(cls):
        cls.contact = MetadataContact.objects.create(name="Coupling contact")

    def service_record(self, **attributes):
        """ A service metadata record holding the coupling fixture. """
        record = ServiceMetadataRecord.objects.create(
            metadata_contact=self.contact, **attributes)
        record.xml_backup_file = SimpleUploadedFile("service.xml", SERVICE_XML)
        record.save()
        return record

    def dataset_record(self, **attributes):
        return DatasetMetadataRecord.objects.create(
            metadata_contact=self.contact,
            dataset_contact=self.contact, **attributes)

    def kinds(self, dataset):
        return set(
            MetadataCouplingReference.objects
            .for_dataset(dataset)
            .values_list("reference_kind", flat=True))

    def test_rebuild_answers_one_row_per_advertised_reference(self):
        record = self.service_record(title="HH WMS", code="hh-wms")
        rows = MetadataCouplingReference.objects.rebuild_for(record)
        self.assertEqual(
            {(row.reference_kind, row.value, row.operation_name)
             for row in rows},
            {
                (MetadataCouplingKindEnum.UUIDREF.value, UUIDREF, ""),
                (MetadataCouplingKindEnum.HREF.value, RESOURCE_ID, ""),
                (MetadataCouplingKindEnum.IDENTIFIER.value, RESOURCE_ID,
                 "GetCapabilities"),
                (MetadataCouplingKindEnum.IDENTIFIER.value, RESOURCE_ID,
                 "GetMap"),
                (MetadataCouplingKindEnum.IDENTIFIER.value, RESOURCE_ID,
                 "GetFeatureInfo"),
            })
        self.assertEqual(
            MetadataCouplingReference.objects
            .filter(service_metadata=record).count(), 5)

    def test_saving_the_record_keeps_the_index_derived(self):
        record = self.service_record(title="HH WMS", code="hh-wms")
        self.assertEqual(MetadataCouplingReference.objects.count(), 5)
        # the rows are derived: saving again regenerates them, never adds
        record.save()
        self.assertEqual(MetadataCouplingReference.objects.count(), 5)

    def test_a_record_without_a_readable_document_holds_no_rows(self):
        record = self.service_record(title="HH WMS", code="hh-wms")
        record.xml_backup_file = SimpleUploadedFile("other.xml", b"<other/>")
        record.save()
        self.assertEqual(MetadataCouplingReference.objects.count(), 0)

    def test_a_record_without_a_stored_document_at_all_holds_no_rows(self):
        ServiceMetadataRecord.objects.create(
            metadata_contact=self.contact, title="No document", code="no-doc")
        self.assertEqual(MetadataCouplingReference.objects.count(), 0)

    def test_the_persistence_order_of_a_harvest_fills_the_index(self):
        # the mapper saves a harvested record before it writes its backup
        # file; the save which writes the file is the one which can read it
        record = ServiceMetadataRecord.objects.create(
            metadata_contact=self.contact, title="HH WMS", code="hh-wms")
        self.assertEqual(MetadataCouplingReference.objects.count(), 0)
        record.xml_backup_file.save("md_metadata.xml", ContentFile(SERVICE_XML))
        self.assertEqual(MetadataCouplingReference.objects.count(), 5)

    def test_a_removed_document_removes_the_rows_of_its_record(self):
        record = self.service_record(title="HH WMS", code="hh-wms")
        record.xml_backup_file.delete(save=True)
        self.assertEqual(MetadataCouplingReference.objects.count(), 0)

    def test_deleting_the_record_removes_its_rows(self):
        record = self.service_record(title="HH WMS", code="hh-wms")
        record.delete()
        self.assertEqual(MetadataCouplingReference.objects.count(), 0)

    def test_command_rebuilds_the_index_from_the_stored_documents(self):
        self.service_record(title="HH WMS", code="hh-wms")
        MetadataCouplingReference.objects.all().delete()
        call_command("rebuild_metadata_coupling_references")
        self.assertEqual(MetadataCouplingReference.objects.count(), 5)

    def test_uuidref_names_the_file_identifier_of_a_record(self):
        self.service_record(title="HH WMS", code="hh-wms")
        named = self.dataset_record(
            title="Named dataset", code="named", file_identifier=UUIDREF)
        self.assertEqual(
            self.kinds(named), {MetadataCouplingKindEnum.UUIDREF.value})

    def test_resource_references_name_the_code_and_resource_identifier(self):
        self.service_record(title="HH WMS", code="hh-wms")
        named = self.dataset_record(
            title="Named dataset", code_space=CODE_SPACE, code=CODE)
        self.assertEqual(
            self.kinds(named),
            {MetadataCouplingKindEnum.HREF.value,
             MetadataCouplingKindEnum.IDENTIFIER.value})

    def test_a_scoped_name_is_matched_like_a_resource_identifier(self):
        record = self.service_record(title="HH WMS", code="hh-wms")
        MetadataCouplingReference.objects.create(
            service_metadata=record,
            reference_kind=MetadataCouplingKindEnum.SCOPED_NAME.value,
            value=CODE)
        named = self.dataset_record(
            title="Named dataset", code_space=CODE_SPACE, code=CODE)
        self.assertIn(MetadataCouplingKindEnum.SCOPED_NAME.value,
                      self.kinds(named))

    def test_the_namespaces_of_the_kinds_are_kept_apart(self):
        self.service_record(title="HH WMS", code="hh-wms")
        # the uuidref names a metadata record; as a resource identifier of a
        # dataset it is a value of another namespace and must not match
        other = self.dataset_record(
            title="Other dataset", code_space="https://example.org/id/",
            code=UUIDREF)
        self.assertEqual(
            MetadataCouplingReference.objects.for_dataset(other).count(), 0)

    def test_the_code_space_alone_never_names_a_whole_namespace(self):
        self.service_record(title="HH WMS", code="hh-wms")
        # a sibling resource of the same namespace is not the coupled one
        sibling = self.dataset_record(
            title="Sibling dataset", code_space=CODE_SPACE,
            code="another-resource")
        self.assertEqual(
            MetadataCouplingReference.objects.for_dataset(sibling).count(), 0)
