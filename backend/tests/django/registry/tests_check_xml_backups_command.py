"""``check_xml_backups`` -- the operator answer to orphaned xml backups (#1150).

The command walks the three metadata record tables and reports every row whose
``xml_backup_file`` names a file the media storage does not hold -- the rows
which make every /csw page that contains one fail with DocumentUnavailable.
These tests pin what an operator relies on: an intact corpus exits 0; a lost
file is reported by identifier and exits 1; ``--model`` narrows the sweep to
one table; a row which names no file is an orphan too.
"""

from io import StringIO

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase

from registry.models.metadata import (ApplicationMetadataRecord,
                                      DatasetMetadataRecord, MetadataContact,
                                      ServiceMetadataRecord)

# the command never reads the document, only whether its file is there
DOCUMENT = b'<md:MD_Metadata xmlns:md="http://www.isotc211.org/2005/gmd"/>'


class CheckXmlBackupsCommandTests(TestCase):
    """One record per table; the tests then remove what the check must find."""

    def setUp(self):
        self.contact = MetadataContact.objects.create(name='integrity contact')
        self.dataset = self.create(
            DatasetMetadataRecord, 'de.mrmap.ds', dataset_contact=self.contact)
        self.service = self.create(ServiceMetadataRecord, 'de.mrmap.svc')
        self.application = self.create(
            ApplicationMetadataRecord, 'de.mrmap.app',
            application_contact=self.contact)

    def create(self, model, identifier, **extra):
        return model.objects.create(
            metadata_contact=self.contact,
            code_space='de.mrmap.',
            code=identifier.split('.')[-1],
            file_identifier=identifier,
            title=identifier,
            xml_backup_file=SimpleUploadedFile(
                f'{identifier}.xml', DOCUMENT, content_type='application/xml'),
            **extra)

    def check(self, expect_orphans, **options):
        """Run the command; it exits 1 exactly when orphans were found."""
        out = StringIO()
        if expect_orphans:
            with self.assertRaises(SystemExit) as exit_info:
                call_command('check_xml_backups', stdout=out, **options)
            self.assertEqual(exit_info.exception.code, 1)
        else:
            call_command('check_xml_backups', stdout=out, **options)
        return out.getvalue()

    def lose_file(self, record):
        """Drop the stored file from the storage while the row keeps naming it.

        Not ``FieldFile.delete()``: that also clears the field, while the
        #1150 situation is a row still pointing at a path the storage lost.
        """
        name = record.xml_backup_file.name
        default_storage.delete(name)
        return name

    # -- the verdict -------------------------------------------------------

    def test_an_intact_corpus_is_answered_successfully(self):
        out = self.check(expect_orphans=False)

        self.assertIn('dataset: 1 records checked, 0 without', out)
        self.assertIn('service: 1 records checked, 0 without', out)
        self.assertIn('application: 1 records checked, 0 without', out)
        self.assertIn('3 records checked, every stored document is there', out)

    def test_a_lost_file_is_reported_by_identifier_and_exits_1(self):
        # the DB row keeps pointing at the file while the storage lost it --
        # exactly the #1150 situation
        name = self.lose_file(self.dataset)

        out = self.check(expect_orphans=True)

        self.assertIn('de.mrmap.ds', out)
        self.assertIn(f'file={name}', out)
        self.assertIn('dataset: 1 records checked, 1 without', out)
        self.assertIn('3 records checked, 1 orphaned', out)

    def test_a_row_which_names_no_file_is_an_orphan_too(self):
        # an empty name can never answer a document either
        self.dataset.xml_backup_file = ''
        self.dataset.save()

        out = self.check(expect_orphans=True)

        self.assertIn('(empty)', out)
        self.assertIn('dataset: 1 records checked, 1 without', out)

    # -- narrowing the sweep -----------------------------------------------

    def test_the_model_option_only_checks_that_table(self):
        self.lose_file(self.dataset)

        # the orphan lives in the dataset table; the application sweep is clean
        out = self.check(expect_orphans=False, model='application')
        self.assertNotIn('dataset:', out)
        self.assertIn('application: 1 records checked', out)

        out = self.check(expect_orphans=True, model='dataset')
        self.assertIn('1 records checked, 1 without', out)
        self.assertNotIn('application:', out)

    def test_the_limit_names_the_first_orphans_and_counts_the_rest(self):
        for identifier in ('de.mrmap.lost-one', 'de.mrmap.lost-two'):
            lost = self.create(DatasetMetadataRecord, identifier,
                               dataset_contact=self.contact)
            self.lose_file(lost)

        # the sweep lists the orphans in pk order -- the pk is a random UUID,
        # so which identifier comes first is not predictable; the listed
        # number is: a limit of 2 shows both orphans and counts nothing more
        out = self.check(expect_orphans=True, limit=2)
        self.assertIn('de.mrmap.lost-one', out)
        self.assertIn('de.mrmap.lost-two', out)
        self.assertNotIn('... and', out)

        # a limit of 1 lists one orphan and counts the other as remainder
        out = self.check(expect_orphans=True, limit=1)
        self.assertIn('identifier=de.mrmap.lost-', out)
        self.assertIn('... and 1 more', out)
