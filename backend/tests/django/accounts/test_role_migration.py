"""The upgrade of an instance which existed before #732.

``accounts/migrations/0007_roles_for_the_groups_of_an_existing_instance.py``
turns the groups a deployment already has into roles. The premises it rests
on are the premises of decision Q5 of #727, and this module pins each of them:

* a legacy group is **reused**, never copied or replaced: guardian's rows point
  at the group by key, so the person who could change something before the
  upgrade can change the same thing after it - asserted by asking the
  permission checker, not by comparing names;
* the two organization-wide groups become *active* roles and the per-model
  groups become **retired** ones, because #741 first has to reconcile what the
  model groups grant - an organization may thereby hold two retired roles of
  one definition, the shape the work list of #741 reads;
* members are adopted with ``granted_by = NULL``: the membership is real, the
  decision behind it is recorded nowhere;
* every run is idempotent and the reverse deletes only the role rows - a group
  is never deleted as a side effect of a rollback.

Like ``test_object_permission_data_migration.py``, this module calls the
migration functions with the live app registry: the functions take ``apps`` as
their first argument, and running them inside a normal ``TestCase`` keeps every
write inside the transaction Django rolls back.

The deployment to migrate is the fixture ``test_deployed_organization.json``:
an organization loaded through ``loaddata``, which therefore never ran the
role bootstrap and still stands exactly as an instance of the time before
#732 - together with the four groups its old bootstrap had created for it and
the guardian rows of those groups.
"""
import importlib

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from guardian.core import ObjectPermissionChecker

from accounts.models import Organization, Role, RoleDefinition, RoleMembership
from accounts.models.guardian import OrganizationGroupObjectPermission

#: the migration under test; the leading digits make it unimportable with
#: ``import``, exactly like the neighbour module above does it
ROLE_MIGRATION = importlib.import_module(
    "accounts.migrations.0007_roles_for_the_groups_of_an_existing_instance")

#: the organization of the deployed fixture and the groups its bootstrap
#: created for it - spelled as literals because they are the legacy shape,
#: the one thing no production code path may name any more
DEPLOYED = "Deployed Organization"
LEGACY_ADMINISTRATORS = f"{DEPLOYED} Administrators"
LEGACY_MEMBERS = f"{DEPLOYED} Members"
LEGACY_WMS_ADMINS = f"{DEPLOYED} webmapservice Admins"
LEGACY_WFS_ADMINS = f"{DEPLOYED} webfeatureservice Admins"


def upgrade():
    """Both steps of the migration, in order"""
    ROLE_MIGRATION.map_existing_organizations(django_apps, None)
    ROLE_MIGRATION.seed_platform_roles(django_apps, None)


def roll_back():
    ROLE_MIGRATION.remove_roles(django_apps, None)


def role_shape():
    """Every role row, in a comparable shape (without primary keys)"""
    return sorted(
        (role.group_id, role.role_definition_id, role.organization_id,
         role.is_active)
        for role in Role.objects.all())


