"""Moves the permissions guardian shared into the tables of their own.

The migrations ``registry/0022`` and ``accounts/0003`` carry the rows which a
deployment already stored in guardian's shared tables into the dedicated tables
of their model. Guardian answers a model with such a table only from it, so a
row which does not move is a grant which stops working, and a row naming an
object which is gone may not move either: the dedicated table has a real foreign
key, the shared one never had one.

Both migrations are called with the live app registry here. ``forwards`` and
``backwards`` take ``apps`` as their first argument and do nothing to the
database which this test does not run inside the transaction that Django rolls
back for every test.
"""
import importlib

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from guardian.models import GroupObjectPermission, UserObjectPermission

from accounts.models.guardian import (
    GroupGroupObjectPermission, GroupUserObjectPermission,
    OrganizationGroupObjectPermission, OrganizationUserObjectPermission)
from accounts.models.groups import Organization
from registry.models.guardian import (
    WebMapServiceGroupObjectPermission, WebMapServiceUserObjectPermission)
from registry.models.service import WebMapService

#: the two migrations which move the rows, by their module name
REGISTRY_MOVE = importlib.import_module(
    "registry.migrations.0030_move_generic_object_permissions_to_direct_tables")
ACCOUNTS_MOVE = importlib.import_module(
    "accounts.migrations.0003_move_generic_object_permissions_to_direct_tables")

#: an organization which the deployment does not have
GONE = "999999"


