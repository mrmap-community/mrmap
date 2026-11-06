"""The makemigrations of this project sees triggers *and* views (#1009).

``django-pgviews-redux`` ships ``makemigrations`` and ``migrate`` commands whose
autodetector only knows the views of that package; ``django-pgtrigger`` patches
Django's base commands instead and ships no command of its own. App commands
are looked up in reverse ``INSTALLED_APPS`` order, so pgviews' commands shadow
the patched base and pgtrigger's autodetector mixin never runs -- triggers
then stay invisible to ``makemigrations`` while the database holds them, which
is the failure that reverted the first pgtrigger attempt in 2023. The project
answers with one shared autodetector combining both mixins
(``MrMap/migration_detection.py``) selected by thin command wrappers; Django's
``commands.E001`` check requires ``makemigrations`` and ``migrate`` to share
exactly that class. These guards fail the day either side of that arrangement
breaks.
"""

from django.apps import apps
from django.core.management import get_commands, load_command_class
from django.test import SimpleTestCase
from django_pgviews.management.commands.makemigrations import (
    Command as PgViewsMakeMigrationsCommand)
from pgtrigger.migrations import MigrationAutodetectorMixin

from MrMap.migration_detection import ViewsAndTriggersAutodetector


class CommandLookupTest(SimpleTestCase):
    """The commands which run are the ones with the combined autodetector."""

    def test_the_project_commands_win_the_lookup(self):
        self.assertEqual(get_commands().get('makemigrations'), 'MrMap')
        self.assertEqual(get_commands().get('migrate'), 'MrMap')

    def test_both_commands_share_the_combined_autodetector(self):
        makemigrations = load_command_class('MrMap', 'makemigrations')
        migrate = load_command_class('MrMap', 'migrate')
        self.assertIs(makemigrations.autodetector, ViewsAndTriggersAutodetector)
        self.assertIs(migrate.autodetector, makemigrations.autodetector)

    def test_the_autodetector_combines_both_packages(self):
        self.assertTrue(issubclass(ViewsAndTriggersAutodetector,
                                   MigrationAutodetectorMixin))
        self.assertTrue(issubclass(ViewsAndTriggersAutodetector,
                                   PgViewsMakeMigrationsCommand.autodetector))

    def test_the_pgviews_command_would_shadow_the_patched_base(self):
        """Documents the hazard this arrangement repairs: the command of the
        views package alone has no trigger detection -- without the wrappers
        above, it is the command which would run."""
        self.assertFalse(issubclass(
            PgViewsMakeMigrationsCommand.autodetector,
            MigrationAutodetectorMixin))


class TriggerRegistrationTest(SimpleTestCase):
    """The keyword maintenance is registered on the models when ready()."""

    def test_every_maintenance_trigger_is_registered_on_its_model(self):
        from registry.models.metadata import (ApplicationMetadataRecord,
                                              DatasetMetadataRecord, Keyword,
                                              ServiceMetadataRecord)
        from registry.triggers import (ApplicationMetadataRecordKeywordsLink,
                                       DatasetMetadataRecordKeywordsLink,
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

        # the unmanaged link models are registered but create nothing
        for link in (DatasetMetadataRecordKeywordsLink,
                     ServiceMetadataRecordKeywordsLink,
                     ApplicationMetadataRecordKeywordsLink):
            self.assertFalse(link._meta.managed)
            self.assertIs(apps.get_model('registry', link.__name__),
                          link)
