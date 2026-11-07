from django.db import DataError, IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from registry.expressions.search import TEXT_CONFIGURATION_NAME


class KeywordMigrationTest(TransactionTestCase):
    migrate_from = [('registry', '0014_catalogueservicemonitoringrun_background_process_and_more')]
    migrate_to = [('registry', '0016_enforce_non_blank_keywords')]

    def test_removes_blank_keywords_and_links_before_adding_constraint(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        self.addCleanup(self.restore_schema)
        apps = executor.loader.project_state(self.migrate_from).apps
        Keyword = apps.get_model('registry', 'Keyword')
        Contact = apps.get_model('registry', 'MetadataContact')
        Service = apps.get_model('registry', 'WebMapService')
        contact = Contact.objects.create()
        service = Service.objects.create(
            version=1, service_url='https://example.com/wms',
            service_contact=contact, metadata_contact=contact,
        )
        keywords = [Keyword.objects.create(keyword=value) for value in ('', ' \t\n', '  valid  ')]
        service.keywords.set(keywords)

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        apps = executor.loader.project_state(self.migrate_to).apps
        Keyword = apps.get_model('registry', 'Keyword')
        Service = apps.get_model('registry', 'WebMapService')
        service = Service.objects.get(pk=service.pk)
        self.assertEqual(list(Keyword.objects.values_list('keyword', flat=True)), ['  valid  '])
        self.assertEqual(list(service.keywords.values_list('keyword', flat=True)), ['  valid  '])
        with self.assertRaises(IntegrityError), transaction.atomic():
            Keyword.objects.create(keyword=' ')

    def restore_schema(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())


class KeywordLengthMigrationTest(TransactionTestCase):
    """The length of a keyword is a decision of the storage, not of the catalogue.

    A German catalogue joined the plan names of one dataset into a single 347
    character ``gmd:keyword``, which is what ISO 19115 asks for and what a
    ``varchar(300)`` refuses: the insert raised ``StringDataRightTruncation``, the
    import task read that as a record error and the records of the file never entered
    the registry (#894). The keyword column and the keywords array of the records are
    text since this migration, and the array is the column the stored vector of a
    record reads - so what a record is still found by after the vector had to go and
    come back is what these tests assert against the schema of each revision.
    """

    migrate_from = [('registry', '0026_drops_the_statistics_materialized_views')]
    migrate_to = [('registry', '0028_a_keyword_is_as_long_as_its_catalogue_says')]

    # the keyword of the report, with a plan named at its end which the title of the
    # record carrying it does not name: the tail is what a narrow column loses
    LONG_KEYWORD = ('Flächennutzungsplan WN '
                    + 'Remshalden,Flächennutzungsplan WN ' * 12 + 'Rudersberg')

    def setUp(self):
        super().setUp()
        self.addCleanup(self.restore_schema)

    def test_the_narrow_column_is_what_refused_the_keyword(self):
        """The old schema is kept as the failure, so that the fix has a witness."""
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        apps = executor.loader.project_state(self.migrate_from).apps
        Keyword = apps.get_model('registry', 'Keyword')
        self.assertGreater(len(self.LONG_KEYWORD), 300)
        with self.assertRaises(DataError), transaction.atomic():
            Keyword.objects.create(keyword=self.LONG_KEYWORD)

    def test_the_widened_schema_keeps_the_keyword_and_the_words_of_it(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        apps = executor.loader.project_state(self.migrate_from).apps
        Contact = apps.get_model('registry', 'MetadataContact')
        Record = apps.get_model('registry', 'DatasetMetadataRecord')
        contact = Contact.objects.create(name='Contact of the widening')
        record_id = Record.objects.create(
            metadata_contact=contact, dataset_contact=contact,
            title='Flächennutzungsplan Remshalden').pk

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        apps = executor.loader.project_state(self.migrate_to).apps
        Keyword = apps.get_model('registry', 'Keyword')
        Record = apps.get_model('registry', 'DatasetMetadataRecord')
        record = Record.objects.get(pk=record_id)

        keywords = [Keyword.objects.create(keyword='Boden'),
                    Keyword.objects.create(keyword=self.LONG_KEYWORD)]
        record.keywords.set(keywords)

        self.assertEqual(
            sorted(Record.objects.values_list('keywords_list', flat=True).get(
                pk=record_id)),
            sorted(keyword.keyword for keyword in keywords),
            'the array of the record answers another text than the keywords relation '
            'of the very same record')
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT search_vector @@ plainto_tsquery(%s, %s)'
                ' FROM registry_datasetmetadatarecord WHERE id = %s',
                [TEXT_CONFIGURATION_NAME, 'Rudersberg', record_id])
            self.assertTrue(
                cursor.fetchone()[0],
                'the vector which came back with the widened array does not answer '
                'the word at the end of the keyword it was built from')

    def test_the_rename_of_a_keyword_still_reaches_the_records(self):
        """The trigger which had to leave with the column comes back firing.

        The rename trigger of ``0021`` is declared ``AFTER UPDATE OF keyword``, which
        makes it depend on the type of that column: postgres refuses to widen the
        column while the trigger exists, so the migration drops it and creates it
        again. A recreated trigger which does not fire is the failure this keeps - it
        would go unnoticed by every other test: the array of a record would keep
        naming the keyword it used to carry while its relation answers another text,
        and the record would stay findable by a word nobody uses anymore.
        """
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        apps = executor.loader.project_state(self.migrate_from).apps
        Contact = apps.get_model('registry', 'MetadataContact')
        Record = apps.get_model('registry', 'DatasetMetadataRecord')
        contact = Contact.objects.create(name='Contact of the rename')
        record_id = Record.objects.create(
            metadata_contact=contact, dataset_contact=contact,
            title='Bauleitplan').pk

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        apps = executor.loader.project_state(self.migrate_to).apps
        Keyword = apps.get_model('registry', 'Keyword')
        Record = apps.get_model('registry', 'DatasetMetadataRecord')
        keyword = Keyword.objects.create(keyword='Flächennutzungsplan WN Remshalden')
        Record.objects.get(pk=record_id).keywords.set([keyword])

        Keyword.objects.filter(pk=keyword.pk).update(keyword=self.LONG_KEYWORD)

        self.assertEqual(
            Record.objects.values_list('keywords_list', flat=True).get(pk=record_id),
            [self.LONG_KEYWORD],
            'the rename trigger which the migration recreated does not reach the '
            'array of the record')
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT search_vector @@ plainto_tsquery(%s, %s)'
                ' FROM registry_datasetmetadatarecord WHERE id = %s',
                [TEXT_CONFIGURATION_NAME, 'Rudersberg', record_id])
            self.assertTrue(
                cursor.fetchone()[0],
                'the renamed keyword does not reach the vector of the record which '
                'the rename of it rewrote')

    def restore_schema(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())


