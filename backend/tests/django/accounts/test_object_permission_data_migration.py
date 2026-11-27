"""Moves the permissions guardian shared into the tables of their own.

The migrations ``registry/0031`` and ``accounts/0003`` carried the rows which
a deployment already stored in guardian's shared tables into the dedicated
tables of their model, and ``registry/0045`` did the same for the models #863
left open: the map applications, their layers, the monitoring settings of a
web map service and the catalogues. The rebuilt chain (#1850) retires these
three nodes - a fresh install it migrates never held rows in the shared
tables to move - but their meaning is what this module tests, so the
``RunPython`` operations of the deleted nodes are ported below: the code is
the one the nodes carried, only its home moved. Guardian answers a model with
such a table only from it, so a row which does not move is a grant which stops
working, and a row naming an object which is gone may not move either: the
dedicated table has a real foreign key, the shared one never had one.

All three ports are called with the live app registry here. The ported code
takes ``apps`` as its first argument and does nothing to the database which
this test does not run inside the transaction that Django rolls back for every
test.
"""
from functools import partial

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import migrations
from django.test import TestCase
from guardian.models import GroupObjectPermission, UserObjectPermission

from accounts.models.guardian import (
    GroupGroupObjectPermission, GroupUserObjectPermission,
    OrganizationGroupObjectPermission, OrganizationUserObjectPermission)
from accounts.models.groups import Organization
from registry.models.guardian import (
    CatalogueServiceGroupObjectPermission, MapContextGroupObjectPermission,
    MapContextLayerGroupObjectPermission, MapContextUserObjectPermission,
    WebMapServiceGroupObjectPermission,
    WebMapServiceMonitoringSettingGroupObjectPermission,
    WebMapServiceUserObjectPermission)
from registry.models.mapcontext import MapContext, MapContextLayer
from registry.models.monitoring import WebMapServiceMonitoringSetting
from registry.models.service import CatalogueService, WebMapService

#: guardian's shared tables, one per kind of actor - the same constant the
#: three deleted nodes carried
SHARED = {
    'user': 'UserObjectPermission',
    'group': 'GroupObjectPermission',
}

#: the rows one statement writes or removes, so that no statement names every
#: permission of a deployment in one list of values
BATCH_SIZE = 500

#: what each node moves, spelled as the node spelled it: app label and model
#: of the objects whose permissions move and, for every kind of actor, the
#: name of the actor and the model of the table it moves into. The entries
#: ``registry/0045`` spelled without an app label (its app is ``APP_LABEL``
#: there) carry the label here, so one loop shape serves all
REGISTRY_MOVED = [
    ('registry', 'webmapservice', 'user', 'WebMapServiceUserObjectPermission'),
    ('registry', 'webmapservice', 'group', 'WebMapServiceGroupObjectPermission'),
    ('registry', 'webfeatureservice', 'user',
     'WebFeatureServiceUserObjectPermission'),
    ('registry', 'webfeatureservice', 'group',
     'WebFeatureServiceGroupObjectPermission'),
]

# an organization is a group of its own table, so it is named by its own
# primary key, which is the one-to-one key to ``auth_group``
ACCOUNTS_MOVED = [
    ('accounts', 'organization', 'user', 'OrganizationUserObjectPermission'),
    ('accounts', 'organization', 'group', 'OrganizationGroupObjectPermission'),
    ('auth', 'group', 'user', 'GroupUserObjectPermission'),
    ('auth', 'group', 'group', 'GroupGroupObjectPermission'),
]

#: the models of #863, which the deleted ``registry/0045`` moved
REMAINING_MOVED = [
    ('registry', 'catalogueservice', 'user',
     'CatalogueServiceUserObjectPermission'),
    ('registry', 'catalogueservice', 'group',
     'CatalogueServiceGroupObjectPermission'),
    ('registry', 'mapcontext', 'user', 'MapContextUserObjectPermission'),
    ('registry', 'mapcontext', 'group', 'MapContextGroupObjectPermission'),
    ('registry', 'mapcontextlayer', 'user',
     'MapContextLayerUserObjectPermission'),
    ('registry', 'mapcontextlayer', 'group',
     'MapContextLayerGroupObjectPermission'),
    ('registry', 'webmapservicemonitoringsetting', 'user',
     'WebMapServiceMonitoringSettingUserObjectPermission'),
    ('registry', 'webmapservicemonitoringsetting', 'group',
     'WebMapServiceMonitoringSettingGroupObjectPermission'),
]


