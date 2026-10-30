"""Pins what the permission bootstrap of ``accounts.signals`` grants.

The bootstrap is the only code which turns a creation into django-guardian
grants: ``handle_organization_creation`` shall give an organization the groups
which administer it, ``handle_secured_model_creation`` shall grant the
administering group of the owning organization view, change and delete on a
newly registered service.

Both receivers connect themselves to ``post_save`` at the bottom of that
module, so the module has to be imported for any of it to run at all. That it
never was imported is what #728 is about; nothing noticed, because every
fixture loads its services with ``loaddata`` which does not emit ``post_save``.

What the bootstrap really does, and what these tests pin down so that the role
work of #727 may change it knowingly:

* an organization created through the ORM gets its administrators and members
  group, one administering group per role-managed model and the object grants
  of ``handle_organization_creation``,
* a service created through the ORM gets **nothing**: no resource model stores
  an owner, so nothing knows which organization a new service belongs to. The
  receiver says so once in the log instead of reading an ``owner`` attribute
  which no model has.

The last test describes the grant the bootstrap was written for. It can only
set ownership in memory because ownership is stored nowhere; #733 stores it and
#734 replaces the grant with the role based one.
"""
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from guardian.models import GroupObjectPermission

from accounts.models.groups import Organization
from accounts.utils import get_secured_models
from registry.models.metadata import MetadataContact
from registry.models.service import WebMapService

#: the log channel of the application, see ``settings.ROOT_LOGGER``
LOGGER = "MrMap.root"

#: a service of ``test_wms.json``, only used to copy the fields a service needs
TEMPLATE_WMS = "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"

ORGANIZATION_NAME = "Permission Bootstrap"


def object_grants(obj):
    """Every object permission a group holds on the given object.

    Args:
        obj: the object the grants are asked for

    Returns:
        queryset: the ``GroupObjectPermission`` rows naming the given object
    """
    return GroupObjectPermission.objects.filter(
        object_pk=str(obj.pk),
        content_type=ContentType.objects.get_for_model(obj))


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
