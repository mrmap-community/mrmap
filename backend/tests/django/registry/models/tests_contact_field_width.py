"""#1211: a contact address of a real Capabilities document is storable.

Registering the WMS "ZDM der GDWS Standort Kiel" failed hard with
``value too long for type character varying(100)`` without naming the field:
its ``ContactInformation`` address is free ISO/OGC text over 100 characters,
while every ``MetadataContact`` field except ``name`` and ``person_name`` was
capped at 100. The INSERT of that statement is made by the persistence
handler's ``bulk_create`` with ``ignore_conflicts`` -- a path which never asks
the model for validation -- so the raw ``DataError`` refused the whole
registration transaction and the service could not be registered at all.

The nine narrow fields carry 255 since the widening of #1211. The rebuilt
chain (#1850) answers that schema from ``0001_initial`` and has no node left
below which the narrow column stands, so the migration test builds the narrow
schema itself -- a narrowing is what the way back of that node was, statement
for statement the ``varchar(255)`` the chain created read from the catalog --
witnesses the failure there, and runs the widening back over it. Both sides
of #1211 stayed what they were: the old schema is kept as the failure, the
widening as its fix, and the handler path which made the failing statement is
kept green on the current schema.
"""

from django.db import DataError, connection, transaction
from django.test import TestCase

from registry.mappers.persistence.handler import PersistenceHandler
from registry.models.metadata import MetadataContact

# the contact of the failing INSERT, as the issue quotes it; the long free-text
# address is what the narrow column refused, so it is carried verbatim
REPORT_CONTACT = dict(
    name='Zentrales Datenmanagement der GDWS Standort Kiel',
    address=('Zentrales Datenmanagement der GDWS Standort Kiel beim '
             'Wasserstraßen- und Schifffahrtsamt Elbe-Nordsee, Fachbereich '
             'Fachdienste und Projekte, Moorweidenstrasse 14'))

# the nine fields which were capped at 100 before #1211 widened them -- the
# ``name`` and ``person_name`` of the model were wide from the start and are
# not touched by the narrowing below
NARROW_FIELDS = ('address', 'address_type', 'city', 'country', 'email',
                 'facsimile', 'phone', 'postal_code', 'state_or_province')


class ContactWidthMigrationTest(TestCase):
    """The narrow column is what refused the address; the widening keeps it.

    The rebuilt chain (#1850) creates the contact table already wide, so the
    executor has no node to travel back to which refused the address; the
    class rebuilds that schema itself by narrowing the nine fields of #1211
    to ``varchar(100)`` -- the very way back the widening node carried --
    over a database which holds no value longer than the width it narrows to,
    and runs the widening back to the width the catalog answers.
    """

    def contact_column_widths(self):
        """The width of the nine fields, as the live schema answers them."""
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT column_name, character_maximum_length"
                " FROM information_schema.columns"
                " WHERE table_name = %s AND column_name = ANY(%s)",
                [MetadataContact._meta.db_table, list(NARROW_FIELDS)])
            widths = dict(cursor.fetchall())
        self.assertEqual(
            set(widths), set(NARROW_FIELDS),
            'the contact table does not answer all nine fields of #1211')
        return widths

    def alter_contact_fields(self, width):
        """The nine fields to one width -- the statement of the way back at
        100, the statement of the widening at 255.
        """
        with connection.cursor() as cursor:
            cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')
            for field in NARROW_FIELDS:
                cursor.execute(
                    'ALTER TABLE "%s" ALTER COLUMN "%s" TYPE varchar(%d)'
                    % (MetadataContact._meta.db_table, field, width))

    def test_the_narrow_column_is_what_refused_the_address(self):
        """The old schema is kept as the failure, so that the fix has a witness."""
        # the witness that the rebuilt chain is what #1211 promised, before
        # the schema is narrowed under it
        self.assertEqual(self.contact_column_widths(),
                         dict.fromkeys(NARROW_FIELDS, 255))
        self.alter_contact_fields(100)
        self.assertGreater(len(REPORT_CONTACT['address']), 100)
        with self.assertRaises(DataError), transaction.atomic():
            MetadataContact.objects.create(**REPORT_CONTACT)

    def test_the_widening_keeps_the_address_of_the_report(self):
        self.alter_contact_fields(100)

        self.alter_contact_fields(255)
        contact = MetadataContact.objects.create(**REPORT_CONTACT)

        self.assertEqual(
            MetadataContact.objects.values_list('address', flat=True)
            .get(pk=contact.pk),
            REPORT_CONTACT['address'],
            'the widened column does not answer the address it was given')
        self.assertEqual(self.contact_column_widths(),
                         dict.fromkeys(NARROW_FIELDS, 255))


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
