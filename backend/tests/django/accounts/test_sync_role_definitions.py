"""``manage.py sync_role_definitions`` (#731): idempotent, drift-reporting.

The command reconciles the shipped catalogue with the database. Three things
are pinned here, and they are the three clauses of the acceptance:

* a freshly migrated database is already in sync - the frozen catalogue of
  migration 0005 and the live catalogue of the command agree, which is what
  stops the two copies from drifting unnoticed;
* running the command again changes nothing - every created, every changed,
  every deleted fact is asserted, not just an output line;
* a role an operator edited is reported and kept: the command names the
  difference instead of reverting it (decision Q4 = A of #727 forbids the
  silent overwrite).
"""

import io

from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from accounts.management.commands import sync_role_definitions
from accounts.management.commands.sync_role_definitions import BUILTIN_ROLES
from accounts.models.roles import RoleDefinition

#: the slug one test edits by hand; a builtin the catalogue holds under two
#: copies is a second test of drift reporting, not of the creation path
EDITED_SLUG = "resource_editor"


def run_sync():
    """Call the command and return what it wrote.

    Returns:
        str: the whole stdout of the run
    """
    out = io.StringIO()
    call_command("sync_role_definitions", stdout=out)
    return out.getvalue()


def catalogue_state():
    """The reconciled state of the whole table, for before/after compares.

    Everything the command compares is captured, so "changed nothing" here
    means "changed nothing the command could have changed" - and the
    permission sets are captured too, which are the interesting part.

    Returns:
        list: one sorted tuple per role definition
    """
    state = []
    for role in RoleDefinition.objects.order_by("slug"):
        state.append((
            role.slug,
            role.label,
            role.description,
            role.scope,
            role.is_builtin,
            role.is_default,
            role.is_assignable,
            sorted(f"{permission.content_type.app_label}."
                   f"{permission.codename}"
                   for permission in role.permissions.all()),
        ))
    return state


class SyncIsInSyncWithTheMigrationTestCase(TestCase):
    """The two shipped copies of the catalogue agree."""

    def test_sync_after_migration_reports_no_drift(self):
        """Nothing to create, nothing edited, nothing reverted"""
        output = run_sync()

        self.assertIn("0 created", output)
        self.assertIn(f"{len(BUILTIN_ROLES)} in sync", output)
        self.assertIn("0 reported as edited", output)
        self.assertNotIn("created builtin role", output)
        self.assertNotIn("differs from the shipped catalogue", output)


class SyncIdempotencyTestCase(TestCase):
    """Running the command twice changes nothing - measured, not asserted."""

    def test_a_second_run_changes_nothing(self):
        first = run_sync()
        before = catalogue_state()
        second = run_sync()
        after = catalogue_state()

        self.assertEqual(before, after)
        self.assertEqual(first, second)

    def test_a_missing_builtin_is_created_and_a_second_run_creates_nothing(
            self):
        """The creation path runs on a catalogue entry the database lacks

        A builtin row cannot be deleted to simulate the missing one - that
        guard has its own test - so the entry is added to the catalogue the
        command reads, which is the same situation the next MrMap version
        faces: the database predates the entry.
        """
        extra = {
            "slug": "next_release_role",
            "label": "Role of a later release",
            "description": "Created by the command, not by migration 0005.",
            "scope": "ORGANIZATION",
            "is_default": False,
            "is_assignable": True,
            "permissions": ["registry.view_webmapservice"],
        }
        catalogue = list(BUILTIN_ROLES) + [extra]

        with patch.object(
                sync_role_definitions, "BUILTIN_ROLES", catalogue):
            first = run_sync()
        self.assertIn(f"created builtin role '{extra['slug']}'", first)
        created = RoleDefinition.objects.get(slug=extra["slug"])
        self.assertTrue(created.is_builtin)
        self.assertEqual(
            [f"{permission.content_type.app_label}.{permission.codename}"
             for permission in created.permissions.all()],
            extra["permissions"])

        before = catalogue_state()
        with patch.object(
                sync_role_definitions, "BUILTIN_ROLES", catalogue):
            second = run_sync()
        self.assertIn("0 created", second)
        self.assertEqual(before, catalogue_state())


class SyncDriftTestCase(TestCase):
    """The edited role is reported, not reverted."""

    def test_a_manually_edited_role_is_reported_and_kept(self):
        role = RoleDefinition.objects.get(slug=EDITED_SLUG)
        shipped_permissions = list(role.permissions.all())

        role.label = "Catalogue editor"
        role.permissions.remove(
            [p for p in shipped_permissions
             if p.codename == "add_webmapservice"][0])
        role.save()
        edited_state = catalogue_state()

        first = run_sync()
        self.assertIn(f"role '{EDITED_SLUG}' differs", first)
        self.assertIn("label: catalogue says", first)
        self.assertIn(
            "registry.add_webmapservice is in the catalogue but not on the "
            "role", first)
        self.assertIn("1 reported as edited", first)
        self.assertEqual(
            catalogue_state(), edited_state,
            "the command reverted the operator's edit")

        # the drift is a stable report, not a one-time event: a second run
        # still reports it and still changes nothing
        second = run_sync()
        self.assertIn(f"role '{EDITED_SLUG}' differs", second)
        self.assertEqual(catalogue_state(), edited_state)

    def test_a_role_the_catalogue_does_not_hold_is_left_alone(self):
        """Operator-defined roles are theirs, not drift to remove"""
        RoleDefinition.objects.create(
            slug="geo_cms_editor", label="Geo CMS editor")
        before = catalogue_state()

        output = run_sync()

        self.assertEqual(catalogue_state(), before)
        self.assertIn("0 created", output)
        self.assertIn("0 reported as edited", output)
        self.assertIn(f"{len(BUILTIN_ROLES)} in sync", output)