class KeywordTriggerTransferTest(TransactionTestCase):
    """0038 hands the keyword maintenance from hand written sql to pgtrigger.

    Forward the legacy functions and triggers must be gone and the package
    objects installed; backwards the very state 0035 left behind must return,
    which since #1075 means the legacy bodies with the empty array of the
    widened element type. Both directions are asked because the harvesting
    writers run against these triggers in production and a deployment must be
    able to roll back.
    """

    #: the objects as 0021, 0024 and 0033 named them
    LEGACY = sorted([
        'registry_datasetmetadatarecord_keywords_keywords_list_sync',
        'registry_servicemetadatarecord_keywords_keywords_list_sync',
        'registry_applicationmetadatarecord_keywords_keywords_list_sync',
        'registry_datasetmetadatarecord_keywords_list_keep',
        'registry_servicemetadatarecord_keywords_list_keep',
        'registry_applicationmetadatarecord_keywords_list_keep',
        'registry_keyword_sync_to_metadatarecords',
    ])

    def tearDown(self):
        # leave the schema at the tip whatever the test did
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

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

    def migrate_to(self, targets):
        MigrationExecutor(connection).migrate(targets)

    def test_the_transfer_swaps_the_objects_in_both_directions(self):
        self.migrate_to([
            ('registry',
             '0035_a_too_long_keyword_does_not_take_a_record_down')])
        self.assertEqual(self.keyword_triggers(), self.LEGACY)
        bodies = self.keyword_bodies()
        self.assertEqual(len(bodies), 3, sorted(bodies))
        for name, body in bodies.items():
            self.assertNotIn(
                'varchar(300)', body,
                'reversing 0038 did not restore the body 0035 left on %s' % name)

        self.migrate_to([
            ('registry', '0038_the_keyword_maintenance_is_managed_by_pgtrigger')])
        installed = self.keyword_triggers()
        self.assertEqual(len(installed), 7, installed)
        self.assertTrue(all(name.startswith('pgtrigger_') for name in installed),
                        installed)
