"""The anonymous viewer role group of #739 - the seed and its meaning.

Decision Q2 of #727: public is an explicit grant, never a side effect. The
grant needs something to be granted TO, and that something is this role: the
``anonymous_viewer`` definition of the catalogue (#731), a PLATFORM-scope
``Role`` with its group (0004 seeds both), and guardian's anonymous user row
as the group's only member - so every anonymous permission check, mapped to
that row, reads exactly the grants which say "the public may view this".

Three things are pinned here:

* the frozen copy in migration 0004 and the live catalogue of
  ``sync_role_definitions`` agree - the same guard ``test_role_definitions.py``
  runs for 0002, because a drift would make an upgraded instance mean
  something else than a fresh install;
* ``ensure_anonymous_viewer`` recreates what a truncation removed and does it
  twice without duplicating anything - guardian 3.5.2 only *reads* its
  anonymous row (``get_anonymous_user`` is a plain ``get``), so nothing else
  in this project ever writes it;
* the meaning itself: a service which comes into the world through the ORM is
  **not** public - the creation bootstrap grants the roles of the owning
  organization and never the anonymous group; only ``set_public`` writes that
  grant, and taking it back leaves every other grant exactly as it was.
"""
import importlib

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from accounts.apps import ensure_anonymous_viewer_hook
from accounts.management.commands.sync_role_definitions import BUILTIN_ROLES
from accounts.models.groups import Organization
from accounts.models.roles import (ANONYMOUS_VIEWER_ROLE, PLATFORM_GROUP_PREFIX,
                                   Role, RoleDefinition, role_group_name)
from accounts.utils import anonymous_viewer_group, ensure_anonymous_viewer
from extras.permissions import Visibility, allowed, set_public
from guardian.utils import get_anonymous_user
from registry.models.metadata import MetadataContact
from registry.models.service import WebMapService

#: the migration whose frozen copy is pinned against the live catalogue
MIGRATION = importlib.import_module(
    "accounts.migrations."
    "0004_the_anonymous_viewer_role_group_is_seeded")

#: the catalogue entry the migration mirrors
SPEC = next(spec for spec in BUILTIN_ROLES
            if spec["slug"] == ANONYMOUS_VIEWER_ROLE)

#: a service of ``test_wms.json``, only used to copy the fields a service needs
TEMPLATE_WMS = "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"

#: the username guardian maps anonymous requests to (#739 seeds its row)
ANONYMOUS_USERNAME = "AnonymousUser"

ORGANIZATION_NAME = "Anonymous Viewer Amt"


def visibility_of(service):
    """The annotation answered for one service, through the SQL of #739."""
    return WebMapService.objects.filter(
        pk=service.pk).with_visibility().values_list(
            "visibility", flat=True).first()


