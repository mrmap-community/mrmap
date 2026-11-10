"""#1211: a contact address of a real Capabilities document is storable.

Registering the WMS "ZDM der GDWS Standort Kiel" failed hard with
``value too long for type character varying(100)`` without naming the field:
its ``ContactInformation`` address is free ISO/OGC text over 100 characters,
while every ``MetadataContact`` field except ``name`` and ``person_name`` was
capped at 100. The INSERT of that statement is made by the persistence
handler's ``bulk_create`` with ``ignore_conflicts`` -- a path which never asks
the model for validation -- so the raw ``DataError`` refused the whole
registration transaction and the service could not be registered at all.

``0041`` widens the nine narrow fields to 255. These tests keep both sides of
that, following the keyword widening of ``0028`` (#894): the old schema is
witnessed as the failure, the migration as its fix, and the handler path
which made the failing statement is kept green on the current schema.
"""

from django.db import DataError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from registry.mappers.persistence.handler import PersistenceHandler
from registry.models.metadata import MetadataContact

# the contact of the failing INSERT, as the issue quotes it; the long free-text
# address is what the narrow column refused, so it is carried verbatim
REPORT_CONTACT = dict(
    name='Zentrales Datenmanagement der GDWS Standort Kiel',
    address=('Zentrales Datenmanagement der GDWS Standort Kiel beim '
             'Wasserstraßen- und Schifffahrtsamt Elbe-Nordsee, Fachbereich '
             'Fachdienste und Projekte, Moorweidenstrasse 14'))


class ContactWidthMigrationTest(TransactionTestCase):
    """The narrow column is what refused the address; the widening keeps it."""

    migrate_from = [
        ('registry',
         '0040_catalogueservicegetcapabilitiesproberesult_error_detail_and_more')]
    migrate_to = [
        ('registry',
         '0041_contact_fields_are_wide_enough_for_real_addresses')]

    def setUp(self):
        super().setUp()
        self.addCleanup(self.restore_schema)

    def test_the_narrow_column_is_what_refused_the_address(self):
        """The old schema is kept as the failure, so that the fix has a witness."""
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        apps = executor.loader.project_state(self.migrate_from).apps
        Contact = apps.get_model('registry', 'MetadataContact')
        self.assertGreater(len(REPORT_CONTACT['address']), 100)
        with self.assertRaises(DataError), transaction.atomic():
            Contact.objects.create(**REPORT_CONTACT)

    def test_the_widening_keeps_the_address_of_the_report(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        apps = executor.loader.project_state(self.migrate_to).apps
        Contact = apps.get_model('registry', 'MetadataContact')
        contact = Contact.objects.create(**REPORT_CONTACT)

        self.assertEqual(
            Contact.objects.values_list('address', flat=True)
            .get(pk=contact.pk),
            REPORT_CONTACT['address'],
            'the widened column does not answer the address it was given')

    def restore_schema(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())


class ContactRegistrationPathTest(TestCase):
    """The statement which failed in the report runs green on current schema."""

    def test_the_persistence_handler_stores_the_address_of_the_report(self):
        """Not a plain save: the lookup tables go through the handler's one
        ``bulk_create`` with ``ignore_conflicts``, which is the INSERT the
        issue captured with a ``CaptureQueriesContext`` and which never
        reaches a model-level validation."""
        PersistenceHandler(mapper=None)._persist_get_or_create(
            [MetadataContact(**REPORT_CONTACT)])

        self.assertEqual(
            list(MetadataContact.objects.filter(
                name=REPORT_CONTACT['name'])
                .values_list('address', flat=True)),
            [REPORT_CONTACT['address']])
