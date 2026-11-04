"""Pins the publishing rights: the grant, the request that asks for it, the filter.

Three code paths answer "who may publish for whom", and all three are in the
blast radius of #740 (role-scoped acceptance, real ``Organization.publishers``)
and #734 (one permission-resolution facade):

* ``Organization.add_publisher`` grants ``can_publish_for_organization`` on
  one organization to another, and ``Organization.can_publish_for`` reads the
  grant back - with ``accept_global_perms=False``, so the same question asked
  through ``notify/managers.py`` (which passes ``True``) has a different
  answer (#727 motivation);
* accepting a ``PublishRequest`` writes that grant - in the direction opposite
  to the one the request states, and without ever persisting
  ``is_accepted``: ``save()`` deletes the request instead of updating it;
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

REQUESTING = "Requesting Organization"
REQUESTED = "Requested Organization"
FILTERED = "Filtered Organization"


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
    """What requesting and accepting a publishing right does today."""

    fixtures = ["test_users.json"]

    def setUp(self):
        self.requesting = Organization.objects.create(name=REQUESTING)
        self.requested = Organization.objects.create(name=REQUESTED)

    def test_creating_a_request_only_stores_the_request(self):
        request = PublishRequest.objects.create(
            from_organization=self.requesting, to_organization=self.requested)

        self.assertIsNotNone(request.pk)
        self.assertFalse(request.is_accepted)
        self.assertIsNotNone(request.activation_until)
        self.assertFalse(self.requested.can_publish_for.exists())
        self.assertFalse(self.requesting.can_publish_for.exists())

    def test_accepting_grants_the_reverse_and_eats_the_request(self):
        """Both warts of ``PublishRequest.save`` on one save

        ``A`` asks to publish for ``B``; accepting calls
        ``A.add_publisher(B)`` - which grants ``B`` the right over ``A``, the
        opposite direction - and the accepted instance is deleted, so
        ``is_accepted`` is never persisted. #740 makes acceptance role-scoped
        and will have to decide the direction on record.
        """
        request = PublishRequest.objects.create(
            from_organization=self.requesting, to_organization=self.requested)
        request.is_accepted = True
        request.save()

        self.assertFalse(
            PublishRequest.objects.filter(pk=request.pk).exists(),
            "accepting the request kept it in the database")
        self.assertIn(self.requesting, self.requested.can_publish_for)
        self.assertNotIn(self.requested, self.requesting.can_publish_for)

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
