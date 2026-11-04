"""Pins what creating a secured registry object grants, and how it is looked up.

``test_permission_bootstrap.py`` pins the WebMapService side of
``handle_secured_model_creation``: a service created through the ORM with an
owner it only has in memory is granted view, change and delete to
``<owner> <model_name> Admins``. This module completes the picture for the
other side of ``SECURED_MODELS`` and for the paths around the grant:

* the same bootstrap answers for a WebFeatureService, so the grant really is
  parameterized by the model and the role name reads
  ``<owner> webfeatureservice Admins`` (#732 grants by role instead);
* a creation grants no user and no anonymous user anything: the bootstrap only
  knows the administering group, an explicit public/anonymous grant arrives
  with #739;
* the grant target is looked up by the interpolated group name, so renaming an
  organization detaches the grant path of everything created afterwards;
* ``loaddata`` does emit ``post_save`` (#864) - the spy here shows the receiver
  seeing ``created=True, raw=True`` for every loaded service - and the guard of
  the receiver is what keeps a loaded service ungranted;
* a grant of a uuid primary key lives in the dedicated table of its model,
  where ``object_pk`` is a foreign key and never the text the shared table
  stores and casts (#863), and the group membership lookup a request or
  ``notify/managers.py`` performs answers from it.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db.models.signals import post_save
from django.test import TestCase
from guardian.core import ObjectPermissionChecker
from guardian.models import GroupObjectPermission, UserObjectPermission
from guardian.shortcuts import assign_perm, get_objects_for_user
from guardian.utils import get_anonymous_user

from accounts.models.groups import Organization
from registry.models.guardian import (WebFeatureServiceGroupObjectPermission,
                                      WebFeatureServiceUserObjectPermission,
                                      WebMapServiceGroupObjectPermission,
                                      WebMapServiceUserObjectPermission)
from registry.models.service import WebFeatureService, WebMapService

#: the first WMS and the first WFS of the fixtures, only used to copy the
#: fields a created service needs (same technique as test_permission_bootstrap)
TEMPLATE_WMS = "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"
TEMPLATE_WFS = "9cc4889d-0cd4-4c3b-8975-58de6d30db41"

ORGANIZATION_NAME = "Grant Org"


def group_grant_matrix(service):
    """The (group name, codename) pairs of every group grant on a service.

    Read from guardian's *shared* table: a service grant created by the
    bootstrap never lives there (dedicated tables), so an empty matrix from
    this reading is a statement about the #863 landmine, and the dedicated
    tables are asked by their own model.
    """
    return set(GroupObjectPermission.objects.filter(
        content_type__model=service._meta.model_name).values_list(
            "group__name", "permission__codename"))


class ServiceGrantTestCaseMixin:
    """Field copying for building a service like the registration task does"""

    def build(self, model, template_pk, title):
        template = model.objects.get(pk=template_pk)
        return model(
            title=title,
            service_url="https://www.example.com/service",
            version=template.version,
            origin=template.origin,
            metadata_contact=template.metadata_contact,
            service_contact=template.service_contact)


class WfsGrantTestCase(ServiceGrantTestCaseMixin, TestCase):
    """The bootstrap answers the same way for the second secured model."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wfs.json"]

    def test_a_created_wfs_is_granted_to_the_webfeatureservice_admins_group(
            self):
        """Three object grants for the role group, added add-permission global

        Ownership can only be set in memory - no resource model stores an
        owner (#728 stopped the bootstrap from crashing on that assumption);
        #733 stores it and #734 grants by role instead of by name.
        """
        Organization.objects.create(name=ORGANIZATION_NAME)
        service = self.build(WebFeatureService, TEMPLATE_WFS, "Owned WFS")
        service.owner = Organization.objects.get(name=ORGANIZATION_NAME)
        service.save()

        rows = WebFeatureServiceGroupObjectPermission.objects.filter(
            content_object=service)
        self.assertEqual(
            {(row.group.name, row.permission.codename) for row in rows},
            {(f"{ORGANIZATION_NAME} webfeatureservice Admins", codename)
             for codename in ("view_webfeatureservice",
                              "change_webfeatureservice",
                              "delete_webfeatureservice")})
        admins = Group.objects.get(
            name=f"{ORGANIZATION_NAME} webfeatureservice Admins")
        self.assertTrue(admins.permissions.filter(
            codename="add_webfeatureservice",
            content_type__app_label="registry").exists())

    def test_no_grant_lands_in_the_shared_table(self):
        """A service grant is never the text uuid the shared table would store

        The dedicated table names the service by a foreign key, so no
        ``object_pk`` text of this grant takes part in a uuid cast - the
        landmine #863 is about.
        """
        Organization.objects.create(name=ORGANIZATION_NAME)
        service = self.build(WebFeatureService, TEMPLATE_WFS, "Owned WFS")
        service.owner = Organization.objects.get(name=ORGANIZATION_NAME)
        service.save()

        self.assertEqual(group_grant_matrix(service), set())
        self.assertEqual(
            GroupObjectPermission.objects.filter(
                content_type__model="webfeatureservice").count(), 0)
        self.assertEqual(
            WebFeatureServiceGroupObjectPermission.objects.filter(
                content_object=service).count(), 3)

    def test_the_creation_grants_no_user_and_no_anonymous_user(self):
        """There is no default grant of a new service to anybody else

        No ``UserObjectPermission`` row of any shape, and the anonymous user
        guardian maps anonymous requests onto holds nothing: today a new
        service is visible to nobody through object permissions - only the
        global permissions of ``Default-Permissions``-style groups let people
        read it. #739 introduces the explicit public/anonymous grant.
        """
        Organization.objects.create(name=ORGANIZATION_NAME)
        service = self.build(WebFeatureService, TEMPLATE_WFS, "Owned WFS")
        service.owner = Organization.objects.get(name=ORGANIZATION_NAME)
        service.save()

        self.assertEqual(
            WebFeatureServiceUserObjectPermission.objects.count(), 0)
        self.assertEqual(
            UserObjectPermission.objects.filter(
                content_type__model="webfeatureservice").count(), 0)
        checker = ObjectPermissionChecker(get_anonymous_user())
        self.assertFalse(checker.has_perm(
            'registry.view_webfeatureservice', service))

    def test_a_renamed_organization_stops_being_a_grant_target(self):
        """The lookup behind the grant is the interpolated name, not a key

        After a rename ``handle_secured_model_creation`` filters
        ``Group.objects`` by a name that was never created, says so in the log
        and grants nothing - the services created before the rename keep their
        grants, the ones after get none. #732 removes the name lookup.
        """
        organization = Organization.objects.create(name=ORGANIZATION_NAME)
        organization.name = "Renamed Grant Org"
        organization.save()

        service = self.build(WebFeatureService, TEMPLATE_WFS, "Orphaned WFS")
        service.owner = organization
        with self.assertLogs("MrMap.root", level="WARNING") as logged:
            service.save()

        message = "".join(logged.output)
        self.assertIn("has no group", message)
        self.assertIn(f"{organization.name} webfeatureservice Admins", message)
        self.assertEqual(
            WebFeatureServiceGroupObjectPermission.objects.filter(
                content_object=service).count(), 0)


