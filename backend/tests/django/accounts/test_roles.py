"""The ``Role`` and ``RoleMembership`` models of #732.

A role is one ``RoleDefinition`` of #731 applied to one organization, and it
**is** the ``auth.Group`` which enforces it: Django and django-guardian already
resolve the permissions of the groups a user belongs to, so a role adds no
place to ask whether somebody may do something. What the two models add is the
identity which does not depend on a name (#727's "renaming an organization
changes no permission") and the record of who decided a membership.

The group name ``"<organization>: <slug>"`` exists for the person reading the
Django admin. It is decoration, and these tests keep it that way: every lookup
here goes through ``Role.objects``, and the test for a renamed organization
asserts that the *name* stays stale while the *role* is found - the opposite way
round is the bug this issue removes.

What is pinned besides the lookups:

* one organization gets one role per definition of ORGANIZATION scope, so the
  count follows the catalogue and not the list of models - the group explosion
  of the old bootstrap was ``2 + len(SECURED_MODELS)`` per organization,
* a membership is what puts a person into the group of a role, and removing it
  takes them out again, which revokes every grant the group carried,
* the group of a role is protected against deletion: guardian's rows point at
  it, so #741 has to retire a role deliberately instead of a ``delete()``
  silently dropping the group under the grants.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from guardian.core import ObjectPermissionChecker
from guardian.utils import get_group_obj_perms_model

from accounts.models.guardian import OrganizationGroupObjectPermission
from accounts.models.groups import Organization
from accounts.models.roles import (Role, RoleMembership, RoleDefinition,
                                   RoleScope, role_group_name)

ORGANIZATION_NAME = "Role Org"

#: the two builtin definitions the grants of a new organization are written on:
#: the default role (the successor of the members group) and the administrator
DEFAULT_SLUG = "viewer"
ADMIN_SLUG = "organization_admin"

#: the definition whose permission set holds ``registry.change_webmapservice``
EDITOR_SLUG = "resource_editor"


def group_grants(group, obj):
    """The codenames a group holds as object permissions on ``obj``.

    Asked from the table guardian resolves for the object, which for an
    organization is ``accounts.models.guardian``'s own table and not the shared
    one (``accounts/models/guardian.py`` says why).

    Args:
        group: the group to ask
        obj: the object the grants are asked for

    Returns:
        set: the codenames of the object permissions of that group on the object
    """
    model = get_group_obj_perms_model(obj)
    if model.objects.is_generic():
        rows = model.objects.filter(
            object_pk=str(obj.pk),
            content_type=ContentType.objects.get_for_model(obj),
            group=group)
    else:
        rows = model.objects.filter(content_object=obj, group=group)
    return set(rows.values_list("permission__codename", flat=True))


class RoleCreationTestCase(TestCase):
    """What one ``Organization.objects.create`` turns into roles."""

    fixtures = ["test_users.json"]

    def setUp(self):
        self.organization = Organization.objects.create(name=ORGANIZATION_NAME)

    def test_an_organization_gets_one_role_per_definition_of_its_scope(self):
        """The roles of an organization are its catalogue, applied"""
        definitions = RoleDefinition.objects.filter(
            scope=RoleScope.ORGANIZATION)
        roles = Role.objects.for_org(self.organization)

        self.assertEqual(roles.count(), definitions.count())
        self.assertEqual(
            {role.role_definition.slug for role in roles},
            set(definitions.values_list("slug", flat=True)))

    def test_the_role_count_follows_the_catalogue_and_not_the_models(self):
        """A definition added to the catalogue is a role; a model is not

        The group count of an organization used to be ``2 + len(SECURED_MODELS)``
        and a role-managed model could only join it with a data migration for
        every organization which existed. Here the number moves with the
        definitions and a group which is no role cannot appear at all.
        """
        roles_before = Role.objects.for_org(self.organization).count()

        RoleDefinition.objects.create(
            slug="extra_org_role", label="Extra", scope=RoleScope.ORGANIZATION)
        second = Organization.objects.create(name="Second Role Org")

        self.assertEqual(
            Role.objects.for_org(second).count(), roles_before + 1)
        # and every group the creation wrote is the group of a role, which is
        # where the unmanaged per-model group of the old bootstrap would show up
        created_groups = set(Group.objects.filter(
            name__startswith="Second Role Org").exclude(
                pk=second.pk).values_list("pk", flat=True))
        self.assertEqual(
            created_groups,
            set(Role.objects.for_org(second).values_list(
                "group_id", flat=True)))

    def test_a_role_group_is_named_after_its_organization_and_definition(self):
        """The name is written for reading, with the organization first"""
        role = Role.objects.for_org(self.organization).with_definition(
            EDITOR_SLUG).get()
        self.assertEqual(
            role.group.name, f"{ORGANIZATION_NAME}: {EDITOR_SLUG}")

    def test_a_renamed_organization_is_still_found_by_key(self):
        """The role survives the rename of the name its group carries

        The group name goes stale on purpose: nothing looks it up, so nothing
        has to follow a rename, and a rename which *did* rewrite the names could
        collide with the name a role of another organization already holds.
        """
        role = Role.objects.for_org(self.organization).with_definition(
            ADMIN_SLUG).get()

        self.organization.name = "Renamed Role Org"
        self.organization.save()

        self.assertEqual(
            Role.objects.for_org(self.organization).with_definition(
                ADMIN_SLUG).get(), role)
        self.assertEqual(
            role.group.name, f"{ORGANIZATION_NAME}: {ADMIN_SLUG}")

    def test_a_long_organization_name_is_cut_instead_of_the_definition_slug(self):
        """The ``# FIXME: name max_length is 150 chars`` of the bootstrap

        An organization name is itself bound by the limit - an ``Organization``
        is a ``Group`` - so the limit is reached by the name of a real
        organization plus the ``": <slug>"`` which is added to it. Cutting the
        organization name keeps the part which says what the role *is* and keeps
        the roles of one organization distinct, which is what the unique
        constraint of ``auth_group.name`` asks for.
        """
        limit = Group._meta.get_field("name").max_length
        organization = Organization.objects.create(name="N" * limit)

        names = [role.group.name for role in Role.objects.for_org(organization)]
        self.assertEqual(len(names), len(set(names)))
        for role in Role.objects.for_org(organization):
            self.assertLessEqual(len(role.group.name), limit)
            self.assertTrue(
                role.group.name.endswith(f": {role.role_definition.slug}"))

    def test_a_name_already_taken_is_numbered_instead_of_failing(self):
        """Two organizations whose names agree in their first ~142 characters

        A truncated name is not unique any more, so the creation of a group
        takes the next free spelling instead of raising on the unique constraint
        of ``auth_group`` in the middle of creating an organization.
        """
        limit = Group._meta.get_field("name").max_length
        first = "D" * (limit - 1) + "1"
        second = "D" * (limit - 1) + "2"
        Organization.objects.create(name=first)

        # the name both organizations would give their default role is one name
        self.assertEqual(
            role_group_name(Organization(name=first), DEFAULT_SLUG),
            role_group_name(Organization(name=second), DEFAULT_SLUG))

        organization = Organization.objects.create(name=second)
        role = Role.objects.for_org(organization).with_definition(
            DEFAULT_SLUG).get()
        self.assertNotEqual(
            role.group.name,
            role_group_name(Organization(name=second), DEFAULT_SLUG))
        self.assertLessEqual(len(role.group.name), limit)

    def test_a_group_of_a_role_cannot_be_deleted_underneath_it(self):
        """Guardian's rows point at the group, so #741 retires deliberately"""
        role = Role.objects.for_org(self.organization).with_definition(
            DEFAULT_SLUG).get()
        with self.assertRaises(ProtectedError):
            role.group.delete()