def content_type(apps, app_label, model):
    """The content type of a model, or None if the deployment never had one"""
    return apps.get_model('contenttypes', 'ContentType').objects.filter(
        app_label=app_label, model=model).first()


def objects_named(target, texts):
    """The texts which name an object of the given model which still exists

    The shared table never had a foreign key, so a row can name an object which
    is gone, or name nothing at all: a text the primary key of the model can not
    read is the same case as a text naming a deleted object.

    Args:
        target: the model whose primary key reads the texts
        texts: the ``object_pk`` values of the rows which want to move

    Returns:
        dict: the primary key of every object named by one of the texts, by the
            text which names it
    """
    named = {}
    for text in texts:
        try:
            named[text] = target._meta.pk.to_python(text)
        except (ValidationError, ValueError):
            continue
    if not named:
        return {}
    existing = set(target.objects.filter(
        pk__in=list(named.values())).values_list('pk', flat=True))
    return {text: pk for text, pk in named.items() if pk in existing}


def delete_in_batches(model, pks):
    """Removes the rows of a model by their primary keys, in batches"""
    for start in range(0, len(pks), BATCH_SIZE):
        model.objects.filter(pk__in=pks[start:start + BATCH_SIZE]).delete()


def forwards(apps, schema_editor, app_label, moved,
             by_permission_content_type=False):
    """Carries the rows of guardian's shared tables into the dedicated ones

    The code of the deleted nodes. ``app_label`` names the app which holds
    the dedicated tables and ``moved`` the rows this node carries; the flag
    is what told ``registry/0045`` apart: it decided the destination by the
    content type of the *permission* - what a lookup of the model filters on
    - while ``registry/0031`` and ``accounts/0003`` filtered the shared table
    by the content type the row carries.
    """
    for target_label, target_model, actor, direct_model in moved:
        content = content_type(apps, target_label, target_model)
        if content is None:
            continue
        target = apps.get_model(target_label, target_model)
        shared = apps.get_model('guardian', SHARED[actor])
        direct = apps.get_model(app_label, direct_model)

        if by_permission_content_type:
            granted = list(shared.objects.filter(
                permission__content_type=content))
        else:
            granted = list(shared.objects.filter(content_type=content))
        objects = objects_named(target, [row.object_pk for row in granted])
        carried = [row for row in granted if row.object_pk in objects]
        if not carried:
            continue

        direct.objects.bulk_create(
            [direct(**{
                f'{actor}_id': getattr(row, f'{actor}_id'),
                'permission_id': row.permission_id,
                'content_object_id': objects[row.object_pk]})
             for row in carried],
            batch_size=BATCH_SIZE, ignore_conflicts=True)
        delete_in_batches(shared, [row.pk for row in carried])


def backwards(apps, schema_editor, app_label, moved):
    """Carries the rows of the dedicated tables back into the shared ones

    The reverse of the deleted nodes: every row of the dedicated table goes
    back to the shared one, named by the text of the primary key it was a
    foreign key to.
    """
    for target_label, target_model, actor, direct_model in moved:
        content = content_type(apps, target_label, target_model)
        if content is None:
            continue
        shared = apps.get_model('guardian', SHARED[actor])
        direct = apps.get_model(app_label, direct_model)

        granted = list(direct.objects.all())
        if not granted:
            continue
        shared.objects.bulk_create(
            [shared(**{
                f'{actor}_id': getattr(row, f'{actor}_id'),
                'permission_id': row.permission_id,
                'content_type': content,
                'object_pk': row.content_object_id})
             for row in granted],
            batch_size=BATCH_SIZE, ignore_conflicts=True)
        delete_in_batches(direct, [row.pk for row in granted])


class RegistryMoveMigration(migrations.Migration):
    """Port of the deleted ``registry/0031_move_generic_object_permissions_to
    _direct_tables``: the services moved into their tables of their own."""

    operations = [migrations.RunPython(
        partial(forwards, app_label='registry', moved=REGISTRY_MOVED),
        partial(backwards, app_label='registry', moved=REGISTRY_MOVED))]


class AccountsMoveMigration(migrations.Migration):
    """Port of the deleted ``accounts/0003_move_generic_object_permissions_to
    _direct_tables``: the organizations and the groups of auth moved."""

    operations = [migrations.RunPython(
        partial(forwards, app_label='accounts', moved=ACCOUNTS_MOVED),
        partial(backwards, app_label='accounts', moved=ACCOUNTS_MOVED))]


