"""Retiring the legacy per-model role groups (#741 AC3).

Migration 0008 left the ``<Org> <model> Admins`` groups of a running instance
standing as *inactive* roles, because guardian's rows point at a group by key.
This module asks what #741 does with that list: the members go to the active
role of the same definition, every guardian row of the group is classified, the
mapping is recorded, and only then does the group go.

Three answers the issue demands are pinned:

* after the upgrade no ``is_active=False`` legacy role is left, and no
  guardian row points at a deleted group;
* **nobody loses a right** - a grant no role covers is preserved per user;
* the record of what went where exists *after* the group is gone, because a
  deleted ``Group`` has no history and its guardian rows cascade with it.

The object the legacy groups grant over is an ``Organization``, which keeps the
fixture to one organization: the dedicated tables of #735 store the rows, and
both dispositions are reachable on it - ``view_organization`` is in the
permission set of the ``organization_admin`` definition (so a grant of it is
*covered* by the role), ``can_publish_for_organization`` is in no set the
retired ``resource_editor`` role holds (so a grant of it must be *preserved*).
"""
from django.apps import apps as global_apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from guardian.shortcuts import assign_perm

from accounts.models.guardian import (OrganizationGroupObjectPermission,
                                      OrganizationUserObjectPermission)
from accounts.models.groups import Organization
from accounts.models.roles import (LegacyGroupRetirement, Role, RoleDefinition,
                                   RoleMembership)
from accounts.retirement import (COVERED_BY_ROLE, PRESERVED_PER_USER,
                                 is_legacy_model_group,
                                 plan_role, retire_legacy_role_groups)

ADMIN_SLUG = "organization_admin"
EDITOR_SLUG = "resource_editor"

ORGANIZATION_NAME = "Retire Org"