class RoleConstraintTestCase(TestCase):
    """What the database refuses, and what only ``clean()`` can refuse."""

    fixtures = ["test_users.json"]

    def setUp(self):
        self.organization = Organization.objects.create(name=ORGANIZATION_NAME)
        self.definition = RoleDefinition.objects.get(slug=ADMIN_SLUG)

    def test_one_active_role_per_definition_and_organization(self):
        """The role of a definition is asked as a single answer"""
        group = Group.objects.create(name="A Second Administrator Group")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Role.objects.create(
                    role_definition=self.definition,
                    organization=self.organization,
                    group=group)

    def test_the_retired_role_of_a_definition_may_be_duplicated(self):
        """The work list of #741 is allowed to hold several rows of one pair

        A deployment which had ``<Org> webmapservice Admins`` *and*
        ``<Org> webfeatureservice Admins`` holds two groups whose role is the
        same definition, both inactive until they are retired. The unique
        constraint covers the active roles, and ``with_definition`` answers the
        active one only, so the ambiguity stays out of the code paths.
        """
        bootstrap_role = Role.objects.for_org(
            self.organization).with_definition(ADMIN_SLUG).get()

        retired = []
        for name in ("A Retired WMS Group", "A Retired WFS Group"):
            retired.append(Role.objects.create(
                role_definition=self.definition,
                organization=self.organization,
                group=Group.objects.create(name=name),
                is_active=False))

        self.assertEqual(
            {role.pk for role in Role.objects.retired()},
            {role.pk for role in retired})
        # the lookup answers the active role of the bootstrap, undisturbed by
        # the two retired duplicates of the same (definition, organization)
        self.assertEqual(
            list(Role.objects.for_org(
                self.organization).with_definition(ADMIN_SLUG)),
            [bootstrap_role])

    def test_one_active_platform_role_per_definition(self):
        """A platform role has no organization, which is still a value

        A unique constraint of a nullable column compares NULL as distinct by
        default, so without ``nulls_distinct=False`` on the partial constraint
        a second active role of ``platform_admin`` could be inserted beside the
        one the migration of #732 seeded.
        """
        definition = RoleDefinition.objects.get(slug="platform_admin")
        # the migration seeded exactly one active role of every PLATFORM
        # definition, without a member (decision Q6 of #727)
        self.assertEqual(
            Role.objects.filter(organization__isnull=True)
            .with_definition("platform_admin").count(), 1)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Role.objects.create(
                    role_definition=definition,
                    organization=None,
                    group=Group.objects.create(
                        name="A Second Platform Administrator Group"))

    def test_the_organization_is_required_exactly_for_its_own_scope(self):
        """"organization is null iff the scope is PLATFORM"

        A ``CheckConstraint`` may only read the table of the row it constrains,
        and the scope is a column of the definition, so this is validated on the
        model - which is what the admin and the API of #736 run.
        """
        organization_role = Role(
            role_definition=self.definition, organization=None,
            group=Group.objects.create(name="An Unassigned Group"))
        with self.assertRaises(ValidationError):
            organization_role.full_clean()

        platform = RoleDefinition.objects.get(slug="platform_admin")
        platform_role = Role(
            role_definition=platform, organization=self.organization,
            group=Group.objects.create(name="A Misplaced Platform Group"))
        with self.assertRaises(ValidationError):
            platform_role.full_clean()

    def test_a_platform_role_without_an_organization_is_valid(self):
        """``clean()`` accepts the one shape a platform role may have

        A definition freshly added to the catalogue, so no uniqueness of the
        seeded ``platform_admin`` role interferes with reading ``clean()``.
        """
        definition = RoleDefinition.objects.create(
            slug="extra_platform_role", label="Extra",
            scope=RoleScope.PLATFORM)
        role = Role(
            role_definition=definition, organization=None,
            group=Group.objects.create(name="A Valid Platform Group"))
        role.full_clean()