class RemainingMoveMigration(migrations.Migration):
    """Port of the deleted ``registry/0045_move_generic_object_permissions_of
    _the_remaining_models``: the models #863 left open moved, reading the
    shared table by the content type of the permission."""

    operations = [migrations.RunPython(
        partial(forwards, app_label='registry', moved=REMAINING_MOVED,
                by_permission_content_type=True),
        partial(backwards, app_label='registry', moved=REMAINING_MOVED))]


#: the three ports, addressed as the deleted modules were
REGISTRY_MOVE = RegistryMoveMigration
ACCOUNTS_MOVE = AccountsMoveMigration
REMAINING_MOVE = RemainingMoveMigration

#: an organization which the deployment does not have
GONE = "999999"

#: the catalogue, the map application and its layer, and the monitoring setting
#: of the fixtures, which the second move test grants on
CATALOGUE = "9cc4889d-0cd4-4c3b-8975-58de6d30db41"
MAPCONTEXT = 1
LAYER = 6
MONITORING_SETTING = 1


class ObjectPermissionMoveTestCase(TestCase):
    """What the ports of the two data migrations carry with them and what
    they leave"""

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
            # table of its own
            UserObjectPermission.objects.create(
                user=self.user, permission=permissions["view_webmapservice"],
                content_object=self.service),
            GroupObjectPermission.objects.create(
                group=self.group, permission=permissions["view_webmapservice"],
                content_object=self.service),
            # an organization and its groups: named by an integer, both kinds of
            # actor, a model with a table of its own
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
        REGISTRY_MOVE.operations[0].code(django_apps, None)
        ACCOUNTS_MOVE.operations[0].code(django_apps, None)

    def move_backwards(self):
        REGISTRY_MOVE.operations[0].reverse_code(django_apps, None)
        ACCOUNTS_MOVE.operations[0].reverse_code(django_apps, None)

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


