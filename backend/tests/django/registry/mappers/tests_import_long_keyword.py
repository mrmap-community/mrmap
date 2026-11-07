"""One over-long keyword must not take the record holding it down (issue #1075).

A live deployment lost three records of one GDI-BW run with the same signature:
the document mapped, the keyword landed in the relation, and the UPDATE of the
sync trigger refused the over-long keyword with ``value too long for type
character varying(300)`` -- the deployed trigger function still answered its
empty-array fallback as ``varchar(300)[]`` as written by ``0021``, so the whole
save of the record rolled back and the file kept its import error (sample
temporary file 1079625). Migration ``0035`` re-creates the maintaining functions
with the widened column they maintain.

This is one of the lost files as the contract which must not lose it again: a
service document of the corpus which publishes one comma-joined keyword of more
than three hundred characters -- the keyword of the report -- stored like a
downloaded record and imported by the very call of the import task. The record
enters the registry, its denormalized array answers the keyword exactly as the
catalogue published it, and the file leaves no import error behind.
"""

from django.test import TestCase

from registry.models.harvest import TemporaryMdMetadataFile
from registry.models.metadata import ServiceMetadataRecord
from tests.django.registry.mappers.tests_import_keyword_quality import (
    GDI_BW_LIST, keyword_document)
from tests.django.registry.mappers.tests_import_writes_each_record_once import \
    ImportHarness


class LongKeywordImportTest(ImportHarness, TestCase):
    """The failing temporary file, imported the way the import task does."""

    def setUp(self):
        super().setUp()
        # the keyword of the report: one gmd:keyword joining eleven plan names,
        # wider than any column the schema ever had
        self.document = keyword_document("service.xml", "de.1075.long-keyword",
                                         [GDI_BW_LIST])

    def test_a_service_document_with_one_over_long_keyword_is_imported(self):
        """The reproduction command of the issue in one call: a stored file of a
        run answers its record instead of raising inside the save."""
        self.assertGreater(len(GDI_BW_LIST), 300)

        file = self.stored_file(self.new_run())
        file.md_metadata_file_to_db()

        record = ServiceMetadataRecord.objects.get()
        self.assertIn(GDI_BW_LIST, [keyword.keyword for keyword in record.keywords.all()],
                      'the keyword is not stored exactly as the catalogue published it')
        stored = ServiceMetadataRecord.objects.values_list(
            'keywords_list', flat=True).get(pk=record.pk)
        self.assertIn(GDI_BW_LIST, stored,
                      'the denormalized array answers another text than the '
                      'keywords relation of the very same record')

    def test_the_file_of_an_over_long_keyword_lands_no_import_error(self):
        """The import task reads any exception of a file as a record error and
        marks the file; the imported file is deleted, the failed one would stay
        with its traceback (#894 lost four files that way, #1075 three more)."""
        file = self.stored_file(self.new_run())
        file.md_metadata_file_to_db()

        self.assertFalse(
            TemporaryMdMetadataFile.objects.exists(),
            'a file which stays after the import was not imported: the task '
            'keeps it with its traceback as import error, which is how the '
            'over-long keyword lost the record (#894, #1075)')
