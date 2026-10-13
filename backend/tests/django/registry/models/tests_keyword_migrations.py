from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


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