class RoleMembershipTestCase(TestCase):
    """What adding and removing a person from a role does to their rights."""

    fixtures = ["test_users.json"]

    def setUp(self):
        self.organization = Organization.objects.create(name=ORGANIZATION_NAME)
        self.user = get_user_model().objects.get(username="User2")
        self.grantor = get_user_model().objects.get(username="User1")
        self.default_role = Role.objects.for_org(
            self.organization).with_definition(DEFAULT_SLUG).get()
        self.admin_role = Role.objects.for_org(
            self.organization).with_definition(ADMIN_SLUG).get()

    def test_a_membership_adds_the_user_to_the_group_of_the_role(self):
        """The group is the enforcement, the membership row the decision"""
        membership = self.default_role.add_member(
            self.user, granted_by=self.grantor)

        self.assertIn(self.default_role.group, self.user.groups.all())
        self.assertIn(self.user, self.default_role.members)
        self.assertEqual(membership.granted_by, self.grantor)
        self.assertIsNotNone(membership.granted_at)

    def test_a_member_holds_what_the_role_grants(self):
        """The grants of the organization reach the person through the group

        The two object grants of the default role are what the members group of
        a deployment before #732 held, so the same person asked before and after
        the migration has the same rights.
        """
        self.default_role.add_member(self.user)

        checker = ObjectPermissionChecker(self.user)
        self.assertTrue(checker.has_perm(
            'accounts.view_organization', self.organization))
        self.assertTrue(checker.has_perm(
            'accounts.can_publish_for_organization', self.organization))
        self.assertEqual(
            group_grants(self.default_role.group, self.organization),
            {"view_organization", "can_publish_for_organization"})

    def test_leaving_a_role_revokes_everything_the_role_granted(self):
        """Removing the membership takes the user out of the enforcing group"""
        self.admin_role.add_member(self.user)
        self.assertTrue(ObjectPermissionChecker(self.user).has_perm(
            'accounts.change_organization', self.organization))

        removed = self.admin_role.remove_member(self.user)

        self.assertEqual(removed, 1)
        self.assertNotIn(self.admin_role.group, self.user.groups.all())
        self.assertFalse(ObjectPermissionChecker(self.user).has_perm(
            'accounts.change_organization', self.organization))
        self.assertEqual(
            OrganizationGroupObjectPermission.objects.filter(
                content_object=self.organization,
                group=self.admin_role.group).count(), 2,
            "the grants of the role must stay for its next member")

    def test_a_bulk_removal_takes_the_users_out_of_the_group(self):
        """``RoleMembership.objects.filter(...).delete()`` is a plain call

        A single ``DELETE`` would leave the user in the group, which is a grant
        no membership explains, so the queryset deletes row by row.
        """
        self.admin_role.add_member(self.user)
        RoleMembership.objects.filter(
            role=self.admin_role, user=self.user).delete()

        self.assertNotIn(self.admin_role.group, self.user.groups.all())
        self.assertEqual(
            RoleMembership.objects.filter(role=self.admin_role).count(), 0)

    def test_a_membership_of_one_user_in_one_role_is_unique(self):
        self.default_role.add_member(self.user)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.default_role.add_member(self.user)

    def test_a_retired_role_takes_no_member(self):
        """The group of a retired role waits for #741, it does not gather"""
        self.default_role.is_active = False
        self.default_role.save()

        with self.assertRaises(ValidationError):
            RoleMembership(role=self.default_role, user=self.user).full_clean()

    def test_a_membership_survives_the_deletion_of_its_grantor(self):
        """Who decided is worth keeping, but it must not block the deletion"""
        self.default_role.add_member(self.user, granted_by=self.grantor)
        self.grantor.delete()

        membership = RoleMembership.objects.get(
            role=self.default_role, user=self.user)
        self.assertIsNone(membership.granted_by)
        self.assertIn(self.default_role.group, self.user.groups.all())


