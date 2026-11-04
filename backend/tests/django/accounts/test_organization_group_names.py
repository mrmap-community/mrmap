"""Pins the group names and the ``Permission`` rows of the organization signal.

``accounts/signals.py`` names the groups of an organization by interpolating
its name: ``<name> Administrators``, ``<name> Members`` and, per entry of
``SECURED_MODELS``, ``<name> <model_name> Admins`` - with the Django-lowercased
``model_name``, so the administering group of a WebMapService really reads
``<name> webmapservice Admins``, not the ``<name> WebMapService Admins`` the
epic #727 text paraphrases. Those names are load bearing:
``handle_secured_model_creation`` looks its grant target up by exactly such an
interpolated name. #732 replaces the name-coupled groups with ``Role`` rows,
so the names belong on record before they are gone.

The permission strings of the signal name the ``registry`` app although
``Organization`` lives in ``accounts`` and ``Group`` in ``auth``; the grants
only work because guardian strips the app label and resolves the codename
against the content type of the object. What they really point at is asserted
here as ``Permission`` rows and content types: the honest-app_label half of
#729 may rewrite the strings, and these rows must not move.
"""
from django.contrib.auth.models import Group
from django.test import TestCase
from guardian.core import ObjectPermissionChecker

from accounts.models.guardian import (GroupGroupObjectPermission,
                                      OrganizationGroupObjectPermission)
from accounts.models.groups import Organization
from accounts.utils import get_secured_models

ORGANIZATION_NAME = "Name Pins"


class OrganizationGroupNamesTestCase(TestCase):
    """What one ``Organization.objects.create`` writes into ``auth_group``."""

    fixtures = ["test_users.json"]

    def setUp(self):
        self.groups_before = Group.objects.count()
        self.organization = Organization.objects.create(name=ORGANIZATION_NAME)
        self.admins = Group.objects.get(
            name=f"{ORGANIZATION_NAME} Administrators")
        self.members = Group.objects.get(name=f"{ORGANIZATION_NAME} Members")

    def test_the_creation_interpolates_exactly_two_plus_one_per_model_names(
            self):
        """The full set of group names, spelled out, and nothing else

        Groups per organization are ``2 + len(SECURED_MODELS)`` today; every
        model added to the list multiplies them (#727 motivation), #732 makes
        the count the number of roles. The organization itself is excluded: an
        ``Organization`` is a ``Group`` (multi table inheritance), so its row
        carries its name into ``auth_group`` as well.
        """
        created_groups = Group.objects.filter(
            name__startswith=ORGANIZATION_NAME).exclude(
                pk=self.organization.pk)
        self.assertEqual(
            set(created_groups.values_list("name", flat=True)),
            {f"{ORGANIZATION_NAME} Administrators",
             f"{ORGANIZATION_NAME} Members",
             f"{ORGANIZATION_NAME} webmapservice Admins",
             f"{ORGANIZATION_NAME} webfeatureservice Admins"})
        self.assertEqual(
            Group.objects.count(),
            self.groups_before + 1 + 2 + len(get_secured_models()))

    def test_the_administering_groups_carry_the_lowercased_model_name(self):
        """``webmapservice``, not ``WebMapService``

        The name is built from ``_meta.model_name``, which Django stores in
        lower case. Nothing displays these names (there is no group UI until
        #737), so nobody noticed they disagree with the model spelling the epic
        text quotes; any migration touching the groups (#732 reuses them) has
        to find them under this spelling.
        """
        self.assertTrue(Group.objects.filter(
            name=f"{ORGANIZATION_NAME} webmapservice Admins").exists())
        self.assertTrue(Group.objects.filter(
            name=f"{ORGANIZATION_NAME} webfeatureservice Admins").exists())

    def test_the_administrators_hold_view_and_change_on_every_administering_group(
            self):
        """The signal's ``registry.view_group`` lands on ``auth`` permissions

        The Permission row behind the grant is ``auth.view_group`` /
        ``auth.change_group`` - the app_label of the string is decorative
        (guardian's ``_normalize_perm`` strips it). That dishonesty is what the
        string rewrite of #729 fixes and what these rows keep identical.
        """
        for secured_model in get_secured_models():
            admins_group = Group.objects.get(
                name=f"{ORGANIZATION_NAME} "
                     f"{secured_model._meta.model_name} Admins")
            rows = GroupGroupObjectPermission.objects.filter(
                content_object=admins_group, group=self.admins)
            self.assertEqual(
                set(rows.values_list("permission__codename", flat=True)),
                {"view_group", "change_group"},
                f"wrong grants on {admins_group.name}")
            for row in rows:
                self.assertEqual(row.permission.content_type.app_label, "auth")
                self.assertEqual(row.permission.content_type.model, "group")

    def test_the_organization_grants_point_at_accounts_permission_rows(self):
        """``registry.view_organization`` resolves onto ``accounts`` too

        The rows are the contract of the honest-app_label rewrite: same
        codenames, same content type ``accounts.organization``, same groups.
        """
        rows = OrganizationGroupObjectPermission.objects.filter(
            content_object=self.organization)
        for row in rows:
            self.assertEqual(row.permission.content_type.app_label, "accounts")
            self.assertEqual(row.permission.content_type.model, "organization")
        self.assertEqual(
            set(rows.filter(group=self.admins).values_list(
                "permission__codename", flat=True)),
            {"view_organization", "change_organization"})
        self.assertEqual(
            set(rows.filter(group=self.members).values_list(
                "permission__codename", flat=True)),
            {"view_organization", "can_publish_for_organization"})

    def test_renaming_the_organization_leaves_the_group_names_behind(self):
        """The groups keep the name the organization had when they were born

        A rename changes nothing in the rows behind the groups - the grants
        reference the organization by key - but the names go stale, and
        ``handle_secured_model_creation``, which looks its grant target up by
        ``f'{organization.name} {model_name} Admins'``, then misses. That miss
        is pinned in ``test_service_object_grants``; "renaming an organization
        changes no permission" is an acceptance criterion of #727 for the role
        model of #732.
        """
        self.organization.name = "Renamed Organization"
        self.organization.save()

        self.assertEqual(
            set(Group.objects.filter(
                name__startswith=ORGANIZATION_NAME).values_list(
                    "name", flat=True)),
            {f"{ORGANIZATION_NAME} Administrators",
             f"{ORGANIZATION_NAME} Members",
             f"{ORGANIZATION_NAME} webmapservice Admins",
             f"{ORGANIZATION_NAME} webfeatureservice Admins"})
        checker = ObjectPermissionChecker(self.members)
        self.assertTrue(checker.has_perm(
            'accounts.view_organization', self.organization))