class RemainingModelsMoveTestCase(TestCase):
    """What the move of the models of #863 carries and what it leaves.

    The tables of these models are the youngest of the dedicated ones, so a
    deployment which has grants on them - or a fixture which wrote them the way
    ``test_mapcontext.json`` did - answers them from the shared table until this
    port moves them. Two readings of a row matter here:

    * a lookup of a model narrows the shared table by ``permission__content_type``,
      so the model whose table a row moves into is the one of the *permission*.
      The fixtures of this repository hold rows whose two content types disagree -
      a permission of a layer naming a map application - and those rows really
      grant on the layer;
    * a text the primary key of that model cannot read names nothing, and stays
      behind like the grant of an object which is gone.
    """

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json", "test_csw.json", "test_mapcontext.json",
                "test_monitoring.json"]

    def setUp(self):
        self.user = get_user_model().objects.get(username="User2")
        self.group = Group.objects.get(name="Group1")
        self.catalogue = CatalogueService.objects.get(pk=CATALOGUE)
        self.mapcontext = MapContext.objects.get(pk=MAPCONTEXT)
        self.layer = MapContextLayer.objects.get(pk=LAYER)
        self.setting = WebMapServiceMonitoringSetting.objects.get(
            pk=MONITORING_SETTING)

    def permission(self, codename, model):
        return Permission.objects.get(
            codename=codename, content_type__model=model)

    def shared_rows(self):
        """One row of every shape this migration has to tell apart

        Returns:
            list: the rows which were written
        """
        rows = [
            # a catalogue: named by a uuid, granted on by no code today and
            # answered from its own table
            GroupObjectPermission.objects.create(
                group=self.group,
                permission=self.permission(
                    "view_catalogueservice", "catalogueservice"),
                content_object=self.catalogue),
            # a map application: named by an integer, the shape which breaks the
            # lookup of a model with a uuid primary key
            UserObjectPermission.objects.create(
                user=self.user,
                permission=self.permission("change_mapcontext", "mapcontext"),
                content_object=self.mapcontext),
            # the monitoring setting of a web map service
            GroupObjectPermission.objects.create(
                group=self.group,
                permission=self.permission(
                    "change_webmapservicemonitoringsetting",
                    "webmapservicemonitoringsetting"),
                content_object=self.setting),
        ]
        # A layer grant as ``test_mapcontext.json`` wrote it: the permission
        # names the layer, the ``content_type`` of the row names the map
        # application and the text names the layer. Guardian's own save()
        # refuses this shape - it insists a permission is designed for the
        # object it points at - so the row is written the way a loaded fixture
        # writes it: created as a grant of the map application and rewritten
        # with an update, which does not ask the model.
        mismatch = GroupObjectPermission.objects.create(
            group=self.group,
            permission=self.permission("change_mapcontext", "mapcontext"),
            content_object=self.mapcontext)
        GroupObjectPermission.objects.filter(pk=mismatch.pk).update(
            permission=self.permission(
                "change_mapcontextlayer", "mapcontextlayer"),
            content_type=ContentType.objects.get_for_model(MapContext),
            object_pk=str(LAYER))
        mismatch.refresh_from_db()
        rows.append(mismatch)
        # a map application which the deployment deleted before the migration
        gone = GroupObjectPermission.objects.create(
            group=self.group,
            permission=self.permission("change_mapcontext", "mapcontext"),
            content_object=self.mapcontext)
        GroupObjectPermission.objects.filter(pk=gone.pk).update(object_pk=GONE)
        gone.object_pk = GONE
        rows.append(gone)
        # a user: a uuid, but no model which got a table, so no row which moves
        rows.append(UserObjectPermission.objects.create(
            user=self.user,
            permission=self.permission("view_user", "user"),
            content_object=self.user))
        return rows

    def move_forwards(self):
        REMAINING_MOVE.operations[0].code(django_apps, None)

    def move_backwards(self):
        REMAINING_MOVE.operations[0].reverse_code(django_apps, None)

    def test_forwards_moves_the_grants_into_the_tables_of_their_model(self):
        """Every row of a model with a new table answers from it afterwards"""
        self.shared_rows()

        self.move_forwards()

        self.assertTrue(CatalogueServiceGroupObjectPermission.objects.filter(
            group=self.group, content_object=self.catalogue,
            permission__codename="view_catalogueservice").exists())
        self.assertTrue(MapContextUserObjectPermission.objects.filter(
            user=self.user, content_object=self.mapcontext,
            permission__codename="change_mapcontext").exists())
        self.assertTrue(
            WebMapServiceMonitoringSettingGroupObjectPermission.objects.filter(
                group=self.group, content_object=self.setting,
                permission__codename="change_webmapservicemonitoringsetting")
            .exists())

    def test_a_row_whose_content_types_disagree_moves_with_its_permission(self):
        """The layer grant of a row naming the map application is a layer grant

        A lookup of a layer filters the shared table by the content type of the
        permission, so the row was always read as a grant on the layer named by
        its text - which is what the fixture meant and what its wrong
        ``content_type`` never said.
        """
        self.shared_rows()

        self.move_forwards()

        self.assertTrue(MapContextLayerGroupObjectPermission.objects.filter(
            group=self.group, content_object=self.layer,
            permission__codename="change_mapcontextlayer").exists())

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
        left = set(GroupObjectPermission.objects.filter(
            pk__in=moved).values_list("pk", flat=True)) | set(
            UserObjectPermission.objects.filter(
                pk__in=moved).values_list("pk", flat=True))

        self.assertEqual(left, set())

        tables = [
            CatalogueServiceGroupObjectPermission,
            MapContextGroupObjectPermission, MapContextUserObjectPermission,
            MapContextLayerGroupObjectPermission,
            WebMapServiceMonitoringSettingGroupObjectPermission]
        moved_count = sum(table.objects.count() for table in tables)
        self.move_forwards()
        self.assertEqual(moved_count, sum(
            table.objects.count() for table in tables))

    def shape_of_shared_table(self):
        """The rows of guardian's shared tables in a comparable shape

        Returns:
            set: one tuple per row, without the primary key - a row which moves
                and comes back does not keep it
        """
        return {(getattr(row, "user_id", None), getattr(row, "group_id", None),
                 row.permission_id, str(row.object_pk))
                for row in list(UserObjectPermission.objects.all())
                + list(GroupObjectPermission.objects.all())}

    def test_backwards_moves_the_grants_back(self):
        """The reverse is what a deployment needs to undo the move"""
        self.shared_rows()
        wanted = self.shape_of_shared_table()

        self.move_forwards()
        self.move_backwards()

        now = self.shape_of_shared_table()
        # the grants the fixtures of this test write live in the dedicated tables
        # already, so the reverse brings those back as well: what this test
        # seeded has to be back, and nothing may stay in the dedicated tables
        self.assertTrue(wanted <= now,
                        f"missing after the reverse: {wanted - now}")
        self.assertEqual(
            CatalogueServiceGroupObjectPermission.objects.count()
            + MapContextGroupObjectPermission.objects.count()
            + MapContextUserObjectPermission.objects.count()
            + MapContextLayerGroupObjectPermission.objects.count()
            + WebMapServiceMonitoringSettingGroupObjectPermission.objects.count(),
            0)
