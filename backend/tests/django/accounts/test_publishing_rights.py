"""Pins the publishing rights: the grant, the request that asks for it, the filter.

Three code paths answer "who may publish for whom", and all three are in the
blast radius of #740 (role-scoped acceptance, real ``Organization.publishers``)
and #734 (one permission-resolution facade):

* ``Organization.add_publisher`` grants ``can_publish_for_organization`` on
  one organization to another, and ``Organization.can_publish_for`` reads the
  grant back - with ``accept_global_perms=False``, so the same question asked
  through ``notify/managers.py`` (which passes ``True``) has a different
  answer (#727 motivation);
* accepting a ``PublishRequest`` writes that grant through the group of the
  requesting organization's ``resource_publisher`` role (#740): in the
  direction the request states, role-scoped so leaving the role revokes at
  once, with view (and the publish capability on the carrier) written onto
  the requested organization's services and the same grants recorded on
  services registered afterwards; the request row is retired;
* the ``user_has_perm`` filter of the organizations endpoint narrows by object
  grants and ignores global permissions - a user who only holds the global
  permission sees nothing.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase
from guardian.models import UserObjectPermission
from guardian.shortcuts import assign_perm

from accounts.filters.groups import OrganizationFilterSet
from accounts.models.guardian import OrganizationGroupObjectPermission
from accounts.models.groups import Organization, PublishRequest
from accounts.models.roles import RESOURCE_PUBLISHER_ROLE, Role
from registry.models.guardian import WebMapServiceGroupObjectPermission
from registry.models.service import WebMapService

REQUESTING = "Requesting Organization"
REQUESTED = "Requested Organization"
FILTERED = "Filtered Organization"

#: the fixture service whose fields a created service copies (same technique
#: as tests/django/accounts/test_service_object_grants.py)
TEMPLATE_WMS = "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"


class PublisherGrantTestCase(TestCase):
    """What ``add_publisher`` writes and what ``can_publish_for`` reads."""

    fixtures = ["test_users.json"]

    def setUp(self):
        self.first = Organization.objects.create(name=REQUESTING)
        self.second = Organization.objects.create(name=REQUESTED)

    def test_add_publisher_grants_the_publisher_over_the_receiver(self):
        """``A.add_publisher(B)`` makes B able to publish for A

        The grant row is ``accounts.can_publish_for_organization`` (the string
        in ``add_publisher`` names the honest app already, unlike the signal's
        ``registry.*`` strings) on A, held by B's group. ``B.can_publish_for``
        lists A; ``A.can_publish_for`` stays empty - the property answers
        "which organizations am I allowed to publish for", not "who may
        publish for me".
        """
        self.first.add_publisher(self.second)

        # the grant of THIS publisher: the signal already gave the organization
        # own Members group can_publish_for_organization on it, so the row is
        # asked for by its holder
        rows = OrganizationGroupObjectPermission.objects.filter(
            content_object=self.first, group=self.second)
        self.assertEqual(
            [(row.group.name, row.permission.codename,
              row.permission.content_type.app_label) for row in rows],
            [(REQUESTED, "can_publish_for_organization", "accounts")])
        self.assertIn(self.first, self.second.can_publish_for)
        self.assertNotIn(self.second, self.first.can_publish_for)

    def test_remove_publisher_revokes_the_grant(self):
        self.first.add_publisher(self.second)
        self.first.remove_publisher(self.second)

        self.assertFalse(OrganizationGroupObjectPermission.objects.filter(
            content_object=self.first, group=self.second,
            permission__codename="can_publish_for_organization").exists())
        self.assertNotIn(self.first, self.second.can_publish_for)

    def test_add_publisher_refuses_anything_but_an_organization(self):
        with self.assertRaises(TypeError):
            self.first.add_publisher(self.first.name)

    def test_publishers_reads_both_the_legacy_and_the_role_shape(self):
        """``publishers`` is the reverse of ``can_publish_for``, in both shapes

        The legacy grant sits on the whole organization group - the granted
        group *is* an organization - and the #740 grant sits on a role group,
        which resolves through its role; the organization's own default role
        holds ``can_publish_for_organization`` over itself (bootstrap of
        #732) and is still never its own publisher answer.
        """
        self.first.add_publisher(self.second)

        self.assertIn(self.second, self.first.publishers)
        self.assertNotIn(self.first, self.first.publishers)
        self.assertNotIn(self.second, self.second.publishers)

    def test_can_publish_for_ignores_the_global_permission(self):
        """``accept_global_perms=False`` - one half of the split answer

        An organization holding the *global* ``can_publish_for_organization``
        permission publishes for nothing; ``notify/managers.py`` asks the same
        kind of question of ``get_objects_for_user`` with
        ``accept_global_perms=True``. #734 answers it once.
        """
        third = Organization.objects.create(name="Global Publisher")
        assign_perm(perm='accounts.can_publish_for_organization',
                    user_or_group=third)

        self.assertFalse(third.can_publish_for.exists())
        self.assertEqual(
            UserObjectPermission.objects.filter(
                user=get_user_model().objects.get(username="User1")).count(),
            0, "the global grant was written as an object grant")


class PublishRequestTestCase(TestCase):
    """What requesting and accepting a publishing right does."""

    fixtures = ["test_users.json", "test_keywords.json", "test_wms.json"]

    def setUp(self):
        self.requesting = Organization.objects.create(name=REQUESTING)
        self.requested = Organization.objects.create(name=REQUESTED)
        self.publisher_role = Role.objects.for_org(
            self.requesting).with_definition(RESOURCE_PUBLISHER_ROLE).get()

    def build_wms(self, title, owner):
        """A WMS like the registration task would store it, with its owner."""
        template = WebMapService.objects.get(pk=TEMPLATE_WMS)
        service = WebMapService(
            title=title,
            service_url="https://www.example.com/service",
            version=template.version,
            origin=template.origin,
            metadata_contact=template.metadata_contact,
            service_contact=template.service_contact)
        service.owner = owner
        return service

    def test_creating_a_request_only_stores_the_request(self):
        request = PublishRequest.objects.create(
            from_organization=self.requesting, to_organization=self.requested)

        self.assertIsNotNone(request.pk)
        self.assertFalse(request.is_accepted)
        self.assertIsNotNone(request.activation_until)
        self.assertFalse(self.requested.publishers.exists())
        self.assertFalse(self.requesting.can_publish_for.exists())

    def test_accepting_grants_the_requesting_publishers_role_and_eats_request(
            self):
        """Acceptance follows the direction the request states, role-scoped

        ``A`` asks to publish for ``B``; accepting writes
        ``can_publish_for_organization`` over ``B`` onto the group of
        ``A``'s ``resource_publisher`` role (#740) - not onto ``A``'s whole
        organization group, and not the reverse grant the old shortcut wrote
        - and the request row is retired: its decision lives in the grant
        rows, the way it was when ``save`` deleted it (#741 reads the
        provenance back).
        """
        request = PublishRequest.objects.create(
            from_organization=self.requesting, to_organization=self.requested)
        request.is_accepted = True
        request.save()

        self.assertFalse(
            PublishRequest.objects.filter(pk=request.pk).exists(),
            "accepting the request kept it in the database")
        rows = OrganizationGroupObjectPermission.objects.filter(
            content_object=self.requested,
            group=self.publisher_role.group,
            permission__codename="can_publish_for_organization")
        self.assertEqual(rows.count(), 1)
        self.assertIsNone(
            rows.get().granted_by,
            "a save without a decider must not invent one")
        # the honest direction: A may publish for B, not the other way round
        self.assertIn(self.requested, self.requesting.can_publish_for)
        self.assertIn(self.requesting, self.requested.publishers)
        self.assertNotIn(self.requesting, self.requested.can_publish_for)
        self.assertNotIn(self.requested, self.requesting.publishers)
        # role-scoped: the organization group itself holds no grant
        self.assertFalse(
            OrganizationGroupObjectPermission.objects.filter(
                content_object=self.requested, group=self.requesting,
                permission__codename=(
                    "can_publish_for_organization")).exists())

    def test_accepting_grants_the_requested_services_to_the_publisher_role(
            self):
        """The existing services of B carry the resource grants of the role

        ``view`` so a member of the role reaches the object through the
        facade's object axis at all, and ``publish`` where the model is the
        capability carrier (#740). The rows name the accepting person: the
        acceptance IS a decision, unlike the creation bootstrap.
        """
        decider = get_user_model().objects.get(username="User1")
        service = self.build_wms("Accepted WMS", self.requested)
        service.save()
        request = PublishRequest.objects.create(
            from_organization=self.requesting, to_organization=self.requested)

        request.accept(granted_by=decider)

        rows = WebMapServiceGroupObjectPermission.objects.filter(
            content_object=service, group=self.publisher_role.group)
        self.assertEqual(
            {(row.permission.codename, row.granted_by_id) for row in rows},
            {("view_webmapservice", decider.pk),
             ("publish_resource", decider.pk)})

    def test_services_registered_after_acceptance_carry_the_publisher_grants(
            self):
        """The promise holds for the stock which comes later, not only at acceptance

        The creation bootstrap asks the owning organization's
        ``publisher_role_groups`` and writes the same actions a fresh
        acceptance wrote onto the stock (#740); the rows are mechanical, so
        they carry no ``granted_by``.
        """
        PublishRequest(
            from_organization=self.requesting,
            to_organization=self.requested).save()
        PublishRequest.objects.filter(
            from_organization=self.requesting,
            to_organization=self.requested).first().accept()

        service = self.build_wms("Later WMS", self.requested)
        service.save()

        rows = WebMapServiceGroupObjectPermission.objects.filter(
            content_object=service, group=self.publisher_role.group)
        self.assertEqual(
            {(row.permission.codename, row.granted_by_id) for row in rows},
            {("view_webmapservice", None), ("publish_resource", None)})
        # the owning organization's own groups answer the bootstrap of #732 -
        # the publisher grant is the only foreign one on the service
        self.assertEqual(
            WebMapServiceGroupObjectPermission.objects.filter(
                content_object=service).exclude(
                    group=self.publisher_role.group).count(), 3)

    def test_accepting_refuses_without_a_publisher_role(self):
        """A role which cannot answer must not be papered over with silence"""
        self.publisher_role.is_active = False
        self.publisher_role.save()
        request = PublishRequest.objects.create(
            from_organization=self.requesting, to_organization=self.requested)

        with self.assertRaises(ValidationError):
            request.accept()
        self.assertTrue(PublishRequest.objects.filter(pk=request.pk).exists())

    def test_clean_silently_passes_a_pair_that_may_publish_already(self):
        """The duplicate check of ``clean`` is dead, not broken

        It asks ``has_perm('accounts.can_publish_for', ...)`` - there is no
        such codename (the real one is ``can_publish_for_organization``) and
        guardian 3.x answers such a lookup with False instead of raising, so
        even a request from an organization that may publish for the target
        already sails through. Honest strings are #729's housekeeping; #734
        owns the resolution; the same-organization check below is alive and
        pinned next.
        """
        # B grants A the real right, so A asking to publish for B duplicates
        self.requested.add_publisher(self.requesting)
        self.assertIn(self.requested, self.requesting.can_publish_for)

        request = PublishRequest(
            from_organization=self.requesting,
            to_organization=self.requested)
        self.assertIsNone(request.clean())

    def test_clean_refuses_the_same_organization(self):
        request = PublishRequest(
            from_organization=self.requesting,
            to_organization=self.requesting)
        with self.assertRaises(ValidationError):
            request.clean()


class UserHasPermFilterTestCase(TestCase):
    """The ``user_has_perm`` filter answers from object grants alone."""

    fixtures = ["test_users.json"]

    def setUp(self):
        self.organization = Organization.objects.create(name=FILTERED)
        self.factory = RequestFactory()

    def filtered(self, username):
        request = self.factory.get(
            '/api/accounts/organizations',
            {'user_has_perm': 'accounts.view_organization'})
        request.user = get_user_model().objects.get(username=username)
        return OrganizationFilterSet(
            data=request.GET.dict(),
            queryset=Organization.objects.all(),
            request=request).qs

    def test_a_member_of_a_granted_group_sees_the_organization(self):
        assign_perm(perm='accounts.view_organization',
                    user_or_group=Group.objects.get(name="Group1"),
                    obj=self.organization)

        self.assertIn(self.organization, self.filtered("User1"))

    def test_a_user_with_only_the_global_permission_sees_nothing(self):
        """``accept_global_perms=False`` in ``accounts/filters/groups.py``

        The global grant below is all ``User2`` holds - the fixture's
        ``Default-Permissions`` group carries registry permissions only - and
        the endpoint still hides the organization although the user really
        holds the permission. The split answer of #727 from the other side,
        before #734 resolves it.
        """
        user = get_user_model().objects.get(username="User2")
        assign_perm(perm='accounts.view_organization', user_or_group=user)

        self.assertNotIn(self.organization, self.filtered("User2"))
        self.assertTrue(user.has_perm('accounts.view_organization'))