class LoadedServiceTestCase(TestCase):
    """What the receivers do and do not do for a ``loaddata``."""

    fixtures = ["test_users.json", "test_keywords.json", "test_wms.json"]

    def collect_post_save(self, sender, body):
        """Run ``body`` with a spy connected to ``sender``'s post_save.

        Args:
            sender: the model whose post_save to watch
            body: callable to run while the spy is connected

        Returns:
            list: ``(pk, created, raw)`` of every signal the body emitted
        """
        seen = []

        def spy(sender, instance, created, raw, **kwargs):
            seen.append((str(instance.pk), created, raw))

        post_save.connect(spy, sender=sender, dispatch_uid="pin_loaddata_spy")
        try:
            body()
        finally:
            post_save.disconnect(
                sender=sender, dispatch_uid="pin_loaddata_spy")
        return seen

    def test_loaddata_fires_post_save_yet_grants_nothing(self):
        """The #864 premise: a loaded service is saved, with raw=True

        Django's deserializer calls ``save_base(raw=True)``, so
        ``created=True`` reaches a ``post_save`` receiver for a fixture row
        exactly as for an ORM creation; only ``raw`` tells them apart, and the
        guard of the receivers (PR #862) is what keeps a loaded service
        ungranted. #864 asks every receiver this epic writes to keep that
        guard - this is the observation both halves rest on.
        """
        seen = self.collect_post_save(
            WebFeatureService,
            lambda: call_command('loaddata', 'test_crs.json',
                                 'test_wfs.json', verbosity=0))
        self.assertIn((TEMPLATE_WFS, True, True), seen,
                      "loaddata did not emit a created, raw post_save")

        service = WebFeatureService.objects.get(pk=TEMPLATE_WFS)
        self.assertEqual(
            WebFeatureServiceGroupObjectPermission.objects.filter(
                content_object=service).count(), 0)
        self.assertEqual(group_grant_matrix(service), set())

    def test_an_orm_creation_fires_the_same_signal_unguarded(self):
        """The contrast: same receiver, raw=False, so it acts

        Without a stored owner (see test_permission_bootstrap) acting means
        the warning, not a grant; ``created`` reads the same as for the loaded
        row, which is exactly why ``raw`` is the only guard there is.
        """
        service = WebMapService(
            title="Created WMS",
            service_url="https://www.example.com/wms",
            version=WebMapService.objects.get(pk=TEMPLATE_WMS).version,
            origin=WebMapService.objects.get(pk=TEMPLATE_WMS).origin,
            metadata_contact=WebMapService.objects.get(
                pk=TEMPLATE_WMS).metadata_contact,
            service_contact=WebMapService.objects.get(
                pk=TEMPLATE_WMS).metadata_contact)

        with self.assertLogs("MrMap.root", level="WARNING"):
            seen = self.collect_post_save(WebMapService, service.save)

        self.assertIn((str(service.pk), True, False), seen)


