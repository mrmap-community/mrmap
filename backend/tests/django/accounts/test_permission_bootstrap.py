"""Pins what the permission bootstrap of ``accounts.signals`` grants.

The bootstrap is the only code which turns a creation into django-guardian
grants: ``handle_organization_creation`` shall give an organization the groups
which administer it, ``handle_secured_model_creation`` shall grant the
administering group of the owning organization view, change and delete on a
newly registered service.

Both receivers connect themselves to ``post_save`` at the bottom of that
module, so the module has to be imported for any of it to run at all. That it
never was imported is what #728 is about. Nothing noticed, because a service
which a test or a deployment loads from a fixture is saved by the deserializer
with ``raw=True`` - ``loaddata`` does emit ``post_save``, it only says that the
object is a loaded one - and both receivers answer that with doing nothing.

What the bootstrap really does, and what these tests pin down so that the role
work of #727 may change it knowingly:

* an organization created through the ORM gets its administrators and members
  group, one administering group per role-managed model and the object grants
  of ``handle_organization_creation``,
* a service created through the ORM gets **nothing**: no resource model stores
  an owner, so nothing knows which organization a new service belongs to. The
  receiver says so once in the log instead of reading an ``owner`` attribute
  which no model has,
* the models the bootstrap grants on are answered from guardian tables of their
  own, which is what keeps a grant of an integer primary key out of the table a
  lookup for a service reads.

The last test of ``ServiceCreationTestCase`` is the grant this bootstrap was
written for. It can only set ownership in memory because ownership is stored
nowhere; #733 stores it and #734 replaces the grant with the role based one.
"""
import importlib

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.test import TestCase
from guardian.models import GroupObjectPermission
from guardian.shortcuts import assign_perm, get_objects_for_user
from guardian.utils import get_group_obj_perms_model

from accounts.models.groups import Organization
from accounts.utils import get_secured_models
from registry.models.metadata import MetadataContact
from registry.models.service import CatalogueService, WebMapService

#: the log channel of the application, see ``settings.ROOT_LOGGER``
LOGGER = "MrMap.root"

#: the dedicated guardian tables and the package which has to export them, so
#: that guardian finds them instead of answering their grants generically
DEDICATED_TABLES = {
    "accounts.models": (
        "OrganizationUserObjectPermission", "OrganizationGroupObjectPermission",
        "GroupUserObjectPermission", "GroupGroupObjectPermission"),
    "registry.models": (
        "WebMapServiceUserObjectPermission",
        "WebMapServiceGroupObjectPermission",
        "WebFeatureServiceUserObjectPermission",
        "WebFeatureServiceGroupObjectPermission",
        # the third kind of service, which the reads look up although no code
        # grants on it, and the models of the grants the fixtures write (#863)
        "CatalogueServiceUserObjectPermission",
        "CatalogueServiceGroupObjectPermission",
        "MapContextUserObjectPermission",
        "MapContextGroupObjectPermission",
        "MapContextLayerUserObjectPermission",
        "MapContextLayerGroupObjectPermission",
        "WebMapServiceMonitoringSettingUserObjectPermission",
        "WebMapServiceMonitoringSettingGroupObjectPermission"),
}

#: a service of ``test_wms.json``, only used to copy the fields a service needs
TEMPLATE_WMS = "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"

ORGANIZATION_NAME = "Permission Bootstrap"

#: the fixture which loads an organization, see the comment in that file
FIXTURE_FILE = "test_organizations"

#: the name of the organization which that fixture loads
FIXTURE_ORGANIZATION = "Fixture Organization"


def object_grants(obj):
    """Every object permission a group holds on the given object.

    Guardian answers the object permissions of a model which has a table of its
    own only from that table (``accounts/models/guardian.py`` says why), so the
    model to ask is the one guardian resolves for the object.

    Args:
        obj: the object the grants are asked for

    Returns:
        queryset: the object permission rows naming the given object
    """
    model = get_group_obj_perms_model(obj)
    if model.objects.is_generic():
        return model.objects.filter(
            object_pk=str(obj.pk),
            content_type=ContentType.objects.get_for_model(obj))
    return model.objects.filter(content_object=obj)


