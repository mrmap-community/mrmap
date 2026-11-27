"""Django's standard migration commands detect the registered triggers.

The retired pgviews app previously shadowed pgtrigger's command integration.
The rebuild of the history (#1850) left no node which carries a view operation
at all, so what remains to be proven is the load without the retired app
itself: the rebuilt chain answers its states with nothing of django_pgviews
installed, and the historical model of the alerts view -- which the rebuild
left no node for -- renders from a state built here, the way the proof of the
keyword transfer builds its intermediate state in the test too.
"""

from types import SimpleNamespace

from django.apps import apps
from django.core.management import get_commands, load_command_class
from django.db import connection, models
from django.db.migrations import (AlterField, CreateModel, Migration,
                                  SeparateDatabaseAndState)
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.state import ModelState, ProjectState
from django.test import SimpleTestCase
from pgtrigger import Insert, Protect
from pgtrigger.migrations import AddTrigger, MigrationAutodetectorMixin
from pgtrigger.registry import registered

#: the model of the alerts view as the node 0017 of the old chain declared it
#: and the node 0037 replaced it with the stored rows of the alerts: the
#: columns of the projection, the model unmanaged. The rebuilt chain carries
#: neither the view nor a node below its replacement, so the state which the
#: load is proven on is built from this declaration.
SERVICE_ALERT_VIEW_FIELDS = [
    ('id', models.CharField(db_column='alert_id', primary_key=True,
                            serialize=False)),
    ('severity', models.CharField(db_column='alert_severity')),
    ('category', models.CharField(db_column='alert_category')),
    ('message', models.CharField(db_column='alert_message')),
    ('service_type', models.CharField(db_column='alert_service_type')),
    ('service', models.CharField(db_column='alert_service')),
    ('service_title', models.CharField(db_column='alert_service_title')),
    ('resource_type', models.CharField(db_column='alert_resource_type')),
    ('resource_id', models.CharField(db_column='alert_resource_id')),
    ('occurred_at', models.DateTimeField(db_column='alert_occurred_at',
                                         null=True)),
    ('target_path', models.CharField(db_column='alert_target_path')),
]

#: the metadata records whose keyword relation answers as an explicit through
#: model of its own today, with the link model each of them names
KEYWORD_LINKS = (
    ('DatasetMetadataRecord', 'DatasetMetadataRecordKeywordsLink'),
    ('ServiceMetadataRecord', 'ServiceMetadataRecordKeywordsLink'),
    ('ApplicationMetadataRecord', 'ApplicationMetadataRecordKeywordsLink'),
)


def unique_pairs(model):
    """The pair uniqueness of a model, however it declares it.

    An automatic through model of a M2M relation gets ``unique_together`` from
    Django itself; the explicit through models of the metadata records name a
    ``UniqueConstraint`` of their own now (#1483). The rule is the same one, so
    the comparison of table definitions which follows reads both ways.
    """
    pairs = {tuple(fields) for fields in model._meta.unique_together}
    pairs |= {
        tuple(constraint.fields)
        for constraint in model._meta.constraints
        if isinstance(constraint, models.UniqueConstraint)}
    return pairs


