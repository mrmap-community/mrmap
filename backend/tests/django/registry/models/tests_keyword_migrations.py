"""The keyword maintenance of the records, proven on the rebuilt history (#1850).

Every class in this file was a travel of the migration executor over named
nodes of the old chain: down to the schema before the keyword constraint, the
widening or the transfer, up to the node which fixed it, and the assertion of
what the schema and the data answered in between. The rebuild (#1850) created
the final schema from the models and left no name of those nodes, and a test
migrating to one of them now runs into ``NodeNotFoundError``.

The proofs are kept the way #1850 keeps a dropped view: the statements of the
state in question are carried here from the history of the old chain, the test
builds the intermediate schema itself, and the upgrade and degrade statements
of the removed node run against the migrated test database. What each class
still asserts is the constraint, the trigger or the column width standing in
the schema and the data which survives it -- never the name of a revision.

*   the blank-keyword constraint: taken off the table the way the old chain
    found it, the removal statements of the fix run over the blanks, and the
    constraint which the rebuilt ``0001_initial`` created -- read from the
    catalog, not retyped -- refuses the next blank;
*   the keyword widening of #894: the narrow ``varchar(300)`` column and the
    narrow array rebuilt around the stored vector which reads them, the
    failure witnessed there, and the widening which brought the vector, its
    index and the rename trigger back asked with data;
*   the transfer of #1009: the legacy functions and triggers of #1075's shape
    installed as the way back of the transfer installed them, and the package
    objects put back by the package itself over them, in both directions;
*   the explicit through models: the physical tables of the keywords
    relations, their links and their triggers surviving the travel the
    rebuilt chain offers between its deepest reachable node and its leaf.
"""

from django.db import DataError, IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models import Q
from django.test import TestCase, TransactionTestCase
from pgtrigger import install as install_triggers, uninstall as uninstall_triggers

from registry.expressions.search import TEXT_CONFIGURATION_NAME
from registry.models.metadata import (DatasetMetadataRecord, Keyword,
                                      MetadataContact)
from registry.models.service import WebMapService

#: the lowest node of the rebuilt registry chain the executor can travel to:
#: its successor loads the initial data with a forward-only ``RunPython``,
#: which by Django's own rule makes everything above it untraversable
#: backwards, so no travel below the seed node exists
SEED = ('registry', '0003_the_initial_data_is_seeded')

#: the check constraint of #1123, as the rebuilt ``0001_initial`` creates it;
#: the blank-keyword test takes it off the table and puts back the very
#: definition the catalog answers, so what refuses the next blank below is
#: the constraint of the chain
NON_EMPTY_CONSTRAINT = 'registry_keyword_non_empty_keywords'

# the removal statements of the blank-keyword node, carried verbatim: every
# keywords relation of a maintained table loses the links of the blanks, and
# the blanks themselves go last -- the same order, and the same condition,
# the node ran inside its transaction
REMOVE_BLANK_KEYWORDS = [
    'DELETE FROM "registry_catalogueservice_keywords" WHERE "keyword_id" IN '
    '(SELECT "id" FROM "registry_keyword" WHERE NOT ("keyword" ~ \'\\S\') '
    'OR "keyword" IS NULL);',
    'DELETE FROM "registry_datasetmetadatarecord_keywords" WHERE "keyword_id" IN '
    '(SELECT "id" FROM "registry_keyword" WHERE NOT ("keyword" ~ \'\\S\') '
    'OR "keyword" IS NULL);',
    'DELETE FROM "registry_featuretype_keywords" WHERE "keyword_id" IN '
    '(SELECT "id" FROM "registry_keyword" WHERE NOT ("keyword" ~ \'\\S\') '
    'OR "keyword" IS NULL);',
    'DELETE FROM "registry_layer_keywords" WHERE "keyword_id" IN '
    '(SELECT "id" FROM "registry_keyword" WHERE NOT ("keyword" ~ \'\\S\') '
    'OR "keyword" IS NULL);',
    'DELETE FROM "registry_servicemetadatarecord_keywords" WHERE "keyword_id" IN '
    '(SELECT "id" FROM "registry_keyword" WHERE NOT ("keyword" ~ \'\\S\') '
    'OR "keyword" IS NULL);',
    'DELETE FROM "registry_webfeatureservice_keywords" WHERE "keyword_id" IN '
    '(SELECT "id" FROM "registry_keyword" WHERE NOT ("keyword" ~ \'\\S\') '
    'OR "keyword" IS NULL);',
    'DELETE FROM "registry_webmapservice_keywords" WHERE "keyword_id" IN '
    '(SELECT "id" FROM "registry_keyword" WHERE NOT ("keyword" ~ \'\\S\') '
    'OR "keyword" IS NULL);',
    'DELETE FROM "registry_keyword" WHERE "id" IN '
    '(SELECT "id" FROM "registry_keyword" WHERE NOT ("keyword" ~ \'\\S\') '
    'OR "keyword" IS NULL);',
]