class ObjectPermissionMoveTestCase(TestCase):
    """What the two data migrations carry with them and what they leave"""

    fixtures = ["test_users.json", "test_keywords.json", "test_wms.json"]

    def setUp(self):
        self.user = get_user_model().objects.get(username="User2")
        self.group = Group.objects.get(name="Group1")
        self.organization = Organization.objects.create(name="Moved Organization")
        self.service = WebMapService.objects.first()

    def shared_rows(self):
        """One row of every shape which lives in a deployment's shared tables

        Returns:
            list: the rows which were written, so a test can name them
        """
        permissions = {
            codename: Permission.objects.get(codename=codename)
            for codename in ("view_webmapservice", "view_organization",
                             "view_group", "view_user")}
        rows = [
            # a service: named by a uuid, both kinds of actor, a model with a
            # table of its own since 0021
            UserObjectPermission.objects.create(
                user=self.user, permission=permissions["view_webmapservice"],
                content_object=self.service),
            GroupObjectPermission.objects.create(
                group=self.group, permission=permissions["view_webmapservice"],
                content_object=self.service),
            # an organization and its groups: named by an integer, both kinds of
            # actor, a model with a table of its own since 0002
            UserObjectPermission.objects.create(
                user=self.user, permission=permissions["view_organization"],
                content_object=self.organization),
            GroupObjectPermission.objects.create(
                group=self.group, permission=permissions["view_organization"],
                content_object=self.organization),
            GroupObjectPermission.objects.create(
                group=self.group, permission=permissions["view_group"],
                content_object=self.group),
            # a user: a uuid, but no model the bootstrap grants on, so no table
            UserObjectPermission.objects.create(
                user=self.user, permission=permissions["view_user"],
                content_object=self.user),
        ]
        # an organization which the deployment deleted before the migration.
        # Guardian derives the content type of a row from the object it is given,
        # so the text of a vanished object is only reachable by writing it after
        # the row exists - which is how a delete leaves a row behind
        gone = GroupObjectPermission.objects.create(
            group=Group.objects.get(name="Group2"),
            permission=permissions["view_organization"],
            content_object=self.organization)
        GroupObjectPermission.objects.filter(pk=gone.pk).update(object_pk=GONE)
        gone.object_pk = GONE
        rows.append(gone)
        return rows

    def move_forwards(self):
        REGISTRY_MOVE.forwards(django_apps, None)
        ACCOUNTS_MOVE.forwards(django_apps, None)

    def move_backwards(self):
        REGISTRY_MOVE.backwards(django_apps, None)
        ACCOUNTS_MOVE.backwards(django_apps, None)

    def test_forwards_moves_the_grants_of_a_model_with_a_table_of_its_own(
            self):
        """Every moved row answers from its own table afterwards"""
        self.shared_rows()

        self.move_forwards()

        self.assertTrue(WebMapServiceUserObjectPermission.objects.filter(
            user=self.user, content_object=self.service,
            permission__codename="view_webmapservice").exists())
        self.assertTrue(WebMapServiceGroupObjectPermission.objects.filter(
            group=self.group, content_object=self.service,
            permission__codename="view_webmapservice").exists())
        self.assertTrue(OrganizationUserObjectPermission.objects.filter(
            user=self.user, content_object=self.organization,
            permission__codename="view_organization").exists())
        self.assertTrue(OrganizationGroupObjectPermission.objects.filter(
            group=self.group, content_object=self.organization,
            permission__codename="view_organization").exists())
        self.assertTrue(GroupGroupObjectPermission.objects.filter(
            group=self.group, content_object=self.group,
            permission__codename="view_group").exists())

    def test_forwards_leaves_what_cannot_move(self):
        """A model without a table of its own and an object which is gone stay

        Both would lose their meaning in a dedicated table: the first has no
        table at all, the second can not be named by a foreign key.
        """
        self.shared_rows()

        self.move_forwards()

        self.assertTrue(UserObjectPermission.objects.filter(
            object_pk=str(self.user.pk),
            permission__codename="view_user").exists(),
            "the grant of a model without a dedicated table was moved away")
        self.assertTrue(GroupObjectPermission.objects.filter(
            object_pk=GONE).exists(),
            "the grant of an object which does not exist was moved away")

    def test_nothing_moves_twice(self):
        """The shared tables hold the moved rows no longer

        A row which stayed behind would be answered a second time by the lookup
        of a model which does have a table of its own, and a second run of the
        migration would find nothing to do.
        """
        rows = self.shared_rows()
        moved = [row.pk for row in rows
                 if str(row.object_pk) not in (GONE, str(self.user.pk))]

        self.move_forwards()
        left = set(UserObjectPermission.objects.filter(
            pk__in=moved).values_list("pk", flat=True)) | set(
            GroupObjectPermission.objects.filter(
                pk__in=moved).values_list("pk", flat=True))

        self.assertEqual(left, set())

        # a second run has nothing left to move and changes nothing
        moved_count = (
            WebMapServiceUserObjectPermission.objects.count()
            + WebMapServiceGroupObjectPermission.objects.count()
            + OrganizationUserObjectPermission.objects.count()
            + OrganizationGroupObjectPermission.objects.count()
            + GroupUserObjectPermission.objects.count()
            + GroupGroupObjectPermission.objects.count())
        self.move_forwards()
        self.assertEqual(moved_count, (
            WebMapServiceUserObjectPermission.objects.count()
            + WebMapServiceGroupObjectPermission.objects.count()
            + OrganizationUserObjectPermission.objects.count()
            + OrganizationGroupObjectPermission.objects.count()
            + GroupUserObjectPermission.objects.count()
            + GroupGroupObjectPermission.objects.count()))

    def shape_of_shared_table(self):
        """The rows of guardian's shared tables in a comparable shape

        Read from the database, because a row which was just created still holds
        the object itself in ``object_pk`` and not its text.

        Returns:
            set: one tuple per row, without the primary key - a row which moves
                and comes back does not keep it
        """
        return {(row.__class__.__name__, getattr(row, "user_id", None),
                 getattr(row, "group_id", None), row.permission_id,
                 row.content_type_id, str(row.object_pk))
                for row in list(UserObjectPermission.objects.all())
                + list(GroupObjectPermission.objects.all())}

    def test_backwards_moves_the_grants_back(self):
        """The reverse is what a deployment needs to undo the move"""
        self.shared_rows()
        wanted = self.shape_of_shared_table()

        self.move_forwards()
        self.move_backwards()

        now = self.shape_of_shared_table()
        # the grants which the bootstrap of the organization in setUp wrote are
        # in the dedicated tables before the move, so the reverse brings them
        # back too: what this test seeded has to be back, and nothing may stay
        self.assertTrue(wanted <= now,
                        f"missing after the reverse: {wanted - now}")
        self.assertEqual(
            WebMapServiceGroupObjectPermission.objects.count()
            + WebMapServiceUserObjectPermission.objects.count()
            + OrganizationGroupObjectPermission.objects.count()
            + OrganizationUserObjectPermission.objects.count()
            + GroupGroupObjectPermission.objects.count()
            + GroupUserObjectPermission.objects.count(), 0)