class CatalogueMirrorTestCase(TestCase):
    """The frozen copy in the migration says what the catalogue says."""

    def test_the_frozen_fields_agree_with_the_live_catalogue(self):
        self.assertEqual(MIGRATION.SLUG, SPEC["slug"])
        self.assertEqual(MIGRATION.LABEL, SPEC["label"])
        self.assertEqual(MIGRATION.DESCRIPTION, SPEC["description"])
        self.assertEqual(set(MIGRATION.PERMISSIONS), set(SPEC["permissions"]))
        # the migration spells the scope as the stored literal, the command
        # as the enum - both must name the platform scope
        self.assertEqual(SPEC["scope"], "PLATFORM")
        self.assertFalse(SPEC["is_default"])
        self.assertFalse(SPEC["is_assignable"])

    def test_the_frozen_group_name_agrees_with_the_model_naming(self):
        """The naming both spellings agree on, and the name is on the group"""
        self.assertEqual(MIGRATION.PLATFORM_GROUP_PREFIX,
                         PLATFORM_GROUP_PREFIX)
        name = role_group_name(None, ANONYMOUS_VIEWER_ROLE)
        self.assertEqual(
            f"{MIGRATION.PLATFORM_GROUP_PREFIX}: {MIGRATION.SLUG}", name)
        self.assertEqual(
            Role.objects.with_definition(ANONYMOUS_VIEWER_ROLE).get().group,
            anonymous_viewer_group())

    def test_the_definition_and_its_role_arrive_with_the_migrations(self):
        """A migrated database needs no command to answer the role."""
        definition = RoleDefinition.objects.get(slug=ANONYMOUS_VIEWER_ROLE)
        self.assertTrue(definition.is_builtin)
        self.assertFalse(definition.is_assignable)

        role = Role.objects.with_definition(ANONYMOUS_VIEWER_ROLE).get()
        self.assertIsNone(role.organization)
        self.assertEqual(
            role.group.name,
            f"{PLATFORM_GROUP_PREFIX}: {ANONYMOUS_VIEWER_ROLE}")

    def test_the_anonymous_user_is_the_only_member(self):
        """Nobody joins this group by a decision - not even an admin."""
        ensure_anonymous_viewer()
        group = anonymous_viewer_group()
        self.assertEqual(
            list(group.user_set.values_list("username", flat=True)),
            [ANONYMOUS_USERNAME])
        # the row exists before any anonymous request asked for it, and it
        # can never log in: guardian's row, not an account
        self.assertFalse(get_user_model().objects.get(
            username=ANONYMOUS_USERNAME).has_usable_password())
        self.assertEqual(get_anonymous_user().username, ANONYMOUS_USERNAME)


class EnsureAnonymousViewerTestCase(TestCase):
    """The post-migrate guard, asked out of turn and twice."""

    def test_running_the_guard_twice_changes_nothing(self):
        first = anonymous_viewer_group()
        _, again = ensure_anonymous_viewer()

        self.assertEqual(again, first)
        self.assertEqual(
            RoleDefinition.objects.filter(
                slug=ANONYMOUS_VIEWER_ROLE).count(), 1)
        self.assertEqual(
            Role.objects.with_definition(ANONYMOUS_VIEWER_ROLE).count(), 1)
        self.assertEqual(get_user_model().objects.filter(
            username=ANONYMOUS_USERNAME).count(), 1)

    def test_the_guard_recreates_a_deleted_group_and_member(self):
        """Rows a ``TransactionTestCase`` truncation removes come back.

        The guard runs the way the ``post_migrate`` hook runs it - on a
        database which still holds the catalogue (the builtin definitions are
        protected) but no longer the rows 0004 wrote beside it.
        """
        role = Role.objects.with_definition(ANONYMOUS_VIEWER_ROLE).get()
        name = role.group.name
        group = role.group
        anonymous = get_user_model().objects.filter(
            username=ANONYMOUS_USERNAME).first()
        # the shape of the migration's reverse: the Role PROTECTs its group
        role.delete()
        group.delete()
        if anonymous is not None:
            anonymous.delete()

        user, recreated = ensure_anonymous_viewer()

        self.assertEqual(recreated.name, name)
        self.assertIn(user, recreated.user_set.all())
        self.assertEqual(user.username, ANONYMOUS_USERNAME)

    def test_a_group_left_without_a_role_is_reused_not_duplicated(self):
        """The check-then-create shape: no orphan group behind a retry."""
        role = Role.objects.with_definition(ANONYMOUS_VIEWER_ROLE).get()
        group = role.group
        role.delete()  # the group deliberately stays behind, E005 aside

        _, recreated = ensure_anonymous_viewer()

        self.assertEqual(recreated, group)

    def test_the_hook_answers_nothing_on_a_flushed_database(self):
        """The empty catalogue a ``flush`` leaves behind is not a failure.

        ``flush`` emits ``post_migrate`` over the tables it has just truncated,
        and a truncate asks no delete: the protected rows of the catalogue are
        gone with everything else. A hook which raised there took the teardown
        of every flushing test down with it - the trap #1141 tells for the
        default organization.
        """
        # a real flush truncates the tables and asks no delete, so the roles
        # are gone together with their definitions; ``Role.role_definition``
        # is PROTECT, which forbids that order in code, so the roles go first
        # to reach the state a flush leaves behind
        Role.objects.all().delete()
        RoleDefinition.objects.all().delete()

        ensure_anonymous_viewer_hook(sender=None)

        self.assertFalse(
            Role.objects.with_definition(ANONYMOUS_VIEWER_ROLE).exists(),
            "without the catalogue there is nothing to build the role from")
        self.assertIsNone(anonymous_viewer_group(),
                          "and nothing is public, which is the safe answer")


