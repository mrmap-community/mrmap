"""The ``RoleDefinition`` model and the catalogue which ships with it (#731).

A role definition is pure description: it names the global permissions which
answer "what may an editor do" and grants nothing itself - django-guardian
and Django's groups remain the enforcement engine, #732 turns a definition
into the managed group of an organization.

The database of a ``TestCase`` is built by running every migration of this
checkout, which is exactly the path of both acceptance targets at once: a
fresh install ends with the same migration run, and an upgraded instance runs
the missing ones - among them ``0005``, which seeds the builtin catalogue.
So asserting the catalogue against this database asserts it for both.
"""

from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from accounts.management.commands.sync_role_definitions import BUILTIN_ROLES
from accounts.models.roles import RoleDefinition, RoleScope

#: the slugs the shipped catalogue must answer on a migrated database
BUILTIN_SLUGS = [spec["slug"] for spec in BUILTIN_ROLES]

#: the new custom permissions with the app their row belongs to; the codename
#: alone is not an answer - Django resolves ``app_label.has_perm`` strings by
#: app_label plus codename, so both must be right
NEW_CUSTOM_PERMISSIONS = [
    ("registry", "publish_resource"),
    ("registry", "share_resource"),
    ("registry", "manage_access_rules"),
    ("registry", "manage_membership"),
    ("registry", "harvest"),
    ("accounts", "grant_platform_role"),
]


class BuiltinCatalogueTestCase(TestCase):
    """What every migrated database must answer without an operator."""

    def test_the_builtin_roles_exist_after_the_migrations(self):
        """Fresh install and upgraded instance see the same catalogue"""
        seeded = {
            role.slug
            for role in RoleDefinition.objects.filter(is_builtin=True)}
        self.assertEqual(seeded, set(BUILTIN_SLUGS))

    def test_the_catalogue_matches_the_migration_after_the_migrations(self):
        """The frozen copy in migration 0005 and the command's copy agree

        A full field-by-field comparison: a drift report with nothing to
        report on a fresh database is only meaningful when the comparison
        itself looks at every reconciled field.
        """
        for spec in BUILTIN_ROLES:
            with self.subTest(role=spec["slug"]):
                role = RoleDefinition.objects.get(slug=spec["slug"])
                self.assertEqual(role.label, spec["label"])
                self.assertEqual(role.description, spec["description"])
                self.assertEqual(role.scope, spec["scope"])
                self.assertTrue(role.is_builtin)
                self.assertEqual(role.is_default, spec["is_default"])
                self.assertEqual(role.is_assignable, spec["is_assignable"])
                self.assertEqual(
                    {f"{permission.content_type.app_label}."
                     f"{permission.codename}"
                     for permission in role.permissions.all()},
                    set(spec["permissions"]))

    def test_every_permission_the_catalogue_names_really_exists(self):
        """No role silently means less than it says (#731 acceptance)"""
        for spec in BUILTIN_ROLES:
            for dotted in spec["permissions"]:
                with self.subTest(role=spec["slug"], permission=dotted):
                    app_label, _, codename = dotted.partition(".")
                    self.assertTrue(
                        Permission.objects.filter(
                            content_type__app_label=app_label,
                            codename=codename).exists(),
                        f"{dotted} is named by the catalogue for "
                        f"'{spec['slug']}' but has no Permission row")

    def test_the_new_custom_permissions_arrived(self):
        """The Meta.permissions declarations of #731 are in the database"""
        for app_label, codename in NEW_CUSTOM_PERMISSIONS:
            with self.subTest(permission=f"{app_label}.{codename}"):
                self.assertTrue(
                    Permission.objects.filter(
                        content_type__app_label=app_label,
                        codename=codename).exists(),
                    f"{app_label}.{codename} has no Permission row, so every "
                    f"catalogue entry naming it promises nothing")

    def test_platform_admin_is_not_offered_in_the_member_picker(self):
        """Holding platform_admin is not an ordinary membership (#731)"""
        role = RoleDefinition.objects.get(slug="platform_admin")
        self.assertFalse(role.is_assignable)
        self.assertEqual(role.scope, RoleScope.PLATFORM)


class RoleDefinitionDeletionTestCase(TestCase):
    """What survives an operator, and what does not."""

    def test_a_builtin_role_cannot_be_deleted(self):
        """Its slug is referenced by migrations and API of the later issues"""
        role = RoleDefinition.objects.get(slug="resource_editor")

        with self.assertRaises(ProtectedError):
            role.delete()
        self.assertTrue(
            RoleDefinition.objects.filter(slug="resource_editor").exists(),
            "the builtin role was deleted despite the guard")

    def test_the_label_and_the_description_of_a_builtin_role_can_be_edited(self):
        """The operator adjusts what a role is called, the row stays"""
        role = RoleDefinition.objects.get(slug="viewer")
        role.label = "Leserin"
        role.description = "Liest die Registry."
        role.save()

        role.refresh_from_db()
        self.assertEqual(role.label, "Leserin")
        self.assertEqual(role.description, "Liest die Registry.")
        self.assertTrue(role.is_builtin)

    def test_a_custom_role_can_be_deleted(self):
        """Only the shipped catalogue is protected"""
        role = RoleDefinition.objects.create(
            slug="geo_cms_editor", label="Geo CMS editor")
        role.delete()
        self.assertFalse(RoleDefinition.objects.filter(
            slug="geo_cms_editor").exists())


class RoleDefinitionFieldTestCase(TestCase):
    """The shape of the model itself."""

    def test_the_slug_is_unique(self):
        with transaction.atomic():
            RoleDefinition.objects.create(slug="unique_slug", label="One")
            with self.assertRaises(IntegrityError):
                RoleDefinition.objects.create(
                    slug="unique_slug", label="The other one")

    def test_the_scope_offers_platform_and_organization(self):
        """The choices enum in the accounts style, as a TextChoices"""
        self.assertEqual(
            [choice.value for choice in RoleScope],
            [RoleScope.PLATFORM.value, RoleScope.ORGANIZATION.value])
        self.assertIsInstance(RoleScope.PLATFORM.value, str)

        role = RoleDefinition(slug="wrong_scope", label="...",
                              scope="GALAXY")
        with self.assertRaises(ValidationError):
            role.full_clean()
        role.scope = RoleScope.ORGANIZATION
        role.full_clean()  # does not raise

    def test_is_builtin_is_not_editable_through_a_form(self):
        """The marker of the shipped rows is not a checkbox to flip

        ``editable=False`` keeps the field out of every ModelForm, so neither
        the admin nor the API form of #736 can offer it; only migrations and
        the sync command set it.
        """
        self.assertFalse(
            RoleDefinition._meta.get_field("is_builtin").editable)