class ServiceLookupPathTestCase(ServiceGrantTestCaseMixin, TestCase):
    """How a grant created by the bootstrap is found again."""

    fixtures = ["test_users.json", "test_keywords.json", "test_wms.json"]

    def setUp(self):
        Organization.objects.create(name=ORGANIZATION_NAME)
        self.admins = Group.objects.get(
            name=f"{ORGANIZATION_NAME} webmapservice Admins")
        self.service = self.build(
            WebMapService, TEMPLATE_WMS, "Looked Up")
        self.service.owner = Organization.objects.get(name=ORGANIZATION_NAME)
        self.service.save()
        self.member = get_user_model().objects.get(username="User2")
        self.member.groups.add(self.admins)
        self.outsider = get_user_model().objects.get(username="User1")

    def test_a_group_member_finds_the_service_by_object_permission(self):
        """The read behind a permission-scoped endpoint and notify/managers

        ``accept_global_perms=False`` narrows to the object grants; the member
        of the granted group sees the service, the non-member sees nothing -
        even though both fixture users hold the global permissions of
        ``Default-Permissions``, which this narrowing ignores (the split answer
        #727 lists; #734 makes one facade answer it).
        """
        visible = get_objects_for_user(
            self.member, 'registry.view_webmapservice',
            klass=WebMapService, accept_global_perms=False)
        self.assertIn(self.service, visible)
        outsider_visible = get_objects_for_user(
            self.outsider, 'registry.view_webmapservice',
            klass=WebMapService, accept_global_perms=False)
        self.assertNotIn(self.service, outsider_visible)
        self.assertTrue(ObjectPermissionChecker(self.member).has_perm(
            'registry.change_webmapservice', self.service))
        self.assertFalse(ObjectPermissionChecker(self.outsider).has_perm(
            'registry.change_webmapservice', self.service))
        # and the answer came from the model's own table: foreign keys, not a
        # single text object_pk column shared with integer primary keys (#863)
        self.assertEqual(
            WebMapServiceGroupObjectPermission.objects.filter(
                content_object=self.service).count(), 3)
        self.assertEqual(WebMapServiceUserObjectPermission.objects.count(), 0)
        self.assertEqual(
            GroupObjectPermission.objects.filter(
                content_type__model="webmapservice").count(), 0)

    def test_a_user_self_grant_keeps_the_text_object_pk_of_its_uuid(self):
        """``User.assign_object_perms`` - dead code, and the #863 shape of it

        Nothing calls this method today (#729 asks to cover or delete it); a
        ``User`` has a uuid primary key and no dedicated guardian table, so its
        object permissions are exactly the rows the shared table stores as
        TEXT: ``object_pk`` is ``str(uuid)``, and the lookup still answers
        because guardian narrows the shared table by the user it was asked
        for. This is the surviving corner of #863 for a model without a table
        of its own.
        """
        user = self.outsider
        user.assign_object_perms()

        rows = UserObjectPermission.objects.filter(user=user)
        self.assertEqual(
            set(rows.values_list("permission__codename", flat=True)),
            {"view_user", "change_user", "delete_user"})
        for row in rows:
            self.assertEqual(row.object_pk, str(user.pk))
        self.assertTrue(user.has_perm('accounts.view_user', user))
        assign_perm(perm='view_user', user_or_group=user, obj=user)  # idempotent
        self.assertEqual(UserObjectPermission.objects.filter(
            user=user, permission__codename='view_user').count(), 1)