class PublicIsAnExplicitGrantTestCase(TestCase):
    """What a service starts as, and what makes it public - and un-publics."""

    #: the history rows of test_wms.json name their user by natural key and
    #: loaddata resolves that while it loads, so the users must be loaded
    #: first or the class dies in setUpClass
    fixtures = ["test_users.json", "test_keywords.json", "test_wms.json"]

    def setUp(self):
        template = WebMapService.objects.get(pk=TEMPLATE_WMS)
        self.contact = MetadataContact.objects.get(pk=1)
        self.version = template.version
        self.origin = template.origin
        # robust against a truncation of the seeded rows before this class
        # (tests/AGENTS.md): recreate through the same paths the deployment
        # uses - the catalogue through the command, the rows through the guard
        call_command("sync_role_definitions", verbosity=0)
        ensure_anonymous_viewer()

    def build_service(self, title, owner=None):
        service = WebMapService(
            title=title,
            service_url="https://www.example.com/wms",
            version=self.version,
            origin=self.origin,
            metadata_contact=self.contact,
            service_contact=self.contact,
            owner=owner)
        service.save()
        return service

    def test_a_new_service_of_an_organization_is_organization_internal(self):
        """The creation bootstrap's grants are the org-internal answer."""
        from django.contrib.auth.models import AnonymousUser

        organization = Organization.objects.create(name=ORGANIZATION_NAME)
        service = self.build_service("Internal", owner=organization)

        self.assertEqual(
            visibility_of(service), Visibility.ORGANIZATION_INTERNAL)
        self.assertFalse(allowed(
            AnonymousUser(), "registry.view_webmapservice", service))

    def test_a_new_service_without_an_owner_is_restricted(self):
        """No owner means no organization grant either - decision Q2."""
        service = self.build_service("Orphaned")

        self.assertEqual(visibility_of(service), Visibility.RESTRICTED)

    def test_public_only_after_the_explicit_grant(self):
        from django.contrib.auth.models import AnonymousUser

        organization = Organization.objects.create(name=ORGANIZATION_NAME)
        service = self.build_service("To publish", owner=organization)

        set_public(service, True)
        self.assertEqual(visibility_of(service), Visibility.PUBLIC)
        self.assertTrue(allowed(
            AnonymousUser(), "registry.view_webmapservice", service))

        set_public(service, False)
        self.assertEqual(
            visibility_of(service), Visibility.ORGANIZATION_INTERNAL)
        self.assertFalse(allowed(
            AnonymousUser(), "registry.view_webmapservice", service))

    def test_unpublishing_leaves_the_other_grants_alone(self):
        """Revoking the anonymous grant is not revoking everything."""
        from guardian.shortcuts import get_groups_with_perms

        organization = Organization.objects.create(name=ORGANIZATION_NAME)
        service = self.build_service("Keepers", owner=organization)
        holders_before = set(get_groups_with_perms(service))

        set_public(service, True)
        set_public(service, False)

        self.assertEqual(
            set(get_groups_with_perms(service)), holders_before,
            "withdrawing from the public added or removed a holder besides "
            "the anonymous viewer group")
