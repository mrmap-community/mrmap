"""Pins #1141: the post-migrate bootstrap reads MRMAP_PRODUCTION as a flag.

``docker-compose.dev.yml`` exports ``MRMAP_PRODUCTION: 'False'`` - a non-empty
string. Read as ``os.environ.get("MRMAP_PRODUCTION", False)``, that answers
truthy for every development and test service, so
``accounts.apps.create_default_user_and_org`` created the ``Testorganization``
on every migrate - and ``handle_organization_creation`` its groups. A
``TransactionTestCase`` truncates the tables, the rollback
``call_command("migrate", ...)`` fires ``post_migrate`` again, and the groups
recreated there collide with the rows surviving from the earlier creation:
``duplicate key value violates unique constraint "auth_group_name_key"``.

The fix is the parsed ``settings.MRMAP_PRODUCTION`` - settings.py turns the env
string into a bool in one place, and this hook now reads that bool. What these
tests pin is the hook's contract, with the flag set both ways through
``override_settings`` rather than through the process environment, so they read
the same in a development stack and in one which exports the production value.
"""
from django.test import TestCase, override_settings

from accounts.apps import create_default_user_and_org
from accounts.models import Organization

ORGANIZATION_NAME = "Testorganization"


class PostMigrateOrganizationBootstrapTest(TestCase):
    """The organization bootstrap below and with the production flag on."""

    def test_flag_off_creates_no_organization(self):
        """A deployment which is not production gets no Testorganization.

        The count is compared with its own before-value rather than asserted
        empty: how the test database was migrated is not what this test is
        about; that the call below adds nothing is.
        """
        before = Organization.objects.filter(
            name=ORGANIZATION_NAME).count()
        with override_settings(MRMAP_PRODUCTION=False):
            create_default_user_and_org(sender=None)
        self.assertEqual(
            Organization.objects.filter(name=ORGANIZATION_NAME).count(),
            before)

    def test_flag_on_creates_the_organization_once(self):
        """A production deployment gets the organization, twice called once.

        Both calls run inside the same override, the second one standing for
        the next migrate over a database which already holds the row - the
        exists() check has to keep the bootstrap idempotent.
        """
        Organization.objects.filter(name=ORGANIZATION_NAME).delete()
        with override_settings(MRMAP_PRODUCTION=True):
            create_default_user_and_org(sender=None)
            create_default_user_and_org(sender=None)
        self.assertEqual(
            Organization.objects.filter(name=ORGANIZATION_NAME).count(), 1)
