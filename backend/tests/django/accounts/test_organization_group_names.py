"""Nothing looks a role up by group name any more - #1107's shape cannot return.

Before #732 the permission bootstrap of ``accounts.signals`` addressed the
groups of an organization by strings built from that organization's name: the
creation of a secured model filtered ``auth_group`` by
``f'{organization.name} {model_name} Admins'`` and logged
``"... has no group '<that name>'.`` when the row was missing - which happened
whenever the name had drifted from the spelling frozen into the group names,
as issue #1107 reported for renames. The ``# FIXME: name max_length is 150
chars`` above that code was the same mechanism's other half: the name was both
decoration and key.

``Role`` replaced the key with two foreign keys - definition and organization
- so a rename cannot detach anything, and these tests are the regression in the
new shape: they exercise renames through ``Organization.save()`` and assert
that the grants keep landing without a word in the log. The names themselves
are asserted only as *decoration*: readable, unique, and allowed to go stale
(the stale-name assertions live in ``test_roles.py``).
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction
from django.test import TestCase
from guardian.core import ObjectPermissionChecker

from accounts.models import Organization, Role, RoleDefinition
from accounts.models.roles import free_role_group_name
from registry.models.guardian import WebMapServiceGroupObjectPermission
from registry.models.service import WebMapService

#: an organization renamed the way #1107 renamed one: the same readable name,
# once without and once with surrounding whitespace. Nothing strips or
# truncates either spelling - they are simply two names of one organization.
ORIGINAL_NAME = "Name with spaces"
SPACED_NAME = " " * 5 + ORIGINAL_NAME + " " * 5

#: the definition whose permission set manages the secured models
EDITOR_SLUG = "resource_editor"

#: a service of ``test_wms.json`` to copy the required fields from
TEMPLATE_WMS = "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"


class RenameKeepsTheGrantPathTestCase(TestCase):
    """A rename moves a name; the roles, memberships and grants stay put."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json"]

    def setUp(self):
        self.organization = Organization.objects.create(name=ORIGINAL_NAME)
        self.admin = get_user_model().objects.get(username="User1")
        self.member = get_user_model().objects.get(username="User2")
        self.admin_role = Role.objects.for_org(
            self.organization).with_definition("organization_admin").get()
        self.admin_role.add_member(self.admin)
        self.viewer_role = Role.objects.for_org(
            self.organization).with_definition(
                RoleDefinition.objects.get(is_default=True).slug).get()

    def test_rename_to_the_spaced_spelling_changes_nothing_but_the_name(self):
        """The #1107 spelling pair, in the new mechanism

        On the develop-time bootstrap this rename made the next grant-time
        lookup miss its group and log ``has no group``; the roles of #732 are
        reached through ``Role.objects.for_org``, so the same rename changes
        exactly one column and logs nothing.
        """
        self.viewer_role.add_member(self.member)

        self.organization.name = SPACED_NAME
        with self.assertNoLogs("MrMap.root", level="WARNING"):
            self.organization.save()

        self.assertEqual(Organization.objects.get().name, SPACED_NAME)
        admin_checker = ObjectPermissionChecker(self.admin)
        member_checker = ObjectPermissionChecker(self.member)
        self.assertTrue(admin_checker.has_perm(
            'accounts.change_organization', self.organization))
        self.assertTrue(member_checker.has_perm(
            'accounts.view_organization', self.organization))
        self.assertFalse(member_checker.has_perm(
            'accounts.change_organization', self.organization))

    def test_a_service_created_after_the_rename_is_still_granted(self):
        """The creation of a secured model finds its target across a rename

        The grant target used to be ``f'{name} webmapservice Admins'``: after a
        rename no row was ever named that, and everything created afterwards
        went ungranted. Now the target is the organization's active role whose
        definition manages the model - found by key, logged in nothing.
        """
        self.organization.name = SPACED_NAME
        self.organization.save()

        editor = Role.objects.for_org(
            self.organization).with_definition(EDITOR_SLUG).get()
        editor.add_member(self.member)

        template = WebMapService.objects.get(pk=TEMPLATE_WMS)
        service = WebMapService(
            title="Renamed Org WMS",
            service_url="https://www.example.com/wms",
            version=template.version,
            origin=template.origin,
            metadata_contact=template.metadata_contact,
            service_contact=template.service_contact)
        service.owner = self.organization
        with self.assertNoLogs("MrMap.root", level="WARNING"):
            service.save()

        checker = ObjectPermissionChecker(self.member)
        self.assertTrue(checker.has_perm(
            'registry.change_webmapservice', service))
        self.assertEqual(
            set(WebMapServiceGroupObjectPermission.objects.filter(
                content_object=service).values_list(
                    "group__name", flat=True)),
            {editor.group.name},
            "the grant went to the role the catalogue names, not to a group "
            "named after the organization")


class RetiredRolesOfOneDefinitionTestCase(TestCase):
    """Several roles of one definition coexist - each keeps its own group.

    Q4 of #727: one group per role. The upgrade of #741 will find an
    organization which held ``<Org> webmapservice Admins`` *and*
    ``<Org> webfeatureservice Admins`` now holds two retired roles whose
    definition manages both models. The old name scheme collapsed such roles
    into one group; the numbering of ``free_role_group_name`` keeps the
    decoration distinguishable while only the role rows carry meaning.
    """

    fixtures = ["test_users.json"]

    def setUp(self):
        self.organization = Organization.objects.create(name="Same Slug")
        self.definition = RoleDefinition.objects.get(slug=EDITOR_SLUG)

    def create_retired(self):
        """One retired role of the definition, named the way #732 names groups"""
        group = Group.objects.create(
            name=free_role_group_name(self.organization, self.definition.slug))
        return Role.objects.create(
            role_definition=self.definition,
            organization=self.organization,
            group=group,
            is_active=False)

    def test_roles_of_one_definition_get_distinguishable_names(self):
        # the active role of the bootstrap already holds the plain name
        plain = Role.objects.for_org(
            self.organization).with_definition(EDITOR_SLUG).get().group.name
        retired = [self.create_retired() for _ in range(2)]
        names = [plain] + [role.group.name for role in retired]

        self.assertEqual(len(set(names)), 3, names)
        self.assertEqual(names[0], "Same Slug: resource_editor")
        self.assertEqual(names[1], "Same Slug: resource_editor (2)")
        self.assertEqual(names[2], "Same Slug: resource_editor (3)")

    def test_retired_roles_stay_out_of_the_lookup(self):
        """``with_definition`` answers the active role, never a retired twin"""
        retired = self.create_retired()

        self.assertEqual(
            list(Role.objects.for_org(
                self.organization).with_definition(EDITOR_SLUG)),
            [Role.objects.for_org(self.organization).active().get(
                role_definition=self.definition)])
        self.assertIn(retired, Role.objects.retired())

    def test_a_second_active_role_of_one_definition_is_refused(self):
        """Two *active* roles of one pair are the accident the constraint is for"""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Role.objects.create(
                    role_definition=self.definition,
                    organization=self.organization,
                    group=Group.objects.create(name="A Second Editor Group"))