def column_definitions(model):
    """The table definition of a model: per column its type, whether it is
    the primary key and whether it may be null.

    The columns are read as they are named, not in the order the model
    declares them: which order ``0001_initial`` of the rebuilt chain added
    the foreign keys of a link model in is an artifact of the regeneration
    (the service link's pair came in keyword first), and a table answers by
    its column names. What the comparison over these dictionaries asks is the
    question of the transfer: does every column stand with the same type,
    primary key and nullability on both sides.
    """
    return {field.column: (field.get_internal_type(), field.primary_key,
                           field.null)
            for field in model._meta.fields}


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
        self.assertNotIn(
            'django_pgviews', {app for app, _ in loader.graph.nodes},
            'the retired app may not contribute nodes to the rebuilt chain')
        plan = loader.graph.forwards_plan(('registry', '0001_initial'))
        self.assertIn(('registry', '0001_initial'), plan)

        # the state of the chain, with the model of the alerts view added the
        # way the node 0017 of the old chain created it: the rebuild left no
        # node for the view, so the state the load is proven on stands here
        state = loader.project_state(plan)
        self.assertNotIn(('registry', 'servicealertview'), state.models)
        state.add_model(ModelState('registry', 'ServiceAlertView',
                                   SERVICE_ALERT_VIEW_FIELDS,
                                   {'managed': False}))

        # load without the retired app: a state holding the view answers a
        # real model out of the state alone -- Django renders historical
        # models from their ModelState and never asks the module of
        # django_pgviews for the base of the view
        view = state.apps.get_model('registry', 'ServiceAlertView')
        self.assertFalse(view._meta.managed)
        self.assertEqual(view._meta.db_table, 'registry_servicealertview')
        self.assertEqual(
            {field.name: field.db_column for field in view._meta.fields},
            {name: field.db_column for name, field in SERVICE_ALERT_VIEW_FIELDS},
            'the rendered view lost the columns of its projection')

        # the end of the chain keeps the view away for good: the alerts
        # answer as the rows of a table since the node 0037 of the old chain
        self.assertNotIn(('registry', 'servicealertview'),
                         loader.project_state().models)


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
    """The ownership transfer changes Django's state without issuing DDL.

    The rebuilt chain (#1850) creates the link models of the keywords inside
    ``0001_initial`` and carries no node below the transfer any more, so the
    test answers the property on states it builds itself from the chain -- the
    pattern the rebuild established for the migration proofs: the automatic
    ownership as the transfer found it, the transfer as a migration of the
    test, and the end state read back from ``0001_initial`` to pin both.
    """

    @staticmethod
    def automatic_ownership(chain):
        """The state of the keywords before the transfer, rebuilt.

        The link models are gone and the three M2M fields no longer name a
        through model, which is the ownership the automatic model had: Django
        renders a through model of its own for such a field. The field which
        the transfer set is declared again from the deconstruction of the
        chain's field, with only the ``through`` reference left out -- the way
        the model of the old revision spelled it.
        """
        before = chain.clone()
        for record, link in KEYWORD_LINKS:
            before.remove_model('registry', link.lower())
            _, path, args, kwargs = (
                before.models['registry', record.lower()]
                .fields['keywords'].deconstruct())
            kwargs.pop('through', None)
            before.alter_field('registry', record.lower(), 'keywords',
                               models.ManyToManyField(*args, **kwargs), True)
        return before

    @staticmethod
    def ownership_transfer(chain):
        """The transfer of the keywords to the managed links, as a migration.

        The operations carry the very model states which ``0001_initial``
        answers today: the link models as the chain creates them -- fields,
        constraints, triggers -- and the three M2M fields with the through
        model the chain names. State operations of a
        ``SeparateDatabaseAndState`` wrapper only, which is how the node 0046
        of the old chain changed the state while it issued no DDL.
        """
        state_operations = []
        for record, link in KEYWORD_LINKS:
            link_state = chain.models['registry', link.lower()]
            state_operations.append(CreateModel(
                name=link,
                fields=list(link_state.fields.items()),
                options=dict(link_state.options)))
            state_operations.append(AlterField(
                model_name=record,
                name='keywords',
                field=chain.models['registry', record.lower()]
                .fields['keywords']))
        transfer = Migration('the_transfer_of_the_keyword_ownership',
                             'registry')
        transfer.operations = [SeparateDatabaseAndState(
            state_operations=state_operations)]
        return transfer

    def test_the_transfer_preserves_table_definitions_in_both_directions(self):
        loader = MigrationLoader(None)
        plan = loader.graph.forwards_plan(('registry', '0001_initial'))
        self.assertIn(('registry', '0001_initial'), plan)
        chain = loader.project_state(plan)

        before = self.automatic_ownership(chain)
        transfer = self.ownership_transfer(chain)
        # No schema-editor methods are available: any attempted database
        # operation fails, which is the state-only character of the transfer.
        schema_editor = SimpleNamespace(atomic_migration=True)
        after = transfer.apply(before.clone(), schema_editor)
        reversed_state = transfer.unapply(before.clone(), schema_editor)

        for name, link in KEYWORD_LINKS:
            with self.subTest(record=name):
                # the transfer answers the state which the chain builds --
                # the link as a whole (its ModelState compares over fields
                # and options) and, on the record, the keywords field which
                # is the only one the transfer touches: the whole field
                # dictionary of the record cannot be compared as a ModelState
                # because the ArrayField of the keywords list answers its
                # deconstruct with a fresh clone of the base field on every
                # call, which no two calls ever find equal
                self.assertEqual(after.models['registry', link.lower()],
                                 chain.models['registry', link.lower()])
                record = after.models['registry', name.lower()]
                chain_record = chain.models['registry', name.lower()]
                self.assertEqual(sorted(record.fields),
                                 sorted(chain_record.fields))
                self.assertEqual(record.options, chain_record.options)
                self.assertEqual(
                    record.fields['keywords'].deconstruct()[1:],
                    chain_record.fields['keywords'].deconstruct()[1:],
                    'the transfer did not answer the keywords field of '
                    '0001_initial')

                automatic = before.apps.get_model('registry', name).keywords.through
                managed = after.apps.get_model('registry', name).keywords.through
                reversed_model = reversed_state.apps.get_model('registry', name).keywords.through
                self.assertTrue(managed._meta.managed)
                self.assertFalse(managed._meta.auto_created)
                self.assertTrue(reversed_model._meta.auto_created)
                for link_model in (managed, reversed_model):
                    self.assertEqual(link_model._meta.db_table,
                                     automatic._meta.db_table)
                    self.assertEqual(unique_pairs(link_model),
                                     unique_pairs(automatic))
                    self.assertEqual(column_definitions(link_model),
                                     column_definitions(automatic))
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