# the record types whose keywords array shares the fate of the keyword column
# during the widening, as the widening node of the old chain listed them; the
# application record came after the widening and shares only the text it
# stores today
WIDENED_RECORD_TABLES = ('registry_datasetmetadatarecord',
                         'registry_servicemetadatarecord')

#: the package object of the keyword rename fan-out, addressed the way the
#: package addresses its objects; uninstalling and installing it is what the
#: way back and the way forward of the widening did to the hand written
#: trigger of the keyword table, and the package recompiles it from the
#: declaration in ``registry/triggers.py``
KEYWORD_RENAME_TRIGGER_URI = 'registry.Keyword:keyword_sync_to_metadatarecords'

#: the seven objects of the transfer (#1009) in both of its states: the
#: package side, as ``registry/triggers.py`` registers it (model and trigger
#: name, addressed ``model:trigger`` by the package), beside the legacy side
#: which the transfer replaced -- the names the legacy objects carried and
#: the statements which create and drop them, carried verbatim from the
#: transfer node of the old chain, where they were the sql of the way back
KEYWORD_PACKAGE_TRIGGERS = [
    ('registry.DatasetMetadataRecordKeywordsLink',
     'datasetmetadatarecord_keywords_list_sync'),
    ('registry.DatasetMetadataRecord',
     'datasetmetadatarecord_keywords_list_keep'),
    ('registry.ServiceMetadataRecordKeywordsLink',
     'servicemetadatarecord_keywords_list_sync'),
    ('registry.ServiceMetadataRecord',
     'servicemetadatarecord_keywords_list_keep'),
    ('registry.ApplicationMetadataRecordKeywordsLink',
     'applicationmetadatarecord_keywords_list_sync'),
    ('registry.ApplicationMetadataRecord',
     'applicationmetadatarecord_keywords_list_keep'),
    ('registry.Keyword',
     'keyword_sync_to_metadatarecords'),
]

KEYWORD_TRIGGER_URIS = ['%s:%s' % pair for pair in KEYWORD_PACKAGE_TRIGGERS]

# the three legacy functions as the widened-element-type fix answered them:
# the empty array of the aggregate carries the element type the columns have,
# so nothing is re-cast on the way into them -- the bodies the way back of
# the transfer installed, which is the state the deployment must be able to
# roll back to (#1075)
LEGACY_SYNC_FUNCTION = """
CREATE OR REPLACE FUNCTION registry_sync_metadatarecord_keywords_list()
    RETURNS TRIGGER
    LANGUAGE plpgsql
AS $$
DECLARE
    -- the record table and the foreign key of the relation the trigger fires on,
    -- given as trigger arguments so that one function serves every record type
    record_table text := TG_ARGV[0];
    foreign_key  text := TG_ARGV[1];
    record_id    uuid;
BEGIN
    -- the key is read through jsonb: the column the trigger needs is only known
    -- at run time and a record parameter cannot be addressed by a field name
    SELECT (to_jsonb(CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END) ->> foreign_key)::uuid
      INTO record_id;

    IF NOT FOUND OR record_id IS NULL THEN
        RETURN NULL;
    END IF;

    EXECUTE format(
        'UPDATE %1$I AS record
            SET keywords_list = (SELECT COALESCE(array_agg(DISTINCT keyword.keyword ORDER BY keyword.keyword),
                             ''{}''::text[])
                 FROM %2$I AS relation
                 JOIN registry_keyword AS keyword ON keyword.id = relation.keyword_id
                WHERE relation.%3$I = record.id
                  AND btrim(keyword.keyword) <> '')
          WHERE record.id = $1',
        record_table, TG_TABLE_NAME, foreign_key
    ) USING record_id;

    RETURN NULL;
END;
$$;
"""

LEGACY_KEEP_FUNCTION = """
CREATE OR REPLACE FUNCTION registry_keep_metadatarecord_keywords_list()
    RETURNS TRIGGER
    LANGUAGE plpgsql
AS $$
DECLARE
    -- the table of the keywords relation and its foreign key, given as trigger
    -- arguments so that one function serves every record type
    relation    text := TG_ARGV[0];
    foreign_key text := TG_ARGV[1];
    -- the type the column has, without naming its length: what the aggregate
    -- answers is what the column stores
    maintained  text[];
BEGIN
    -- the array belongs to the database, so a value which differs from the stored
    -- one is not a change but a write which did not read the column: answered from
    -- the relation, never from the write. A writer which carries the stored value
    -- is the common case and is not asked for the aggregate.
    IF NEW.keywords_list IS DISTINCT FROM OLD.keywords_list THEN
        EXECUTE format(
            'SELECT (SELECT COALESCE(array_agg(DISTINCT keyword.keyword ORDER BY keyword.keyword),
                             ''{}''::text[])
                 FROM %2$I AS relation
                 JOIN registry_keyword AS keyword ON keyword.id = relation.keyword_id
                WHERE relation.%3$I = record.id
                  AND btrim(keyword.keyword) <> '') FROM %1$I AS record WHERE record.id = $1',
            TG_TABLE_NAME, relation, foreign_key
        ) INTO maintained USING NEW.id;

        NEW.keywords_list := maintained;
    END IF;

    RETURN NEW;
END;
$$;
"""

