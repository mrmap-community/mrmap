"""Pins the rule #864 states: a permission receiver of this app survives a fixture.

``loaddata`` does emit ``post_save``. Django's deserializer does not call
``Model.save()``, it calls ``models.Model.save_base(self.object, using=using,
raw=True)``, and ``save_base`` forwards that to the signal - so a receiver sees
``created=True`` **and** ``raw=True`` for every row a fixture writes, and only
``raw`` tells the loaded row apart from a creation. What that costs without the
guard is measured in #864: one row of an organization fixture becomes four
groups and their object grants, and because the dump of a deployment contains
the groups which were created for its organizations, the second ``loaddata`` of
the same dump collides on the unique name of ``auth_group``.

#862 gave the guard to both receivers of ``accounts/signals.py`` and #729 pinned
what they do with a loaded row: an organization gets no groups and a service no
grants. This module adds the two halves which keep that state for the receivers
#731, #732 and #734 will write:

* the rule as an executable check - a receiver this app connects to ``post_save``
  or ``pre_save`` without the ``raw`` parameter fails here, before it can ship,
* the duplication the guard is really about - a fixture which *is* a dump of a
  deployment, an organization together with the groups and grants that
  deployment already carries, loads its own rows and nothing else, twice in a
  row.

The exemptions named in the docstring of ``accounts/signals.py`` (a receiver of
``post_migrate``, a grant inside ``Model.save()``) cannot run during a
``loaddata`` and are not scanned by the check below.
"""
import functools
import inspect
import weakref

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db.models.signals import post_save, pre_save
from django.test import TestCase
from guardian.models import GroupObjectPermission, UserObjectPermission

from accounts.models.guardian import (GroupGroupObjectPermission,
                                      GroupUserObjectPermission,
                                      OrganizationGroupObjectPermission,
                                      OrganizationUserObjectPermission)
from accounts.models.groups import Organization
from accounts.signals import (handle_organization_creation,
                              handle_secured_model_creation)
from registry.models.guardian import (
    WebFeatureServiceGroupObjectPermission,
    WebMapServiceGroupObjectPermission)
from registry.models.service import WebFeatureService, WebMapService

#: the fixture which is a dump of a deployment, see the comment in that file
DEPLOYED_ORGANIZATION_FIXTURE = "test_deployed_organization"

#: the name of the organization which that fixture loads
DEPLOYED_ORGANIZATION = "Deployed Organization"

#: the groups ``handle_organization_creation`` creates for an organization
BOOTSTRAP_GROUPS = ("Administrators", "Members",
                    "webmapservice Admins", "webfeatureservice Admins")

#: the grant rows ``test_deployed_organization.json`` declares: four on the
#: organization itself and two on each of its two administering model groups
DUMP_ORGANIZATION_GRANTS = 4
DUMP_GROUP_GRANTS = 4

#: the log channel of the application, see ``settings.ROOT_LOGGER``
LOGGER = "MrMap.root"

#: the signals whose ``send`` hands a receiver the ``raw`` argument of
#: ``save_base``, and which a ``loaddata`` therefore emits with ``raw=True``
RAW_BEARING_SIGNALS = (post_save, pre_save)

#: the package whose receivers the rule of #864 belongs to
ACCOUNTS_PACKAGE = "accounts"

#: receivers exempt from the rule, by qualified name and with the reason why
#: they cannot run during a ``loaddata``. Empty: the accounts app connects no
#: receiver to a raw bearing signal which may not see ``raw``. An exemption
#: added here needs the reason, not only the name.
RAW_GUARD_EXEMPT = {}


def grant_rows():
    """Every row a permission grant of this app can live in, counted per table.

    Both the dedicated guardian tables of the models the bootstrap grants on
    and guardian's shared tables are asked: a grant which a receiver duplicates
    during a ``loaddata`` has to show up in one of them, wherever guardian
    answers it from. The global permissions a group holds are counted as well,
    because ``handle_secured_model_creation`` adds ``add_<model>`` to the
    administering group as part of a grant.

    Returns:
        dict: table label -> row count, plus the global group permissions
    """
    tables = {
        model._meta.label: model.objects.count() for model in (
            OrganizationGroupObjectPermission, OrganizationUserObjectPermission,
            GroupGroupObjectPermission, GroupUserObjectPermission,
            WebMapServiceGroupObjectPermission,
            WebFeatureServiceGroupObjectPermission,
            GroupObjectPermission, UserObjectPermission)}
    tables["auth.Group.permissions"] = \
        Group.permissions.through.objects.count()
    return tables