class OrganizationCreationTestCase(TestCase):
    """What the creation of an organization through the ORM grants."""

    fixtures = ["test_users.json"]

    def test_an_organization_gets_its_administrators_and_members_group(self):
        """The organization signal is the only code which names these groups"""
        Organization.objects.create(name=ORGANIZATION_NAME)

        self.assertTrue(
            Group.objects.filter(name=f"{ORGANIZATION_NAME} Administrators").exists())
        self.assertTrue(
            Group.objects.filter(name=f"{ORGANIZATION_NAME} Members").exists())

    def test_an_organization_gets_one_administering_group_per_secured_model(
            self):
        """Groups per organization grow with the list of secured models"""
        Organization.objects.create(name=ORGANIZATION_NAME)

        for secured_model in get_secured_models():
            self.assertTrue(
                Group.objects.filter(
                    name=f"{ORGANIZATION_NAME} "
                    f"{secured_model._meta.model_name} Admins").exists(),
                f"no administering group for {secured_model.__name__}")

    def test_an_organization_is_granted_to_its_own_groups(self):
        """The members may view and publish, the administrators may also change

        The permission strings of the signal name the ``registry`` app, but
        guardian resolves a codename against the content type of the object, so
        the grants land on ``accounts``. #729 makes the strings say that too.
        """
        organization = Organization.objects.create(name=ORGANIZATION_NAME)

        codenames = set(
            object_grants(organization).values_list(
                "permission__codename", flat=True))
        self.assertEqual(
            codenames,
            {"view_organization", "change_organization",
             "can_publish_for_organization"})

        members = Group.objects.get(name=f"{ORGANIZATION_NAME} Members")
        self.assertEqual(
            set(object_grants(organization).filter(
                group=members).values_list("permission__codename", flat=True)),
            {"view_organization", "can_publish_for_organization"})

    def test_an_organization_of_a_fixture_creates_no_groups(self):
        """A loaded organization brings its own groups along

        ``loaddata`` saves what it deserialized and does emit ``post_save``, with
        ``raw=True``. A receiver which ran anyway would create the groups of every
        organization of a dump a second time, because a dump of a deployment
        contains the groups which were created for it.
        """
        call_command('loaddata', FIXTURE_FILE, verbosity=0)

        self.assertTrue(
            Organization.objects.filter(name=FIXTURE_ORGANIZATION).exists(),
            "the fixture did not load an organization at all")
        created_by_the_bootstrap = [
            f"{FIXTURE_ORGANIZATION} Administrators",
            f"{FIXTURE_ORGANIZATION} Members"] + [
            f"{FIXTURE_ORGANIZATION} {model._meta.model_name} Admins"
            for model in get_secured_models()]
        self.assertFalse(
            Group.objects.filter(name__in=created_by_the_bootstrap).exists(),
            "the bootstrap created groups for a loaded organization: "
            f"{list(Group.objects.filter(
                name__in=created_by_the_bootstrap
            ).values_list('name', flat=True))}")


