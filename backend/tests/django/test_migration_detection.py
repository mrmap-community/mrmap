"""Django's standard migration commands detect the registered triggers.

The retired pgviews app previously shadowed pgtrigger's command integration.
Historical view operations still load from the dependency without activating
that app or requiring project-specific commands.
"""

from types import SimpleNamespace

from django.apps import apps
from django.core.management import get_commands, load_command_class
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.state import ProjectState
from django.test import SimpleTestCase
from pgtrigger import Insert, Protect
from pgtrigger.migrations import AddTrigger, MigrationAutodetectorMixin
from pgtrigger.registry import registered


class CommandLookupTest(SimpleTestCase):
    """The standard commands use pgtrigger's migration integration."""

    def test_the_standard_commands_win_the_lookup(self):
        self.assertEqual(get_commands().get('makemigrations'), 'django.core')
        self.assertEqual(get_commands().get('migrate'), 'django.core')

    def test_both_commands_share_the_trigger_autodetector(self):
        makemigrations = load_command_class('django.core', 'makemigrations')
        migrate = load_command_class('django.core', 'migrate')
        self.assertIs(migrate.autodetector, makemigrations.autodetector)
        self.assertTrue(issubclass(makemigrations.autodetector,
                                   MigrationAutodetectorMixin))

    def test_historical_view_migrations_load_without_the_retired_app(self):
        self.assertFalse(apps.is_installed('django_pgviews'))
        loader = MigrationLoader(None)
        old_state = loader.project_state([('registry', '0017_auto_20261022_1331')])
        self.assertIn(('registry', 'servicealertview'), old_state.models)
        self.assertNotIn(('registry', 'servicealertview'), loader.project_state().models)


class TriggerRegistrationTest(SimpleTestCase):
    """The keyword maintenance is registered on the models when ready()."""

    def test_other_metadata_keeps_its_automatic_keywords_relations(self):
        for name in ('WebMapService', 'WebFeatureService', 'CatalogueService',
                     'Layer', 'FeatureType'):
            with self.subTest(model=name):
                model = apps.get_model('registry', name)
                self.assertTrue(model.keywords.through._meta.auto_created)

    def test_registered_sql_matches_the_existing_migrations(self):
        state = MigrationLoader(None).project_state()
        for model, trigger in registered():
            with self.subTest(model=model._meta.label, trigger=trigger.name):
                stored = state.models[model._meta.app_label, model._meta.model_name]
                self.assertIn(trigger.compile(model), stored.options['triggers'])

    def test_every_maintenance_trigger_is_registered_on_its_model(self):
        from registry.models.metadata import (ApplicationMetadataRecord,
                                              ApplicationMetadataRecordKeywordsLink,
                                              DatasetMetadataRecord,
                                              DatasetMetadataRecordKeywordsLink,
                                              Keyword, ServiceMetadataRecord,
                                              ServiceMetadataRecordKeywordsLink)

        expected = {
            DatasetMetadataRecordKeywordsLink: 1,
            ServiceMetadataRecordKeywordsLink: 1,
            ApplicationMetadataRecordKeywordsLink: 1,
            DatasetMetadataRecord: 1,
            ServiceMetadataRecord: 1,
            ApplicationMetadataRecord: 1,
            Keyword: 1,
        }
        for model, count in expected.items():
            with self.subTest(model=model.__name__):
                registered = getattr(model._meta, 'triggers', [])
                self.assertEqual(len(registered), count)
                # the makemigrations autodetector reads the original attrs
                self.assertIn('triggers', model._meta.original_attrs)

        for record, link in (
                (DatasetMetadataRecord, DatasetMetadataRecordKeywordsLink),
                (ServiceMetadataRecord, ServiceMetadataRecordKeywordsLink),
                (ApplicationMetadataRecord, ApplicationMetadataRecordKeywordsLink)):
            self.assertTrue(link._meta.managed)
            self.assertIs(record.keywords.through, link)
            self.assertIs(apps.get_model('registry', link.__name__),
                          link)


class KeywordThroughMigrationStateTest(SimpleTestCase):
    """The ownership transfer changes Django's state without issuing DDL."""

    def test_the_transfer_preserves_table_definitions_in_both_directions(self):
        loader = MigrationLoader(None)
        migration = loader.get_migration('registry', '0046_explicit_keyword_through_models')
        before = loader.project_state(migration.dependencies)
        # No schema-editor methods are available: any attempted database operation fails.
        schema_editor = SimpleNamespace(atomic_migration=True)
        after = migration.apply(before.clone(), schema_editor)
        reversed_state = migration.unapply(before.clone(), schema_editor)

        for name in ('DatasetMetadataRecord', 'ServiceMetadataRecord',
                     'ApplicationMetadataRecord'):
            with self.subTest(record=name):
                automatic = before.apps.get_model('registry', name).keywords.through
                managed = after.apps.get_model('registry', name).keywords.through
                reversed_model = reversed_state.apps.get_model('registry', name).keywords.through
                self.assertTrue(managed._meta.managed)
                self.assertFalse(managed._meta.auto_created)
                self.assertTrue(reversed_model._meta.auto_created)
                for link in (managed, reversed_model):
                    self.assertEqual(link._meta.db_table, automatic._meta.db_table)
                    self.assertEqual(set(link._meta.unique_together),
                                     set(automatic._meta.unique_together))
                    self.assertEqual(
                        [(field.column, field.get_internal_type(), field.primary_key,
                          field.null) for field in link._meta.fields],
                        [(field.column, field.get_internal_type(), field.primary_key,
                          field.null) for field in automatic._meta.fields])
                self.assertEqual(len(managed._meta.triggers), 1)

    def test_future_link_triggers_use_ordinary_migration_operations(self):
        loader = MigrationLoader(None)
        future = ProjectState.from_apps(apps)
        link_names = {
            'datasetmetadatarecordkeywordslink',
            'servicemetadatarecordkeywordslink',
            'applicationmetadatarecordkeywordslink',
        }
        for name in link_names:
            model_state = future.models['registry', name]
            model_state.options['triggers'] = [
                *model_state.options['triggers'],
                Protect(name='protect_link_probe', operation=Insert),
            ]
        command = load_command_class(get_commands()['makemigrations'], 'makemigrations')
        changes = command.autodetector(loader.project_state(), future).changes(
            graph=loader.graph)
        operations = [operation for migration in changes['registry']
                      for operation in migration.operations]
        self.assertEqual(len(operations), 3)
        self.assertEqual({operation.model_name for operation in operations}, link_names)
        for operation in operations:
            self.assertIs(type(operation), AddTrigger)
            model = apps.get_model('registry', operation.model_name)
            self.assertTrue(operation.allow_migrate_model_trigger(
                SimpleNamespace(connection=connection), model))