def connected_receiver(entry):
    """The receiver callable of one entry of ``Signal.receivers``.

    The arity of that entry is a Django internal which has changed before - it
    is a four-tuple in the 6.0 this project runs on - and the entry holds the
    receiver either directly or as a live weakref, so what identifies it is
    being a function or a method rather than a position.
    Model classes are excluded on purpose: a sender kept by weakref is callable
    too, but it is never the receiver of a signal.

    Args:
        entry: one element of ``signal.receivers``

    Returns:
        callable or None: the connected receiver, None if it already died
    """
    candidates = entry if isinstance(entry, tuple) else (entry,)
    for candidate in candidates:
        unwrapped = (candidate() if isinstance(candidate, weakref.ref)
                     else candidate)
        if (inspect.isfunction(unwrapped) or inspect.ismethod(unwrapped)
                or isinstance(unwrapped, functools.partial)):
            return unwrapped
    return None


def accounts_receivers(signal):
    """Every receiver currently connected to ``signal`` by the accounts app.

    ``Signal.receivers`` names the sender only by ``id()`` - Django 6 removed
    the ``receivers_for()`` reading which resolved it - so the reading is by the
    module of the receiver, which is the scope of the rule anyway: whatever
    ``accounts`` connects, wherever it connects it.

    Args:
        signal: the signal to read the connections of

    Returns:
        dict: qualified name -> callable of every connected receiver
    """
    found = {}
    for entry in signal.receivers:
        receiver = connected_receiver(entry)
        if receiver is None:
            continue
        target = inspect.unwrap(receiver)
        module = getattr(target, "__module__", "") or ""
        if not module.startswith(ACCOUNTS_PACKAGE):
            continue
        found[f"{module}.{getattr(target, '__qualname__', '?')}"] = target
    return found


class ReceiverTakesRawTestCase(TestCase):
    """The rule of #864 as a check, covering receivers which do not exist yet."""

    def test_every_receiver_of_the_accounts_app_takes_raw(self):
        """A connected receiver without the parameter may not pass review"""
        connected = {}
        for signal in RAW_BEARING_SIGNALS:
            connected.update(accounts_receivers(signal))

        # the reading has to include what is there, else this test would also
        # pass for an app which simply connected nothing at all
        self.assertIn("accounts.signals.handle_organization_creation", connected)
        self.assertIn("accounts.signals.handle_secured_model_creation",
                      connected)

        without_guard = sorted(
            name for name, receiver in connected.items()
            if "raw" not in inspect.signature(receiver).parameters
            and name not in RAW_GUARD_EXEMPT)
        self.assertEqual(
            without_guard, [],
            "a receiver of the accounts app is connected to a raw bearing "
            "signal without taking raw. loaddata does emit post_save with "
            "created=True (#864), so such a receiver creates or grants for "
            "every row of every fixture: return early when raw is true, or "
            "name it in RAW_GUARD_EXEMPT with the reason it cannot run "
            "during a loaddata.")


class ReceiverCalledWithRawTestCase(TestCase):
    """What a receiver does with a loaded row: nothing, even where it could act."""

    def test_the_organization_bootstrap_creates_nothing_for_a_loaded_row(self):
        """The guard answers before its first write, not instead of one

        The instance is deliberately unsaved: a ``loaddata`` hands the receiver
        the instance it just deserialized, and the guard must not need a row to
        look at.
        """
        loaded = Organization(name="Raw Organization")
        before = grant_rows()

        handle_organization_creation(
            sender=Organization, instance=loaded, created=True, raw=True)

        self.assertFalse(
            Group.objects.filter(
                name__startswith="Raw Organization").exists(),
            "the bootstrap created groups for an instance handed raw=True")
        self.assertEqual(
            grant_rows(), before,
            "the bootstrap granted something for an instance handed raw=True")

    def test_the_service_bootstrap_grants_and_logs_nothing_for_a_loaded_row(
            self):
        """An owner in memory is exactly what the guard has to outrule

        Without the guard this call reaches the grant: the administering group
        of the organization exists, the instance names its owner and carries a
        primary key, so it is the situation of #862 - and ``raw`` is the only
        argument which says that nothing was really registered.
        """
        organization = Organization.objects.create(name="Raw Guard Org")
        admins = Group.objects.get(
            name=f"Raw Guard Org {WebMapService._meta.model_name} Admins")

        loaded = WebMapService(title="Loaded WMS")
        loaded.pk = "11111111-2222-3333-4444-555555555555"
        loaded.owner = organization

        with self.assertNoLogs(LOGGER, level="WARNING"):
            handle_secured_model_creation(
                sender=WebMapService, instance=loaded, created=True, raw=True)

        self.assertFalse(
            WebMapServiceGroupObjectPermission.objects.filter(
                content_object_id=loaded.pk).exists())
        self.assertFalse(
            admins.permissions.filter(codename="add_webmapservice").exists(),
            "the administering group was given the right to register services "
            "for a service which a fixture loaded")