class SharedObjectPermissionTableTestCase(TestCase):
    """Why the models the bootstrap grants on need a table of their own.

    Guardian stores the object permissions of *every* model in one table and
    names the object by ``content_type`` and the text of its primary key. A
    lookup for a model whose primary key is a uuid compares that text column by
    casting it to a uuid, and whether PostgreSQL evaluates the cast only for the
    rows of the looked up model or for the rows of every other model in the
    table is a decision of the query plan: with the wiring of #728 and without
    the tables of ``accounts/models/guardian.py``, the alerts endpoint answered
    ``invalid input syntax for type uuid: "1"`` for the organization
    ``post_migrate`` creates.

    An organization is named by an integer, the services by a uuid, so a grant of
    an organization may not stay in the table the services are answered from.
    """

    fixtures = ["test_users.json"]

    def test_no_grant_of_the_bootstrap_lives_in_the_shared_table(self):
        """An organization and its groups are answered from their own tables"""
        organization = Organization.objects.create(name=ORGANIZATION_NAME)

        shared = GroupObjectPermission.objects.filter(
            content_type__in=[
                ContentType.objects.get_for_model(organization),
                ContentType.objects.get_for_model(Group)])
        self.assertFalse(
            shared.exists(),
            "guardian's shared table holds an object permission of an "
            "organization or a group, which a lookup of a model with a uuid "
            "primary key may then have to cast")

    def test_a_model_without_a_table_of_its_own_answers_a_uuid_key(self):
        """The lookup of a uuid model without a table of its own still answers

        A model without a table of its own is answered from the shared table and
        takes whatever the plan does with the cast of its text column, so this is
        the read which ``/api/registry/service-alerts`` asked when the bootstrap
        was connected and the dedicated tables were not. The organization is
        granted to a group of the looking user on purpose: guardian narrows the
        shared table by the groups of that user, so a row of a group the user is
        not in would never be part of the comparison.
        """
        organization = Organization.objects.create(name=ORGANIZATION_NAME)
        assign_perm(perm='registry.view_organization',
                    user_or_group=Group.objects.get(name="Group2"),
                    obj=organization)

        visible = get_objects_for_user(
            get_user_model().objects.get(username="User2"),
            'registry.view_catalogueservice',
            klass=CatalogueService,
            accept_global_perms=False)
        self.assertEqual(list(visible), [])

    def test_the_models_of_the_dedicated_tables_belong_to_their_app(self):
        """The import which registers the tables belongs to the app, not to a test

        Guardian answers an object permission from a dedicated table only for a
        model it has in its registry, and the only code importing
        ``accounts.models.guardian`` and ``registry.models.guardian`` at runtime
        is the ``models`` package of the app - the way ``apps.py`` imports
        ``accounts.signals``.

        So this asserts the export of the package instead of a behaviour, which is
        the one thing no other test of this module can assert: the test modules
        import the two guardian modules themselves and register their models for
        the whole run, whether or not the app does it. With the export of the app
        removed, every test above stays green while every deployment answers the
        grants of an organization from the shared table again.
        """
        for package, tables in DEDICATED_TABLES.items():
            models = importlib.import_module(package)
            for table in tables:
                self.assertTrue(
                    hasattr(models, table),
                    f"{package} does not export {table}, so an application which "
                    f"imports only the package never registers that table and "
                    f"guardian answers its grants from the shared one")


class ServiceCreationTestCase(TestCase):
    """What the creation of a service through the ORM grants."""

    fixtures = ["test_users.json", "test_keywords.json", "test_wms.json"]

    def setUp(self):
        template = WebMapService.objects.get(pk=TEMPLATE_WMS)
        self.contact = MetadataContact.objects.get(pk=1)
        self.version = template.version
        self.origin = template.origin

    def build_service(self, title):
        """A service like the one the registration task persists

        Args:
            title (str): the title to give the service

        Returns:
            WebMapService: an unsaved service
        """
        return WebMapService(
            title=title,
            service_url="https://www.example.com/wms",
            version=self.version,
            origin=self.origin,
            metadata_contact=self.contact,
            service_contact=self.contact)

    def test_a_service_created_through_the_orm_names_the_missing_owner(self):
        """The receiver runs and says out loud that it found no owner

        Reading ``instance.owner`` here raised ``AttributeError`` inside
        ``post_save``, which every registration would have noticed. The receiver
        may not depend on a field which no resource model has.
        """
        with self.assertLogs(LOGGER, level="WARNING") as logged:
            self.build_service("Orphaned").save()

        message = "".join(logged.output).lower()
        self.assertEqual(len(logged.output), 1)
        self.assertIn("webmapservice", message)
        self.assertIn("owner", message)

    def test_a_service_created_through_the_orm_has_no_object_grants(self):
        """Nothing knows which organization a registered service belongs to"""
        service = self.build_service("Orphaned")
        service.save()

        self.assertFalse(object_grants(service).exists())

    def test_the_bootstrap_grants_the_administering_group_of_the_owner(self):
        """The grant this receiver was written for, with ownership set by hand

        No model stores the owner today, so ownership can only be given to the
        instance in memory. #733 stores it and #734 grants by role instead.
        """
        Organization.objects.create(name=ORGANIZATION_NAME)
        admins = Group.objects.get(
            name=f"{ORGANIZATION_NAME} {WebMapService._meta.model_name} Admins")

        service = self.build_service("Owned")
        service.owner = Organization.objects.get(name=ORGANIZATION_NAME)
        service.save()

        self.assertEqual(
            set(object_grants(service).values_list(
                "permission__codename", flat=True)),
            {"view_webmapservice", "change_webmapservice",
             "delete_webmapservice"})
        self.assertEqual(
            set(object_grants(service).values_list(
                "group__name", flat=True)), {admins.name})
        self.assertTrue(
            admins.permissions.filter(
                codename="add_webmapservice",
                content_type__app_label="registry").exists(),
            "the administering group may not register further services")