class RoleRenameRegressionTestCase(TestCase):
    """AC2: a rename leaves every membership and every grant intact."""

    fixtures = ["test_users.json"]

    def setUp(self):
        self.organization = Organization.objects.create(name=ORGANIZATION_NAME)
        self.user = get_user_model().objects.get(username="User2")
        self.admin_role = Role.objects.for_org(
            self.organization).with_definition(ADMIN_SLUG).get()
        self.admin_role.add_member(self.user)

    def test_renaming_changes_no_membership_and_no_grant(self):
        memberships_before = [
            (membership.pk, membership.role_id, membership.user_id)
            for membership in RoleMembership.objects.all()]
        grants_before = [
            (row.group_id, row.permission_id)
            for row in OrganizationGroupObjectPermission.objects.filter(
                content_object=self.organization)]
        groups_before = list(self.user.groups.values_list("pk", flat=True))

        self.organization.name = "Renamed Role Organization"
        self.organization.save()

        self.assertEqual([
            (membership.pk, membership.role_id, membership.user_id)
            for membership in RoleMembership.objects.all()], memberships_before)
        self.assertEqual(
            sorted((row.group_id, row.permission_id) for row in
                   OrganizationGroupObjectPermission.objects.filter(
                       content_object=self.organization)),
            sorted(grants_before))
        self.assertEqual(
            sorted(self.user.groups.values_list("pk", flat=True)),
            sorted(groups_before))
        self.assertTrue(ObjectPermissionChecker(self.user).has_perm(
            'accounts.change_organization', self.organization))