LEGACY_RENAME_FUNCTION = """
CREATE OR REPLACE FUNCTION registry_sync_keyword_rename_to_metadatarecords()
    RETURNS TRIGGER
    LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.keyword IS DISTINCT FROM NEW.keyword THEN
        UPDATE registry_datasetmetadatarecord AS record
           SET keywords_list = (SELECT COALESCE(array_agg(DISTINCT keyword.keyword ORDER BY keyword.keyword),
                             '{}'::text[])
                 FROM registry_datasetmetadatarecord_keywords AS relation
                 JOIN registry_keyword AS keyword ON keyword.id = relation.keyword_id
                WHERE relation.datasetmetadatarecord_id = record.id
                  AND btrim(keyword.keyword) <> '');

        UPDATE registry_servicemetadatarecord AS record
           SET keywords_list = (SELECT COALESCE(array_agg(DISTINCT keyword.keyword ORDER BY keyword.keyword),
                             '{}'::text[])
                 FROM registry_servicemetadatarecord_keywords AS relation
                 JOIN registry_keyword AS keyword ON keyword.id = relation.keyword_id
                WHERE relation.servicemetadatarecord_id = record.id
                  AND btrim(keyword.keyword) <> '');

        UPDATE registry_applicationmetadatarecord AS record
           SET keywords_list = (SELECT COALESCE(array_agg(DISTINCT keyword.keyword ORDER BY keyword.keyword),
                             '{}'::text[])
                 FROM registry_applicationmetadatarecord_keywords AS relation
                 JOIN registry_keyword AS keyword ON keyword.id = relation.keyword_id
                WHERE relation.applicationmetadatarecord_id = record.id
                  AND btrim(keyword.keyword) <> '');

    END IF;

    RETURN NULL;
END;
$$;
"""


def _legacy_create_statements():
    """Every legacy function and trigger, the state the way back installed."""
    create = [LEGACY_SYNC_FUNCTION, LEGACY_KEEP_FUNCTION,
              LEGACY_RENAME_FUNCTION]
    for record, relation, foreign_key in (
            ('registry_datasetmetadatarecord',
             'registry_datasetmetadatarecord_keywords',
             'datasetmetadatarecord_id'),
            ('registry_servicemetadatarecord',
             'registry_servicemetadatarecord_keywords',
             'servicemetadatarecord_id'),
            ('registry_applicationmetadatarecord',
             'registry_applicationmetadatarecord_keywords',
             'applicationmetadatarecord_id')):
        create.append("""
CREATE TRIGGER {relation}_keywords_list_sync
    AFTER INSERT OR UPDATE OR DELETE ON {relation}
    FOR EACH ROW
    EXECUTE FUNCTION registry_sync_metadatarecord_keywords_list('{record}', '{foreign_key}');
""".format(record=record, relation=relation, foreign_key=foreign_key))
        create.append("""
CREATE TRIGGER {record}_keywords_list_keep
    BEFORE UPDATE ON {record}
    FOR EACH ROW
    EXECUTE FUNCTION registry_keep_metadatarecord_keywords_list('{relation}', '{foreign_key}');
""".format(record=record, relation=relation, foreign_key=foreign_key))
    create.append("""
CREATE TRIGGER registry_keyword_sync_to_metadatarecords
    AFTER UPDATE OF keyword ON registry_keyword
    FOR EACH ROW
    EXECUTE FUNCTION registry_sync_keyword_rename_to_metadatarecords();
""")
    return create


def _legacy_drop_statements():
    """The removal of every legacy object, the way forward out of them."""
    drop = []
    for record, relation, _foreign_key in (
            ('registry_datasetmetadatarecord',
             'registry_datasetmetadatarecord_keywords', None),
            ('registry_servicemetadatarecord',
             'registry_servicemetadatarecord_keywords', None),
            ('registry_applicationmetadatarecord',
             'registry_applicationmetadatarecord_keywords', None)):
        drop.append('DROP TRIGGER IF EXISTS %s ON %s;'
                    % (relation + '_keywords_list_sync', relation))
        drop.append('DROP TRIGGER IF EXISTS %s ON %s;'
                    % (record + '_keywords_list_keep', record))
    drop.append('DROP TRIGGER IF EXISTS registry_keyword_sync_to_metadatarecords'
                ' ON registry_keyword;')
    for function in ('registry_sync_metadatarecord_keywords_list()',
                     'registry_keep_metadatarecord_keywords_list()',
                     'registry_sync_keyword_rename_to_metadatarecords()'):
        drop.append('DROP FUNCTION IF EXISTS %s;' % function)
    return drop