class DeployedOrganizationDumpTestCase(TestCase):
    """A fixture which is a dump of a deployment loads exactly its own rows."""

    def test_a_deployment_dump_grows_no_groups_and_no_grants(self):
        """The dump already carries what the bootstrap would create

        ``test_organizations.json`` loads an organization on its own; a dump of
        a deployment additionally carries the four groups #862's receiver
        created for it and the grants of those groups. A receiver without the
        guard adds a second set of both (#864).
        """
        before = grant_rows()
        call_command("loaddata", DEPLOYED_ORGANIZATION_FIXTURE, verbosity=0)

        organization = Organization.objects.get(name=DEPLOYED_ORGANIZATION)
        self.assertEqual(
            sorted(
                Group.objects.filter(
                    name__startswith=DEPLOYED_ORGANIZATION)
                .values_list("name", flat=True)),
            sorted([DEPLOYED_ORGANIZATION] + [
                f"{DEPLOYED_ORGANIZATION} {suffix}"
                for suffix in BOOTSTRAP_GROUPS]),
            "loading a deployment's organization created or dropped groups")

        self.assertEqual(
            set(OrganizationGroupObjectPermission.objects.filter(
                content_object=organization).values_list(
                    "group__name", "permission__codename")),
            {("Deployed Organization Administrators", "view_organization"),
             ("Deployed Organization Administrators", "change_organization"),
             ("Deployed Organization Members", "view_organization"),
             ("Deployed Organization Members",
              "can_publish_for_organization")},
            "the grants of the dump are not the grants of the dump any more")

        after = grant_rows()
        self.assertEqual(
            after["accounts.OrganizationGroupObjectPermission"]
            - before["accounts.OrganizationGroupObjectPermission"],
            DUMP_ORGANIZATION_GRANTS,
            "loading an organization of a deployment added grants of its own")
        self.assertEqual(
            after["accounts.GroupGroupObjectPermission"]
            - before["accounts.GroupGroupObjectPermission"],
            DUMP_GROUP_GRANTS,
            "loading the administering groups of a deployment added grants of "
            "their own")
        self.assertEqual(
            after["auth.Group.permissions"], before["auth.Group.permissions"],
            "a loaded group was given global permissions, which only the "
            "bootstrap of an ORM creation does")

    def test_loading_the_dump_a_second_time_changes_nothing(self):
        """The collision #864 measures: a dump is loaded more than once

        On the second load a receiver without the guard recreates the groups of
        every organization of the dump, which then collide on the unique name of
        ``auth_group`` - so this asserts that nothing moves at all.
        """
        call_command("loaddata", DEPLOYED_ORGANIZATION_FIXTURE, verbosity=0)
        after_first_load = grant_rows()

        call_command("loaddata", DEPLOYED_ORGANIZATION_FIXTURE, verbosity=0)

        self.assertEqual(grant_rows(), after_first_load)
        self.assertEqual(
            Group.objects.filter(
                name__startswith=DEPLOYED_ORGANIZATION).count(),
            len(BOOTSTRAP_GROUPS) + 1)
        self.assertEqual(
            Organization.objects.filter(
                name=DEPLOYED_ORGANIZATION).count(), 1)


class LoadedServiceStaysQuietTestCase(TestCase):
    """The other side of the bootstrap: a loaded service is never registered."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json"]

    #: the WFS of ``test_wfs.json``, which is loaded inside the test
    LOADED_WFS = "9cc4889d-0cd4-4c3b-8975-58de6d30db41"

    def build(self, title, template_pk):
        """A WFS like the one the registration task persists

        Same field copying as ``test_service_object_grants``: only a service
        created through the ORM reaches the receiver ungarded.
        """
        template = WebFeatureService.objects.get(pk=template_pk)
        return WebFeatureService(
            title=title,
            service_url="https://www.example.com/service",
            version=template.version,
            origin=template.origin,
            metadata_contact=template.metadata_contact,
            service_contact=template.service_contact)

    def test_a_loaded_service_leaves_the_receiver_quiet(self):
        """The guard, not the missing owner, is what keeps it quiet

        ``handle_secured_model_creation`` warns once for every service it cannot
        grant, and it is reached for a loaded service unless ``raw`` returned
        first. The class fixtures hold no service: the only save inside the
        block is the one of the fixture rows.
        """
        with self.assertNoLogs(LOGGER, level="WARNING"):
            call_command("loaddata", "test_wfs.json", verbosity=0)

        self.assertEqual(
            WebFeatureServiceGroupObjectPermission.objects.filter(
                content_object_id=self.LOADED_WFS).count(), 0)

    def test_the_same_service_created_through_the_orm_does_warn(self):
        """The contrast: same row, same receiver, ``raw`` false

        No resource model stores an owner, so acting means the warning here and
        no grant (#728 stopped the receiver from crashing on that assumption).
        """
        call_command("loaddata", "test_wfs.json", verbosity=0)

        with self.assertLogs(LOGGER, level="WARNING") as logged:
            self.build("Created WFS", self.LOADED_WFS).save()

        message = "".join(logged.output).lower()
        self.assertIn("webfeatureservice", message)
        self.assertIn("owner", message)
        self.assertEqual(
            WebFeatureServiceGroupObjectPermission.objects.count(), 0)