class LegacyGroupRetirementTest(TestCase):
    """One organization, the two legacy groups 0008 would have left behind."""

    def setUp(self):
        self.organization = Organization.objects.create(name=ORGANIZATION_NAME)
        self.member = get_user_model().objects.create_user(
            username="retiree", password="x")

        self.admin_definition = RoleDefinition.objects.get(slug=ADMIN_SLUG)
        self.editor_definition = RoleDefinition.objects.get(slug=EDITOR_SLUG)
        self.active_admin_role = Role.objects.for_org(
            self.organization).with_definition(ADMIN_SLUG).get()

        # the covered case: a legacy group of the very definition which also
        # has an active role, granted a permission that definition holds
        self.covered_group = self.legacy_group("organization")
        self.covered_role = self.retired_role(
            self.admin_definition, self.covered_group)
        assign_perm(perm="accounts.view_organization",
                    user_or_group=self.covered_group,
                    obj=self.organization)

        # the preserved case: a legacy group of a definition which does not
        # hold the permission it was granted
        self.preserved_group = self.legacy_group("webmapservice")
        self.preserved_role = self.retired_role(
            self.editor_definition, self.preserved_group)
        assign_perm(perm="accounts.can_publish_for_organization",
                    user_or_group=self.preserved_group,
                    obj=self.organization)

    # -- the fixture -------------------------------------------------------

    def legacy_group(self, model_name, with_member=True):
        """A group named exactly like migration 0008 named a per-model group.

        ``"<organization> <model> Admins"``: the name is the evidence #741
        uses to tell a legacy group from a role an administrator retired over
        the api, so the fixture spells it rather than approximating it.
        """
        group = Group.objects.create(
            name=f"{ORGANIZATION_NAME} {model_name} Admins")
        if with_member:
            group.user_set.add(self.member)
        return group

    def retired_role(self, definition, group):
        """The inactive role 0008 gave a legacy group it could not delete."""
        return Role.objects.create(
            role_definition=definition,
            organization=self.organization,
            group=group,
            is_active=False)

    # -- the plan ----------------------------------------------------------

    def test_the_plan_names_the_successor_the_members_and_each_grant(self):
        """``--dry-run`` answers what an upgrade would do, before it does.

        A report which is not the application would be worthless here: the
        reconciliation deletes rows which cannot be restored, so the same
        classification has to be what runs.
        """
        plan = plan_role(global_apps, self.covered_role)

        self.assertIsNone(plan["declined"])
        self.assertEqual(plan["successor"], str(self.active_admin_role))
        self.assertEqual(
            [(entry["user"], entry["action"]) for entry in plan["members"]],
            [("retiree", "adopted")])
        self.assertEqual(len(plan["grants"]), 1)
        self.assertEqual(plan["grants"][0]["disposition"], COVERED_BY_ROLE)

        plan = plan_role(global_apps, self.preserved_role)
        self.assertEqual(
            [entry["disposition"] for entry in plan["grants"]],
            [PRESERVED_PER_USER])

    def test_the_dry_run_writes_nothing(self):
        """The report is safe to ask of a production copy.

        An operator who wants to see the diff of an upgrade before the upgrade
        must be able to ask - so asking leaves the groups, the memberships and
        the grants exactly as they were, and records nothing.
        """
        report = retire_legacy_role_groups(apps=global_apps, dry_run=True)

        self.assertEqual(len(report["retired"]), 2)
        self.assertEqual(report["declined"], [])
        self.assertEqual(Group.objects.filter(
            pk__in=[self.covered_group.pk, self.preserved_group.pk]).count(), 2)
        self.assertEqual(LegacyGroupRetirement.objects.count(), 0)
        self.assertFalse(RoleMembership.objects.filter(
            role=self.active_admin_role, user=self.member).exists())

    # -- the application ---------------------------------------------------

    def test_retiring_removes_the_legacy_groups_and_their_rows(self):
        """AC3: after the upgrade neither an inactive role nor an orphan row.

        A group which is gone has to be gone *with* the guardian rows which
        pointed at it: ``Role.group`` PROTECTs the group, so the role goes
        first and the group's rows cascade with it - and what is asserted here
        is the end state the acceptance criterion names, not the order which
        produced it.
        """
        retire_legacy_role_groups(apps=global_apps)

        self.assertFalse(
            Role.objects.retired().exists(),
            "an inactive legacy role survived the retirement")
        self.assertFalse(Group.objects.filter(
            pk__in=[self.covered_group.pk, self.preserved_group.pk]).exists())
        self.assertEqual(OrganizationGroupObjectPermission.objects.filter(
            group_id__in=[self.covered_group.pk,
                          self.preserved_group.pk]).count(), 0)
        # the organization which carried the grants is untouched by all of it
        self.assertTrue(Organization.objects.filter(
            pk=self.organization.pk).exists())

    def test_retiring_adopts_the_members_into_the_active_role(self):
        """The person keeps the role axes: adopted, not merely deleted.

        The membership row is the person-readable statement of the grant and
        the group is the enforcement; both are written, because a row without
        the group would be the stale grant this issue is about.
        """
        retire_legacy_role_groups(apps=global_apps)

        membership = RoleMembership.objects.filter(
            role=self.active_admin_role, user=self.member).first()
        self.assertIsNotNone(membership, "the member was not adopted")
        self.assertIn(self.member,
                      self.active_admin_role.group.user_set.all())
        self.assertIsNone(membership.granted_by,
                          "no person decided this grant: a migration took it "
                          "over, and the audit says so by naming no grantor")

    def test_retiring_loses_no_right(self):
        """A grant no role covers is written onto the people who held it.

        The catalogue grants no ``delete_<model>`` and no publish right to the
        retired per-model administrator, so dropping its guardian rows with the
        group would silently narrow what a person may do after the upgrade -
        the one outcome Q5 = B rules out. Preserving it per user broadens
        nothing either: only the member who already held it keeps it.
        """
        retire_legacy_role_groups(apps=global_apps)

        preserved = OrganizationUserObjectPermission.objects.filter(
            user=self.member,
            permission__codename="can_publish_for_organization")
        self.assertEqual(preserved.count(), 1)
        self.assertTrue(
            self.member.has_perm("accounts.can_publish_for_organization",
                                 self.organization),
            "the member could publish before the upgrade and cannot after it")

    def test_the_record_outlives_the_group_it_deleted(self):
        """The mapping AC3 asks for, readable after the rows are gone.

        A deleted ``Group`` has no history of its own and its guardian rows
        cascade away, so without this record the question "whose rights came
        from which legacy group, and was anything broadened?" has no answer on
        an upgraded instance.
        """
        retire_legacy_role_groups(apps=global_apps)

        records = {record.group_name: record
                   for record in LegacyGroupRetirement.objects.all()}
        self.assertEqual(
            set(records),
            {f"{ORGANIZATION_NAME} organization Admins",
             f"{ORGANIZATION_NAME} webmapservice Admins"})

        covered = records[f"{ORGANIZATION_NAME} organization Admins"]
        self.assertEqual(covered.role_definition.slug, ADMIN_SLUG)
        self.assertEqual(covered.successor, self.active_admin_role)
        self.assertEqual(covered.grants_covered, 1)
        self.assertEqual(covered.grants_preserved, 0)
        self.assertEqual(covered.members[0]["user"], "retiree")

        preserved = records[f"{ORGANIZATION_NAME} webmapservice Admins"]
        self.assertEqual(preserved.grants_preserved, 1)
        self.assertEqual(
            preserved.grants[0]["permission"],
            "accounts.can_publish_for_organization")

    def test_running_the_retirement_twice_changes_nothing(self):
        """Idempotence: the second sweep has nothing left to reconcile.

        ``migrate`` can be run again at any time, and a data migration which
        re-deleted on a second run would be a hazard rather than a nuisance.
        """
        retire_legacy_role_groups(apps=global_apps)
        before = LegacyGroupRetirement.objects.count()

        report = retire_legacy_role_groups(apps=global_apps)

        self.assertEqual(report["retired"], [])
        self.assertEqual(LegacyGroupRetirement.objects.count(), before)

    def test_a_role_an_administrator_retired_is_left_alone(self):
        """An inactive role is not evidence of a legacy group.

        #736 lets an administrator retire a role to take it out of the member
        picker without deleting it. Such a role is a decision somebody can
        still undo, so a migration must not delete it: the sweep reports it and
        leaves it, which is what ``is_legacy_model_group`` is for.
        """
        retired_by_hand = Group.objects.create(
            name=f"{ORGANIZATION_NAME}: {EDITOR_SLUG}")
        role = Role.objects.create(
            role_definition=self.editor_definition,
            organization=self.organization,
            group=retired_by_hand,
            is_active=False)
        self.assertFalse(is_legacy_model_group(global_apps, role))

        report = retire_legacy_role_groups(apps=global_apps)

        self.assertIn(retired_by_hand.name, report["skipped"])
        self.assertTrue(
            Role.objects.filter(pk=role.pk).exists(),
            "a role an administrator retired was deleted by the migration")

    def test_anonymous_and_inactive_members_are_never_adopted(self):
        """No migration publishes anything (Q2 of #727).

        The guardian anonymous user sits in ``user_set`` of a group which was
        ever granted something; adopting it into the successor role would make
        whatever the successor's group holds public, so it is never a member to
        adopt - and the group goes, which is what withdraws the grant.
        """
        from guardian.utils import get_anonymous_user

        anonymous = get_anonymous_user()
        self.covered_group.user_set.add(anonymous)

        plan = plan_role(global_apps, self.covered_role)

        self.assertEqual(
            [entry["user"] for entry in plan["members"]], ["retiree"])