LEGACY_CREATE_SQL = _legacy_create_statements()
LEGACY_DROP_SQL = _legacy_drop_statements()


def run_schema_sql(*statements):
    """Statements as a migration ran them: pending checks first.

    The foreign keys of a database built by migrations come up ``DEFERRABLE
    INITIALLY DEFERRED``; what the transaction boundary of a migration node
    answered on the old chain is forced here before any DDL of the rebuilt
    intermediate state touches a table.
    """
    with connection.cursor() as cursor:
        cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')
        for statement in statements:
            cursor.execute(statement)


class KeywordMigrationTest(TestCase):
    """Blank keywords go away, and then the schema refuses them.

    The rebuilt chain (#1850) creates the keyword table already constrained,
    so the executor has no node left to travel to which allowed the blanks;
    the class builds that state itself instead. It takes the check constraint
    off the table -- the way the old chain found it before the blanks were
    removed and the constraint which refuses them was tightened -- writes the
    blanks and their links, and runs the removal statements of the fix over
    them. The constraint which comes back is the definition the catalog
    answers, which is the definition of ``0001_initial``: a chain which lost
    it goes red at the reading, one which weakened it goes red at the refusal
    of the next blank.

    ``TestCase`` rather than ``TransactionTestCase``: nothing migrates any
    more -- the intermediate state is plain sql inside the transaction of the
    test, which postgres rolls back with it. What the case still prepares by
    itself is the keyword table, because the assertion below compares it as a
    whole and cannot know what a worker had left behind.
    """

    # the same test postgres applies when it refuses a blank, spelled as a
    # Django Q. Named for what it selects, because the removal states its
    # condition the other way round: it removes what `NOT (keyword ~
    # <non-whitespace>)` matches, so a keyword is blank when this Q does NOT
    # match it. Reading it the other way round is the easiest mistake in this
    # file -- a name like "blank" over a condition which selects every keyword
    # that HAS content makes the assertion below report a content-bearing
    # keyword as a survivor of the removal.
    HAS_CONTENT = Q(keyword__regex='\\S') & ~Q(keyword__isnull=True)

    # the fully blank contact; a fixture of the application creates this shape
    # too, and the twelve-column unique constraint of #1215 lets at most one
    # of them exist
    BLANK_CONTACT = dict(name='', person_name='', email='', phone='', facsimile='',
                         city='', postal_code='', address_type='', address='',
                         state_or_province='', country='')

    def non_empty_constraint_definition(self):
        """The constraint of the chain, read rather than retyped.

        Its existence and its condition are already a witness: the rebuilt
        ``0001_initial`` owes the check which refuses blanks, comparing the
        keyword against the non-whitespace pattern and against null.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_get_constraintdef(con.oid)"
                " FROM pg_constraint con"
                " JOIN pg_class rel ON rel.oid = con.conrelid"
                " WHERE rel.relname = 'registry_keyword'"
                " AND con.conname = %s", [NON_EMPTY_CONSTRAINT])
            row = cursor.fetchone()
        self.assertIsNotNone(
            row, 'the rebuilt 0001_initial did not create the non-blank '
                 'keyword constraint %s' % NON_EMPTY_CONSTRAINT)
        definition = row[0]
        self.assertIn('~', definition,
                      'the keyword constraint %s does not compare the keyword '
                      'against the non-whitespace pattern' % NON_EMPTY_CONSTRAINT)
        self.assertIn('IS NOT NULL', definition,
                      'the keyword constraint %s does not refuse null'
                      % NON_EMPTY_CONSTRAINT)
        return definition

    def prepare_database(self):
        """Puts the tables this test is about into the state its assertion assumes.

        The assertion compares the whole keyword table, which holds only while
        no other case has loaded keywords before. Establishing it instead of
        hoping for it is what makes the run deterministic: ``keyword`` is
        unique, so a foreign keyword can neither exist next to this test's own
        rows nor be skipped over by an assertion. The links of the removed
        keywords go with them by the cascade of the relation tables.

        The blank ``MetadataContact`` is the one state this method does not
        clear: it reuses it instead. A blank contact can be what a service's
        restricted ``service_contact`` and ``metadata_contact`` point at -- and
        the assertion below is indifferent to which blank contact its service
        carries, so an existing one is exactly as usable as a freshly created
        one.

        Only the keyword table is touched. Nothing else in the database is
        considered, because nothing else is asserted about.
        """
        blank_contacts = MetadataContact.objects.filter(**self.BLANK_CONTACT)
        # Recorded because this case answered itself oppositely on two runs
        # and the failure text named neither of the two states it had started
        # from; naming them in the failure is the cheapest way for the next
        # occurrence to explain itself.
        self.was = {'keywords': Keyword.objects.count(),
                    'blank_contacts': blank_contacts.count()}
        Keyword.objects.all().delete()

    def test_removes_blank_keywords_and_links_before_adding_constraint(self):
        definition = self.non_empty_constraint_definition()
        run_schema_sql(
            'ALTER TABLE "registry_keyword" DROP CONSTRAINT "%s"'
            % NON_EMPTY_CONSTRAINT)

        # the schema which allowed the blanks: what the old chain stood in
        # when the removal node ran, built by taking the constraint away
        self.prepare_database()
        # The twelve-column unique constraint of #1215 lets at most one fully
        # blank contact exist, and one can exist in the state this case starts
        # from. That row may be under a restricted reference, so it cannot be
        # deleted to make room for a new one - it is used, and a new one is
        # created only while nothing blank is there.
        contact = (MetadataContact.objects.filter(**self.BLANK_CONTACT).first()
                   or MetadataContact.objects.create())
        service = WebMapService.objects.create(
            title='Keyword blank wms', version=1, origin=1,
            service_url='https://example.com/wms',
            service_contact=contact, metadata_contact=contact,
        )
        keywords = [Keyword.objects.create(keyword=value)
                    for value in ('', ' \t\n', '  valid  ')]
        service.keywords.set(keywords)

        # the upgrade statements over them: blanks and their links first, the
        # constraint of the chain again at the end
        run_schema_sql(*REMOVE_BLANK_KEYWORDS)
        run_schema_sql(
            'ALTER TABLE "registry_keyword" ADD CONSTRAINT "%s" %s'
            % (NON_EMPTY_CONSTRAINT, definition))

        service = WebMapService.objects.get(pk=service.pk)
        self.assertFalse(Keyword.objects.filter(~self.HAS_CONTENT).exists(),
                         f'a keyword without content survived the removal which '
                         f'exists to remove it (started from {self.was})')
        self.assertEqual(
            list(Keyword.objects.values_list('keyword', flat=True)),
            ['  valid  '])
        self.assertEqual(list(service.keywords.values_list('keyword', flat=True)),
                         ['  valid  '])
        with self.assertRaises(IntegrityError), transaction.atomic():
            Keyword.objects.create(keyword=' ')


class KeywordLengthMigrationTest(TestCase):
    """The length of a keyword is a decision of the storage, not of the catalogue.

    A German catalogue joined the plan names of one dataset into a single 347
    character ``gmd:keyword``, which is what ISO 19115 asks for and what a
    ``varchar(300)`` refuses: the insert raised ``StringDataRightTruncation``,
    the import task read that as a record error and the records of the file
    never entered the registry (#894). The keyword column and the keywords
    array of the records are text since the widening, and the array is the
    column the stored vector of a record reads.

    The rebuilt chain (#1850) knows only the widened schema, so there is no
    node left below which the narrow column stands. The class builds it
    itself: it takes the rename trigger off the keyword table (naming a column
    in ``UPDATE OF`` makes the trigger depend on its type), takes the stored
    vector and its index off the two record tables (a generated column is what
    postgres refuses to leave reading while the array changes) and narrows the
    column and the arrays to ``varchar(300)`` -- the statements of the widening
    node read backwards. The way forward runs them in the other direction,
    over stored rows, and what is asked of it is what was asked before: the
    vector which came back with the array answers the word at the end of the
    long keyword, and the recreated rename trigger still reaches the records.
    """

    # the keyword of the report, with a plan named at its end which the title of the
    # record carrying it does not name: the tail is what a narrow column loses
    LONG_KEYWORD = ('Flächennutzungsplan WN '
                    + 'Remshalden,Flächennutzungsplan WN ' * 12 + 'Rudersberg')

    def vector_objects(self, table):
        """The stored vector of a record table and its index, as the chain made them.

        Read from the catalog rather than retyped, so that what comes back on
        the way forward is what ``0001_initial`` created -- and so a chain
        which lost the stored vector goes red here, before the narrowing ever
        hides the question.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT format_type(a.atttypid, a.atttypmod),"
                " pg_get_expr(d.adbin, d.adrelid), a.attgenerated"
                " FROM pg_attribute a"
                " LEFT JOIN pg_attrdef d"
                " ON d.adrelid = a.attrelid AND d.adnum = a.attnum"
                " WHERE a.attrelid = %s::regclass"
                " AND a.attname = 'search_vector' AND NOT a.attisdropped",
                [table])
            row = cursor.fetchone()
            self.assertIsNotNone(
                row, 'the rebuilt chain did not create the stored search '
                     'vector of %s' % table)
            column_type, expression, generated = row
            self.assertEqual(
                generated, 's',
                'the search_vector of %s is not a stored generated column, '
                'which is the dependency the widening had to work around' % table)
            cursor.execute(
                "SELECT indexname, indexdef FROM pg_indexes"
                " WHERE tablename = %s AND indexdef ILIKE %s",
                [table, '%search_vector%'])
            indexes = cursor.fetchall()
            self.assertTrue(
                indexes, 'no index answers the search_vector of %s' % table)
        return {'type': column_type, 'expression': expression,
                'indexes': indexes}

    def _resize_keyword_schema(self, keyword_type, array_type):
        """The widening node in one direction, statement for statement.

        The objects which read the columns go first -- the trigger naming the
        keyword column in its ``UPDATE OF`` (a trigger which names a column
        depends on its type) and the stored vector with its index (postgres
        refuses to change the element type of an array while a generated
        column reads it) -- and come back last, over rows which are already
        stored. The vector which comes back is the one the chain created, read
        from the catalog rather than retyped; the trigger which comes back is
        recompiled by the package from ``registry/triggers.py``.
        """
        statements = []
        for table in WIDENED_RECORD_TABLES:
            for index_name, _definition in self.vectors[table]['indexes']:
                statements.append('DROP INDEX IF EXISTS "%s";' % index_name)
            statements.append(
                'ALTER TABLE %s DROP COLUMN search_vector;' % table)
        statements.append(
            'ALTER TABLE registry_keyword ALTER COLUMN keyword TYPE %s;'
            % keyword_type)
        for table in WIDENED_RECORD_TABLES:
            statements.append(
                'ALTER TABLE %s ALTER COLUMN keywords_list TYPE %s;'
                % (table, array_type))
        for table in WIDENED_RECORD_TABLES:
            vector = self.vectors[table]
            statements.append(
                'ALTER TABLE %s ADD COLUMN search_vector %s'
                ' GENERATED ALWAYS AS (%s) STORED;'
                % (table, vector['type'], vector['expression']))
            statements.extend(
                definition + ';' for _name, definition in vector['indexes'])
        run_schema_sql('SET CONSTRAINTS ALL IMMEDIATE')
        uninstall_triggers(KEYWORD_RENAME_TRIGGER_URI)
        run_schema_sql(*statements)
        install_triggers(KEYWORD_RENAME_TRIGGER_URI)

    def narrow_keyword_schema(self):
        """The schema before the widening, rebuilt statement by statement.

        The keyword column and the keywords arrays to ``varchar(300)`` -- and
        the stored vector standing again over the narrow array afterwards,
        which is the state the old chain's records were written into before
        the widening came.
        """
        # the keyword table belongs to this test alone: the narrow column is
        # rebuilt over whatever a crashed run had left in it
        Keyword.objects.all().delete()
        self.vectors = {table: self.vector_objects(table)
                        for table in WIDENED_RECORD_TABLES}
        self._resize_keyword_schema('varchar(300)', 'varchar(300)[]')

    def widen_keyword_schema(self):
        """The way forward of the widening node, over stored rows.

        The arrays and the column widened to text with the vector and the
        rename trigger back as the chain answers them -- the statement for
        statement partner of the way back above.
        """
        self._resize_keyword_schema('text', 'text[]')

    def test_the_narrow_column_is_what_refused_the_keyword(self):
        """The old schema is kept as the failure, so that the fix has a witness."""
        self.narrow_keyword_schema()
        self.assertGreater(len(self.LONG_KEYWORD), 300)
        with self.assertRaises(DataError), transaction.atomic():
            Keyword.objects.create(keyword=self.LONG_KEYWORD)

    def test_the_widened_schema_keeps_the_keyword_and_the_words_of_it(self):
        self.narrow_keyword_schema()
        contact = MetadataContact.objects.create(name='Contact of the widening')
        record_id = DatasetMetadataRecord.objects.create(
            metadata_contact=contact, dataset_contact=contact,
            title='Flächennutzungsplan Remshalden').pk

        self.widen_keyword_schema()

        keywords = [Keyword.objects.create(keyword='Boden'),
                    Keyword.objects.create(keyword=self.LONG_KEYWORD)]
        DatasetMetadataRecord.objects.get(pk=record_id).keywords.set(keywords)

        self.assertEqual(
            sorted(DatasetMetadataRecord.objects.values_list(
                'keywords_list', flat=True).get(pk=record_id)),
            sorted(keyword.keyword for keyword in keywords),
            'the array of the record answers another text than the keywords '
            'relation of the very same record')
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT search_vector @@ plainto_tsquery(%s, %s)'
                ' FROM registry_datasetmetadatarecord WHERE id = %s',
                [TEXT_CONFIGURATION_NAME, 'Rudersberg', record_id])
            self.assertTrue(
                cursor.fetchone()[0],
                'the vector which came back with the widened array does not '
                'answer the word at the end of the keyword it was built from')

    def test_the_rename_of_a_keyword_still_reaches_the_records(self):
        """The trigger which had to leave with the column comes back firing.

        The rename trigger of the keyword table is declared ``AFTER UPDATE OF
        keyword``, which makes it depend on the type of that column: postgres
        refuses to widen the column while the trigger exists, so the widening
        took it down and brought it back. A recreated trigger which does not
        fire is the failure this keeps -- it would go unnoticed by every other
        test: the array of a record would keep naming the keyword it used to
        carry while its relation answers another text, and the record would
        stay findable by a word nobody uses anymore.
        """
        self.narrow_keyword_schema()
        contact = MetadataContact.objects.create(name='Contact of the rename')
        record_id = DatasetMetadataRecord.objects.create(
            metadata_contact=contact, dataset_contact=contact,
            title='Bauleitplan').pk

        self.widen_keyword_schema()

        keyword = Keyword.objects.create(keyword='Flächennutzungsplan WN Remshalden')
        DatasetMetadataRecord.objects.get(pk=record_id).keywords.set([keyword])

        Keyword.objects.filter(pk=keyword.pk).update(keyword=self.LONG_KEYWORD)

        self.assertEqual(
            DatasetMetadataRecord.objects.values_list(
                'keywords_list', flat=True).get(pk=record_id),
            [self.LONG_KEYWORD],
            'the rename trigger which the widening recreated does not reach '
            'the array of the record')
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT search_vector @@ plainto_tsquery(%s, %s)'
                ' FROM registry_datasetmetadatarecord WHERE id = %s',
                [TEXT_CONFIGURATION_NAME, 'Rudersberg', record_id])
            self.assertTrue(
                cursor.fetchone()[0],
                'the renamed keyword does not reach the vector of the record '
                'which the rename of it rewrote')