class UpgradeOfADeploymentTestCase(TestCase):
    """What the migration makes of a deployment's organizations."""

    fixtures = ["test_users.json", "test_deployed_organization.json"]

    def setUp(self):
        self.organization = Organization.objects.get(name=DEPLOYED)
        self.admin = get_user_model().objects.get(username="User1")
        self.member = get_user_model().objects.get(username="User2")
        # the memberships the deployment accumulates over its life, written
        # the way the deployment wrote them: by group
        self.admin.groups.add(
            Group.objects.get(name=LEGACY_ADMINISTRATORS),
            Group.objects.get(name=LEGACY_WMS_ADMINS))
        self.member.groups.add(
            Group.objects.get(name=LEGACY_MEMBERS),
            Group.objects.get(name=LEGACY_WFS_ADMINS))

    def test_the_legacy_groups_are_reused_not_replaced(self):
        """Each role manages the very group row it grew from"""
        before = {group.pk: group.name for group in Group.objects.all()}

        upgrade()

        for slug, legacy_name in (
                ("organization_admin", LEGACY_ADMINISTRATORS),
                ("viewer", LEGACY_MEMBERS)):
            role = Role.objects.for_org(self.organization).with_definition(
                slug).get()
            self.assertEqual(role.group.name, legacy_name)

        retired = Role.objects.for_org(
            self.organization).retired().filter(
                role_definition__slug="resource_editor")
        self.assertEqual(
            {role.group.name for role in retired},
            {LEGACY_WMS_ADMINS, LEGACY_WFS_ADMINS},
            "the two per-model groups of the deployment became two retired "
            "roles of the one definition which manages both models")
        self.assertTrue(all(not role.is_active for role in retired))

        for pk, name in before.items():
            self.assertTrue(
                Group.objects.filter(pk=pk).exists(),
                f"the migration deleted the group {name}")

    def test_the_organization_row_is_never_taken_for_a_group(self):
        """An organization *is* a group row - and stays its own row

        The lookup for legacy groups runs over ``auth_group``, the very table
        the organization itself sits in. Taking the organization for one of
        its own legacy groups would hand it out as a role's group.
        """
        upgrade()

        self.assertFalse(
            Role.objects.filter(group_id=self.organization.pk).exists())

    def test_every_definition_ends_up_with_a_role(self):
        """The upgraded instance answers the catalogue of a fresh one

        A definition which never had a group of its own gets a new, empty,
        active group; the ``resource_editor`` of this deployment already
        exists twice over as retired rows and is not doubled by a new one.
        """
        upgrade()

        for definition in RoleDefinition.objects.filter(
                scope="ORGANIZATION"):
            self.assertTrue(
                Role.objects.for_org(
                    self.organization).filter(
                        role_definition=definition).exists(),
                f"{definition.slug} has no role on the upgraded organization")
        self.assertFalse(
            Role.objects.for_org(self.organization).with_definition(
                "resource_editor").exists(),
            "the active lookup stays empty while both editor roles of the "
            "deployment wait for #741 - which is what keeps an upgraded "
            "instance from silently holding two managing roles")

    def test_the_members_are_adopted_without_a_grantor(self):
        """A membership the migration took over explains itself by NULL"""
        upgrade()

        admin_role = Role.objects.for_org(
            self.organization).with_definition("organization_admin").get()
        viewer_role = Role.objects.for_org(
            self.organization).with_definition("viewer").get()
        retired_editors = Role.objects.for_org(
            self.organization).retired().filter(
                role_definition__slug="resource_editor")

        self.assertTrue(RoleMembership.objects.filter(
            role=admin_role, user=self.admin, granted_by__isnull=True).exists())
        self.assertTrue(RoleMembership.objects.filter(
            role=viewer_role, user=self.member,
            granted_by__isnull=True).exists())
        # the member of a model group is adopted by its retired role as well:
        # her rights continue until #741 reconciles the group
        self.assertEqual(
            RoleMembership.objects.filter(
                role__in=retired_editors, user=self.admin).count(), 1)
        self.assertEqual(
            RoleMembership.objects.filter(
                role__in=retired_editors, user=self.member).count(), 1)

    def test_the_same_person_holds_the_same_rights_after_the_upgrade(self):
        """AC: the upgrade changes no answer of the permission checker

        The fixture wrote the guardian rows of the legacy groups; the reuse
        means the checker keeps answering from exactly those rows.
        """
        before_admin = ObjectPermissionChecker(self.admin)
        self.assertTrue(
            before_admin.has_perm('accounts.change_organization',
                                  self.organization))

        upgrade()

        self.assertTrue(ObjectPermissionChecker(self.admin).has_perm(
            'accounts.change_organization', self.organization))
        self.assertTrue(ObjectPermissionChecker(self.member).has_perm(
            'accounts.view_organization', self.organization))
        self.assertFalse(ObjectPermissionChecker(self.member).has_perm(
            'accounts.change_organization', self.organization))

    def test_a_second_run_changes_nothing(self):
        """Restartable: a half-done run re-runs without doubling anything"""
        upgrade()
        roles, memberships = role_shape(), sorted(
            (m.role_id, m.user_id) for m in RoleMembership.objects.all())
        groups = Group.objects.count()

        upgrade()

        self.assertEqual(role_shape(), roles)
        self.assertEqual(
            sorted((m.role_id, m.user_id)
                   for m in RoleMembership.objects.all()),
            memberships)
        self.assertEqual(Group.objects.count(), groups)


class PlatformRolesSeededTestCase(TestCase):
    """The platform half of the migration: roles without an organization."""

    fixtures = ["test_users.json"]

    def test_the_platform_roles_are_seeded_without_a_member(self):
        """The migration seeds the instances; it enrols nobody

        Decision Q6 of #727: the superuser of the instance is not enrolled in
        ``platform_admin`` either - a seeded role is an empty group.
        """
        roll_back()

        ROLE_MIGRATION.seed_platform_roles(django_apps, None)

        for definition in RoleDefinition.objects.filter(scope="PLATFORM"):
            roles = Role.objects.filter(
                organization__isnull=True, role_definition=definition)
            self.assertEqual(roles.count(), 1, definition.slug)
            self.assertTrue(roles.get().is_active)
            self.assertEqual(
                roles.get().group.name, f"platform: {definition.slug}",
                "the migration's spelling of the platform prefix must agree "
                "with accounts.models.roles.PLATFORM_GROUP_PREFIX")
            self.assertEqual(roles.get().members.count(), 0)

        self.assertEqual(RoleMembership.objects.count(), 0,
                         "the migration enrolled somebody into a role")


class ReverseTestCase(TestCase):
    """The reverse deletes the rows this migration wrote - and nothing else."""

    fixtures = ["test_users.json", "test_deployed_organization.json"]

    def test_the_reverse_keeps_every_group_and_every_grant(self):
        """Undoing #732 must not undo the groups of a deployment

        A group may hold a grant written onto it after the migration ran;
        deleting groups is #741's deliberate work, never a side effect of a
        rollback. The role rows go, their memberships cascade with them.
        """
        upgrade()
        groups_before = {group.pk for group in Group.objects.all()}
        grants_before = OrganizationGroupObjectPermission.objects.filter(
            content_object=Organization.objects.get(name=DEPLOYED)).count()
        self.assertGreater(grants_before, 0,
                           "the fixture writes no grants to protect")
        self.assertGreater(Role.objects.count(), 0)

        roll_back()

        self.assertEqual(Role.objects.count(), 0)
        self.assertEqual(RoleMembership.objects.count(), 0)
        self.assertEqual({group.pk for group in Group.objects.all()},
                         groups_before,
                         "the reverse deleted a group, including the ones "
                         "this migration created itself")
        self.assertEqual(
            OrganizationGroupObjectPermission.objects.filter(
                content_object=Organization.objects.get(
                    name=DEPLOYED)).count(),
            grants_before)