class KeywordTriggerTransferTest(TestCase):
    """The keyword maintenance is managed by pgtrigger -- in both directions.

    The transfer of #1009 moved the sync, keep and rename rules from hand
    written sql to declarative package objects. The rebuilt chain (#1850)
    installs the package objects with the schema and never had a node at which
    the legacy objects stood, so the executor cannot travel to either side
    any more; the class travels them itself, statement by statement the way
    the transfer node did:

    *   the way back: the package objects uninstalled and the legacy objects
        of #1075's shape created -- the functions and triggers the reverse of
        the transfer installed, carried verbatim into this file;
    *   the way forward: the legacy objects dropped and the package objects
        installed by the package itself, which recompiles them from the
        declarations in ``registry/triggers.py``.

    Both directions are asked because the harvesting writers run against
    these triggers in production and a deployment must be able to roll back.
    The witness stayed the catalog: the seven legacy objects standing under
    their legacy names with the bodies of the widened element type -- and the
    seven package objects standing over no legacy function at all.
    """

    #: the objects as the old chain named them
    LEGACY = sorted([
        'registry_datasetmetadatarecord_keywords_keywords_list_sync',
        'registry_servicemetadatarecord_keywords_keywords_list_sync',
        'registry_applicationmetadatarecord_keywords_keywords_list_sync',
        'registry_datasetmetadatarecord_keywords_list_keep',
        'registry_servicemetadatarecord_keywords_list_keep',
        'registry_applicationmetadatarecord_keywords_list_keep',
        'registry_keyword_sync_to_metadatarecords',
    ])

    def keyword_triggers(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal"
                " AND (tgname LIKE '%keywords\\_list\\_sync%'"
                " OR tgname LIKE '%keywords\\_list\\_keep%'"
                " OR tgname LIKE '%keyword\\_sync\\_to\\_metadatarecords%')"
                " ORDER BY tgname")
            return [row[0] for row in cursor.fetchall()]

    def keyword_bodies(self):
        """The stored sources of the three legacy functions, by name"""
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT proname, prosrc FROM pg_proc WHERE proname IN"
                " ('registry_sync_metadatarecord_keywords_list',"
                " 'registry_keep_metadatarecord_keywords_list',"
                " 'registry_sync_keyword_rename_to_metadatarecords')")
            return dict(cursor.fetchall())

    def reverse_transfer(self):
        """The way back of the transfer node, run against the migrated schema."""
        run_schema_sql('SET CONSTRAINTS ALL IMMEDIATE')
        uninstall_triggers(*KEYWORD_TRIGGER_URIS)
        run_schema_sql(*LEGACY_CREATE_SQL)

    def forward_transfer(self):
        """The way forward of the transfer node, over the legacy objects."""
        run_schema_sql(*LEGACY_DROP_SQL)
        run_schema_sql('SET CONSTRAINTS ALL IMMEDIATE')
        install_triggers(*KEYWORD_TRIGGER_URIS)

    def assert_package_objects(self):
        """The end state of the rebuilt chain: the package objects, no legacy body."""
        installed = self.keyword_triggers()
        self.assertEqual(len(installed), 7, installed)
        self.assertTrue(all(name.startswith('pgtrigger_') for name in installed),
                        installed)
        self.assertEqual(self.keyword_bodies(), {})

    def test_the_transfer_swaps_the_objects_in_both_directions(self):
        # what the rebuilt chain leaves behind its creation node: the package
        # objects installed and no legacy function anywhere
        self.assert_package_objects()

        # the way back: the state the legacy objects left behind, installed by
        # the very statements the reverse of the transfer carried
        self.reverse_transfer()
        self.assertEqual(self.keyword_triggers(), self.LEGACY)
        bodies = self.keyword_bodies()
        self.assertEqual(len(bodies), 3, sorted(bodies))
        for name, body in bodies.items():
            self.assertNotIn(
                'varchar(300)', body,
                'the way back did not restore the widened body of %s' % name)

        # the way forward: the legacy objects gone and the package objects
        # recompiled from what the chain declares
        self.forward_transfer()
        self.assert_package_objects()


class KeywordThroughModelMigrationTest(TransactionTestCase):
    """Taking ownership of the M2M tables preserves links and installed triggers.

    Making the keywords relations of the three record types explicit through
    models was, in the old chain, an operation of the migration state alone:
    its node owed -- in both directions -- that the physical tables are never
    touched. The rebuild (#1850) created these tables already explicit, so no
    pair of node names is left to travel between; what the executor travels
    here is the rebuilt chain itself, back to the deepest node it can be
    walked to -- its successor loads the initial data with a forward-only
    ``RunPython``, which by Django's own rule stops any travel below it -- and
    forward to its leaf, over stored records, links and installed triggers.
    The ownership node's debt is the assertion of every stop: the tables stand
    and are not replaced (OIDs detect table replacement even when names and
    rows were copied), their triggers answer the very definitions, the links
    keep their physical ids, and the installed triggers keep the array of
    every record honest.
    """

    record_types = (
        ('DatasetMetadataRecord', 'dataset_contact'),
        ('ServiceMetadataRecord', None),
        ('ApplicationMetadataRecord', 'application_contact'),
    )

    def restore_schema(self):
        # leave the schema at the tip whatever the test did -- this is the one
        # class of the file whose statements commit
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def table_objects(self):
        """OIDs detect table replacement even when names and rows were copied."""
        tables = [f'registry_{name.lower()}_keywords' for name, _ in self.record_types]
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT c.relname, c.oid, t.tgname, pg_get_triggerdef(t.oid)'
                ' FROM pg_class c JOIN pg_trigger t ON t.tgrelid = c.oid'
                ' WHERE c.relname = ANY(%s) AND NOT t.tgisinternal'
                ' ORDER BY c.relname, t.tgname', [tables])
            return cursor.fetchall()

    def test_links_and_triggers_survive_forward_and_reverse(self):
        self.addCleanup(self.restore_schema)
        executor = MigrationExecutor(connection)
        graph = executor.loader.graph
        self.assertIn(SEED, graph.forwards_plan(SEED))
        tip = graph.leaf_nodes()
        # the travel between the deepest node the rebuilt chain can be walked
        # back to and its leaf: every app at its leaf, the registry at the
        # seed node -- below it the chain is forward-only by design
        below = [node for node in tip if node[0] != 'registry'] + [SEED]

        apps = executor.loader.project_state(tip).apps
        Contact = apps.get_model('registry', 'MetadataContact')
        Keyword = apps.get_model('registry', 'Keyword')
        contact = Contact.objects.create(name='Keyword through migration contact')
        keyword = Keyword.objects.create(keyword='through migration keyword')
        extra = Keyword.objects.create(keyword='through migration extra keyword')
        records = []
        for name, contact_field in self.record_types:
            Record = apps.get_model('registry', name)
            values = {'metadata_contact': contact, 'title': 'Through migration'}
            if contact_field:
                values[contact_field] = contact
            record = Record.objects.create(**values)
            record.keywords.add(keyword)
            records.append((name, record.pk, record.keywords.through.objects.get(
                keyword=keyword).pk))
        before = self.table_objects()
        self.assertEqual(len(before), 3)

        # Both directions of the travel must keep the physical tables and
        # their original link IDs.
        for target in (below, tip):
            executor = MigrationExecutor(connection)
            executor.migrate(target)
            state_apps = executor.loader.project_state(target).apps
            self.assertEqual(self.table_objects(), before)
            for name, record_id, link_id in records:
                with self.subTest(target=target, record=name):
                    Record = state_apps.get_model('registry', name)
                    record = Record.objects.get(pk=record_id)
                    self.assertEqual(
                        record.keywords.through.objects.get(
                            keyword_id=keyword.pk).pk,
                        link_id)
                    self.assertEqual(
                        list(record.keywords.values_list('pk', flat=True)),
                        [keyword.pk])
                    self.assertEqual(record.keywords_list, [keyword.keyword])
                    # A migration which preserves the objects must preserve
                    # their effect too.
                    record.keywords.add(extra.pk)
                    record.refresh_from_db()
                    self.assertEqual(record.keywords_list,
                                     sorted([keyword.keyword, extra.keyword]))
                    record.keywords.remove(extra.pk)
                    record.refresh_from_db()
                    self.assertEqual(record.keywords_list, [keyword.keyword])
