"""The one permission-resolution facade of #734 (``extras.permissions``).

The issue replaces the four expressions that answered "may this user do this
on this object" - the ``accept_global_perms=False`` of
``accounts/filters/groups.py``, the ``True`` of ``notify/managers.py``, the
global AND object of the ``can_edit`` hints, and DRF's two gates - with one
facade. Its acceptance is that *all three entry points* (detail decision,
list queryset, serializer hint) answer one and the same question for one and
the same user, so this module is tested as a matrix: each case builds the
state of a user, and every entry point is asked about the same three
services.

The services stand for the three shapes a decision depends on:

* ``owned``   - ``owner`` is organization A (the typed ownership of #733);
  the bootstrap of #732/#733 has granted its view/change/delete to the
  ``resource_editor`` role group of A - the grant shape the API hands out
  for newly registered resources,
* ``foreign`` - ``owner`` is organization B,
* ``loose``   - no owner at all; decided by object grants alone.

The role states use the builtin catalogue seeded by the migrations of #731
(``resource_editor`` holds ``change_webmapservice``, ``service_account``
holds it on PLATFORM scope); one custom ORGANIZATION definition ("reads the
registry", view only) isolates the role-definition axis from any group grant
the bootstrap may have written.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from guardian.core import ObjectPermissionChecker
from guardian.shortcuts import assign_perm
from guardian.utils import get_anonymous_user
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory, force_authenticate

from accounts.models.groups import Organization
from accounts.models.roles import Role, RoleDefinition, RoleScope
from extras.permissions import (DjangoObjectPermissionsOrAnonReadOnly,
                                allowed, allowed_actions, allowed_model_scope,
                                objects_for_user)
from registry.models import WebMapService
from registry.models.guardian import WebMapServiceGroupObjectPermission
from registry.serializers.service import ExplorerAttributesSerializer

#: the first WMS of ``test_wms.json``; its contact rows seed the copies
TEMPLATE_WMS = "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"

CHANGE = "registry.change_webmapservice"
VIEW = "registry.view_webmapservice"


class _ViewStub:
    """Just enough view for ``DjangoObjectPermissions``' ``_queryset``."""

    def __init__(self, queryset):
        self._queryset = queryset

    def get_queryset(self):
        return self._queryset


class FacadeTestCaseMixin:
    """The three services, the users and the entry-point probes."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json"]

    def setUp(self):
        # the builtin catalogue of #731 is seeded by a migration; a test
        # process which ran a flushing module before must be able to build
        # on it all the same - the sync is idempotent and no-op when the
        # catalogue is present, and the organization bootstrap below needs
        # it to create the roles.
        from django.core.management import call_command
        call_command("sync_role_definitions", verbosity=0)
        # guardian maps an AnonymousUser to the database row of that name,
        # which post_migrate created - a TransactionTestCase running earlier
        # in the same full-suite process has flushed all tables and the
        # deferred creation of that flush never fires, so the anonymous
        # probes below re-create the row, as backend/tests/AGENTS.md
        # prescribes for every test asserting anonymous access
        get_user_model().objects.get_or_create(username="AnonymousUser")
        self.organization_a = Organization.objects.create(name="Facade Org A")
        self.organization_b = Organization.objects.create(name="Facade Org B")
        self.template = WebMapService.objects.get(pk=TEMPLATE_WMS)
        self.owned = self.make_service("Owned Service", self.organization_a)
        self.foreign = self.make_service("Foreign Service",
                                         self.organization_b)
        self.loose = self.make_service("Loose Service", None)
        self.services = (self.owned, self.foreign, self.loose)

        self.editor_a = Role.objects.for_org(
            self.organization_a).with_definition("resource_editor").get()
        self.platform_account_definition = RoleDefinition.objects.get(
            slug="service_account")

    def make_service(self, title, owner):
        service = WebMapService(
            title=title,
            service_url="https://www.example.com/service",
            version=self.template.version,
            origin=self.template.origin,
            metadata_contact=self.template.metadata_contact,
            service_contact=self.template.service_contact)
        service.owner = owner
        service.save()
        return service

    def new_user(self, username):
        return get_user_model().objects.create_user(
            username=username, password=username)

    def platform_account_role(self):
        """The PLATFORM role of the builtin ``service_account`` definition.

        The platform roles are seeded once per deployment (#732); a test
        must not create a second active role of one definition, so an
        existing one is used and only created when the process state lacks
        it (a flushed test database).
        """
        role = Role.objects.filter(
            role_definition=self.platform_account_definition,
            organization__isnull=True, is_active=True).first()
        if role is not None:
            return role
        group, _ = Group.objects.get_or_create(
            name="PLATFORM: service_account")
        return Role.objects.create(
            role_definition=self.platform_account_definition,
            organization=None, group=group)

    def publisher_role(self):
        """The ORGANIZATION role of the builtin ``resource_publisher``.

        Same dance as ``platform_account_role``: the bootstrap may already
        have created the role of the definition, and a second active role of
        one definition in one organization must not be added.
        """
        role = Role.objects.for_org(
            self.organization_a).with_definition("resource_publisher").first()
        if role is not None:
            return role
        group, _ = Group.objects.get_or_create(
            name="Facade Org A: resource_publisher")
        return Role.objects.create(
            role_definition=RoleDefinition.objects.get(
                slug="resource_publisher"),
            organization=self.organization_a, group=group)

    # -- the entry points, asked through their real consumers --------------

    def request_as(self, user, method="patch", query=None):
        """A DRF request as the endpoint sees it, authenticated as ``user``."""
        factory = APIRequestFactory()
        build = getattr(factory, method)
        wsgi_request = build("/", data=query or {})
        force_authenticate(wsgi_request, user=user)
        # the permission classes run on the wrapped DRF request (that is
        # what the view's dispatch hands them); the factory's raw request
        # carries the force-authenticate markers only
        return Request(wsgi_request)

    def gate_allows(self, user, obj, method="patch"):
        """The endpoint's answer: DRF's object gate over the facade class."""
        permission = DjangoObjectPermissionsOrAnonReadOnly()
        return permission.has_object_permission(
            self.request_as(user, method=method), _ViewStub(
                WebMapService.objects), obj)

    def hint_actions(self, user, obj):
        """The explorer's ``allowedActions`` hint over the facade (#738)."""
        request = self.request_as(user, method="get", query={
            "fields[WebMapService]": "id,title,allowed_actions"})
        checker = ObjectPermissionChecker(user)
        checker.prefetch_perms(list(self.services))
        serializer = _ExplorerProbe(context={
            "request": request, "perm_checker": checker})
        return serializer.get_allowed_actions(obj)

    def hint_allows(self, user, obj):
        """The explorer's ``change`` answer over the facade."""
        return "change" in self.hint_actions(user, obj)

    def listed(self, user, perm=CHANGE):
        """The list axis as a set of pks."""
        return {pk for pk in objects_for_user(
            user, perm, WebMapService.objects).values_list(
                "pk", flat=True)}


class _ExplorerProbe(ExplorerAttributesSerializer):
    """Concrete shell around the explorer serializer's ``get_allowed_actions``."""

    class Meta:
        model = WebMapService
        fields = ("allowed_actions",)


class FacadeAxesTests(FacadeTestCaseMixin, TestCase):
    """Each axis of ``allowed()`` on its own, and the retirement of the rest."""

    def test_superuser_is_the_break_glass(self):
        user = self.new_user("facade-break-glass")
        user.is_superuser = True
        user.save()
        for service in self.services:
            self.assertTrue(allowed(user, CHANGE, service))

    def test_no_grant_answers_nothing(self):
        user = self.new_user("facade-nothing")
        for service in self.services:
            self.assertFalse(allowed(user, CHANGE, service))

    def test_object_grant_on_the_user_decides_without_anything_else(self):
        user = self.new_user("facade-user-grant")
        assign_perm(CHANGE, user, self.loose)
        self.assertTrue(allowed(user, CHANGE, self.loose))
        self.assertFalse(allowed(user, CHANGE, self.owned))
        self.assertFalse(allowed(user, CHANGE, self.foreign))

    def test_object_grant_on_a_group_decides_alone(self):
        user = self.new_user("facade-group-grant")
        group = Group.objects.create(name="Facade Granted Group")
        assign_perm(CHANGE, group, self.loose)
        user.groups.add(group)
        self.assertTrue(allowed(user, CHANGE, self.loose))
        self.assertFalse(allowed(user, CHANGE, self.owned))

    def test_organization_role_reaches_its_own_organization_only(self):
        """The role-definition axis, isolated from every group grant.

        The custom ORGANIZATION-scope definition holds ``view_webmapservice``
        and nothing is ever granted to its group, so the only possible
        answer is the definition itself - scoped by the ``owner`` of #733.
        """
        definition = RoleDefinition.objects.create(
            slug="facade_reader", label="Facade reader",
            scope=RoleScope.ORGANIZATION)
        definition.permissions.set([Permission.objects.get(
            content_type__app_label="registry", codename="view_webmapservice")])
        group = Group.objects.create(name="Facade Reader Group")
        role = Role.objects.create(
            role_definition=definition,
            organization=self.organization_a, group=group)
        user = self.new_user("facade-reader")
        role.add_member(user)

        # isolation of the axis: the group holds no object grant anywhere
        self.assertFalse(
            WebMapServiceGroupObjectPermission.objects.filter(
                group=role.group).exists(),
            "the definition axis must be the only possible answer here")
        for service in self.services:
            self.assertEqual(
                allowed(user, VIEW, service),
                service is self.owned,
                f"{service.title} decided through the wrong axis")
        # and an organization role never reaches a *change* it does not hold
        self.assertFalse(allowed(user, CHANGE, self.owned))

    def test_platform_role_reaches_over_every_organization(self):
        user = self.new_user("facade-service-account")
        self.platform_account_role().add_member(user)
        for service in self.services:
            self.assertTrue(allowed(user, CHANGE, service))

    def test_expired_membership_stops_the_role_axis(self):
        """Q5's expiry semantics: the definition axis stops with ``valid_until``."""
        user = self.new_user("facade-expired")
        self.editor_a.add_member(
            user, valid_until=timezone.now() - timedelta(days=1))
        # the loose service has no grant of any kind for this user: only the
        # role axis could answer, and it is expired
        self.assertFalse(allowed(user, CHANGE, self.loose))

    def test_group_grants_of_an_expired_membership_keep_granting(self):
        """Stated in ``RoleMembership``: only #741's revocation flips the group.

        The bootstrap wrote this user's editor group the object grant of
        ``owned``; the membership expiry stops the definition axis but not
        that row - which is fine only as long as list, detail and hint all
        keep granting (next test), never one of them alone.
        """
        user = self.new_user("facade-expired-group")
        self.editor_a.add_member(
            user, valid_until=timezone.now() - timedelta(days=1))
        self.assertTrue(allowed(user, CHANGE, self.owned))
        self.assertIn(self.owned.pk, self.listed(user))
        self.assertTrue(self.hint_allows(user, self.owned))

    def test_retired_global_permission_is_no_ask_of_the_facade(self):
        """Q5=B: the Default-Permissions shape edits nothing by itself."""
        user = self.new_user("facade-legacy-global")
        assign_perm(CHANGE, user)
        for service in self.services:
            self.assertFalse(allowed(user, CHANGE, service))
        self.assertEqual(self.listed(user), set())

    def test_anonymous_reaches_only_explicit_anonymous_grants(self):
        assign_perm(CHANGE, get_anonymous_user(), self.loose)
        self.assertTrue(allowed(AnonymousUser(), CHANGE, self.loose))
        self.assertFalse(allowed(AnonymousUser(), CHANGE, self.owned))

    def test_the_hint_answers_the_full_action_batch_in_order(self):
        """#738: one answer for all actions, capabilities included.

        ``resource_publisher`` holds view plus the app-level publish and
        share on ORGANIZATION scope; a user holding it reads exactly those
        three actions on a service of its organization - the CRUD actions
        spelled per model, the capabilities spelled ``registry.<codename>``,
        in the fixed order - and only its explicit ``change`` grant answers
        on the service which belongs to no organization, because the
        organization axis reaches nothing there.
        """
        role = self.publisher_role()
        user = self.new_user("facade-publisher")
        role.add_member(user)
        assign_perm(CHANGE, user, self.loose)

        self.assertEqual(self.hint_actions(user, self.owned),
                         ["view", "publish", "share"])
        self.assertEqual(self.hint_actions(user, self.loose), ["change"])
        self.assertEqual(self.hint_actions(user, self.foreign), [])

    def test_model_scope_gate_of_a_create(self):
        """The create gate keeps the legacy ``add`` AND gains the role axes."""
        user = self.new_user("facade-creator")
        self.assertFalse(allowed_model_scope(user, "registry.add_webmapservice"))
        self.editor_a.add_member(user)
        self.assertTrue(
            allowed_model_scope(user, "registry.add_webmapservice"),
            "resource_editor holds add_webmapservice in the catalogue of #731")
        self.assertFalse(allowed_model_scope(user, "registry.delete_webmapservice"),
                         "the editor deletes nothing - the catalogue scopes this")


class EndpointGateTests(FacadeTestCaseMixin, TestCase):
    """``has_permission``/``has_object_permission`` of the API's class."""

    def setUp(self):
        super().setUp()
        self.permission = DjangoObjectPermissionsOrAnonReadOnly()
        self.view = _ViewStub(WebMapService.objects)

    def post_as(self, user):
        wsgi_request = APIRequestFactory().post("/")
        force_authenticate(wsgi_request, user=user if user is not None
                           else AnonymousUser())
        return Request(wsgi_request)

    def test_create_gate_accepts_roles_and_the_legacy_add(self):
        self.assertTrue(self.permission.has_permission(
            self.post_as(self.editor_member()), self.view))

        legacy = self.new_user("gate-legacy-add")
        assign_perm("registry.add_webmapservice", legacy)
        self.assertTrue(self.permission.has_permission(
            self.post_as(legacy), self.view),
            "the add gate retires with its data migration, not here")

        nobody = self.new_user("gate-nobody")
        self.assertFalse(self.permission.has_permission(
            self.post_as(nobody), self.view))

    def test_write_gate_is_authentication_only(self):
        """The object decides a write; no global can open it earlier."""
        wsgi_patch = APIRequestFactory().patch("/")
        force_authenticate(wsgi_patch, user=self.new_user("gate-writer"))
        request = Request(wsgi_patch)
        self.assertTrue(self.permission.has_permission(request, self.view))
        self.assertFalse(self.permission.has_object_permission(
            request, self.view, self.owned))

    def test_anonymous_may_read_but_not_write(self):
        wsgi_get = APIRequestFactory().get("/")
        force_authenticate(wsgi_get, user=AnonymousUser())
        self.assertTrue(self.permission.has_permission(
            Request(wsgi_get), self.view))
        self.assertFalse(self.permission.has_permission(
            self.post_as(None), self.view))

    def editor_member(self):
        user = self.new_user("gate-editor")
        self.editor_a.add_member(user)
        return user


class EntryPointsAgreeTests(FacadeTestCaseMixin, TestCase):
    """The acceptance of #734: detail, list and hint flip together.

    Every case asks all three entry points about the same three services;
    the matrix also pins WHAT the shared answer is, so a shared regression
    is visible as a wrong expectation, not as a silent agreement.
    """

    def assert_all_entry_points(self, user, expected_services,
                                all_rows=False):
        """``expected_services``: the services the CHANGE decision passes.

        ``all_rows`` marks the deliberately widening axes (break-glass,
        platform) which answer yes to every row, not only to the three of
        the matrix.
        """
        expected = {service.pk for service in expected_services}
        listed = self.listed(user)
        for service in self.services:
            detail = self.gate_allows(user, service)
            hint = self.hint_allows(user, service)
            in_list = service.pk in listed
            self.assertEqual(
                (detail, hint, in_list), (in_list, in_list, in_list),
                f"{user} / {service.title}: the three entry points "
                f"disagree (detail={detail}, hint={hint}, list={in_list})")
            self.assertEqual(
                detail, service.pk in expected,
                f"{user} / {service.title}: shared answer is wrong")
        if all_rows:
            self.assertEqual(
                listed,
                set(WebMapService.objects.values_list("pk", flat=True)),
                "a widening axis must answer every row, not only some")
        else:
            self.assertEqual(
                listed, expected,
                "the list axis agreed with the detail gate but not with "
                "the expected state of the case")

    def test_without_any_grant_no_entry_point_passes(self):
        self.assert_all_entry_points(
            self.new_user("agree-nothing"), [])

    def test_user_object_grant_passes_everywhere_on_its_object(self):
        user = self.new_user("agree-user-grant")
        assign_perm(CHANGE, user, self.loose)
        self.assert_all_entry_points(user, [self.loose])

    def test_group_object_grant_passes_everywhere_on_its_object(self):
        user = self.new_user("agree-group-grant")
        group = Group.objects.create(name="Agree Granted Group")
        assign_perm(CHANGE, group, self.owned)
        user.groups.add(group)
        self.assert_all_entry_points(user, [self.owned])

    def test_organization_role_passes_its_own_rows_everywhere(self):
        """The service predates its editor's membership - no per-row grant
        was ever written for it; the definition axis answers on ALL three."""
        definition = RoleDefinition.objects.create(
            slug="facade_editor", label="Facade editor",
            scope=RoleScope.ORGANIZATION)
        definition.permissions.set([Permission.objects.get(
            content_type__app_label="registry", codename="change_webmapservice")])
        role = Role.objects.create(
            role_definition=definition,
            organization=self.organization_a,
            group=Group.objects.create(name="Agree Editor Group"))
        service = self.make_service("Earlier Service", self.organization_a)
        user = self.new_user("agree-editor")
        role.add_member(user)
        # isolation: this service carries no object grant for this user's group
        self.assert_all_entry_points(user, [self.owned, service])

    def test_a_role_only_grant_answers_change_in_hint_and_write(self):
        """The #738 acceptance: the hint and the PATCH agree on a role grant.

        The service predates the membership and the role's group holds no
        object grant - only the ORGANIZATION definition axis can answer
        ``change``. The retired ``can_edit`` read "cannot edit" on exactly
        this state while the endpoint let the user through; the hint must
        answer ``change`` now and the same user must really pass the gate of
        the PATCH.
        """
        definition = RoleDefinition.objects.create(
            slug="facade_hint_editor", label="Facade hint editor",
            scope=RoleScope.ORGANIZATION)
        definition.permissions.set([Permission.objects.get(
            content_type__app_label="registry",
            codename="change_webmapservice")])
        role = Role.objects.create(
            role_definition=definition,
            organization=self.organization_a,
            group=Group.objects.create(name="Facade Hint Editor Group"))
        user = self.new_user("agree-hint-write")
        role.add_member(user)

        self.assertIn("change", self.hint_actions(user, self.owned))
        self.assertTrue(
            self.gate_allows(user, self.owned),
            "the answer of the hint is the answer of the PATCH endpoint")
        self.assertNotIn("change", self.hint_actions(user, self.foreign))
        self.assertFalse(self.gate_allows(user, self.foreign))

    def test_platform_role_passes_every_row_everywhere(self):
        user = self.new_user("agree-platform")
        self.platform_account_role().add_member(user)
        self.assert_all_entry_points(user, list(self.services),
                                     all_rows=True)

    def test_expired_membership_flips_all_entry_points_alike(self):
        """The expiry pin: what stops, stops everywhere at once."""
        user = self.new_user("agree-expired")
        role = self.editor_a
        role.add_member(user, valid_until=timezone.now() - timedelta(days=1))
        # the bootstrap grant of the editor group on `owned` still stands ->
        # it passes on ALL entry points; the definition axis is expired and
        # `loose`/`foreign` are out on all three. A loose service later
        # granted nothing: after revoking membership, `owned` flips too.
        self.assert_all_entry_points(user, [self.owned])
        role.remove_member(user)
        self.assert_all_entry_points(user, [])

    def test_retired_global_permission_passes_no_entry_point(self):
        user = self.new_user("agree-legacy")
        assign_perm(CHANGE, user)
        self.assert_all_entry_points(user, [])

    def test_superuser_passes_every_entry_point(self):
        user = self.new_user("agree-super")
        user.is_superuser = True
        user.save()
        self.assert_all_entry_points(user, list(self.services),
                                     all_rows=True)

    def test_anonymous_passes_no_entry_point(self):
        self.assert_all_entry_points(AnonymousUser(), [])


class CacheInvalidationTests(FacadeTestCaseMixin, TestCase):
    """The next request sees the grant - no caller pops caches by hand."""

    def test_joining_a_group_refreshes_the_user_instance(self):
        user = self.new_user("cache-groups")
        group = Group.objects.create(name="Cache Granted Group")
        group.permissions.set([Permission.objects.get(
            content_type__app_label="registry", codename="view_webmapservice")])
        self.assertFalse(user.has_perm(VIEW), "prime the permission cache")
        user.groups.add(group)
        self.assertTrue(user.has_perm(VIEW))

    def test_direct_global_grant_refreshes_the_user_instance(self):
        user = self.new_user("cache-direct")
        self.assertFalse(user.has_perm(VIEW), "prime the permission cache")
        user.user_permissions.set([Permission.objects.get(
            content_type__app_label="registry", codename="view_webmapservice")])
        self.assertTrue(user.has_perm(VIEW))

    def test_group_side_membership_is_effective_for_the_next_load(self):
        """Group-side pk writes: the fact is true for every user read after them.

        ``group.user_set.add`` names the changed users by pks only - no
        loaded instance of the caller is reachable from the signal (that is
        Django's own limitation, which is why it documents manual pops).
        What #734 centralizes: the writes that DO hold the instance
        invalidate it there - ``RoleMembership.save()`` covers the project's
        real group-side write (the previous test pair) - and everything the
        signal reaches is dropped, so a user loaded afterwards, as every
        request does, decides from current state.
        """
        user = self.new_user("cache-reverse")
        group = Group.objects.create(name="Cache Reverse Group")
        group.permissions.set([Permission.objects.get(
            content_type__app_label="registry", codename="view_webmapservice")])
        self.assertFalse(user.has_perm(VIEW), "prime the permission cache")
        group.user_set.add(user)
        reread = get_user_model().objects.get(pk=user.pk)
        self.assertTrue(reread.has_perm(VIEW))
        # and the write path that holds the exact instance - the pattern of
        # all membership writes (#734) - reaches the caller's object too
        self.editor_a.add_member(user)
        self.assertTrue(user.has_perm(VIEW),
                        "the membership's own invalidation reaches the "
                        "instance the caller handed in")

    def test_membership_and_removal_take_effect_without_a_new_user(self):
        """Grant and revoke are decided the same, on the same instance.

        The membership writes go through ``RoleMembership.save()``, the
        removal through ``Role.remove_member`` - both paths drop Django's
        caches centrally (#734); the request-facing proof is that the very
        next decision flips.
        """
        user = self.new_user("cache-role")
        self.editor_a.add_member(user)
        self.assertIn(user, self.editor_a.group.user_set.all(),
                      "the membership is the group membership")
        self.assertTrue(self.gate_allows(user, self.owned))
        self.editor_a.remove_member(user)
        self.assertFalse(
            self.gate_allows(user, self.owned),
            "a revoked membership answers 403 on the next request - the "
            "split this central invalidation exists to prevent")


class QueryBudgetTests(FacadeTestCaseMixin, TestCase):
    """The facade must not turn permission resolution into N+1 (#922 kin)."""

    def test_role_axes_are_memoized_per_checker(self):
        user = self.new_user("budget-editor")
        self.editor_a.add_member(user)
        checker = ObjectPermissionChecker(user)
        checker.prefetch_perms(list(self.services))
        # warm every axis once: one object passes on the grant, one reaches
        # the role axes and finds nothing
        allowed(user, CHANGE, self.owned, checker=checker)
        allowed(user, CHANGE, self.loose, checker=checker)
        with CaptureQueriesContext(connection) as context:
            self.assertTrue(allowed(user, CHANGE, self.owned,
                                    checker=checker))
            self.assertFalse(allowed(user, CHANGE, self.loose,
                                     checker=checker))
        self.assertEqual(
            len(context), 0,
            "a repeated decision over the same request re-reads nothing")

    def test_the_action_batch_answers_per_request_not_per_row(self):
        """The six actions of #738 must not become six queries per row."""
        user = self.new_user("budget-actions")
        self.editor_a.add_member(user)
        checker = ObjectPermissionChecker(user)
        checker.prefetch_perms(list(self.services))
        # one unmeasured object: the foreign service holds no grant, so this
        # call reads both role axes for the whole batch once
        allowed_actions(user, self.foreign, checker=checker)
        with CaptureQueriesContext(connection) as context:
            for service in self.services:
                allowed_actions(user, service, checker=checker)
        self.assertEqual(
            len(context), 0,
            "the batched role axes and the prefetched object axis re-read "
            "nothing for the rows that follow")

    def test_list_axis_does_not_grow_with_rows(self):
        user = self.new_user("budget-list")
        self.editor_a.add_member(user)
        # one unmeasured pass: a TransactionTestCase flushing earlier in
        # the same process has cleared Django's content-type cache, and the
        # reload guardian's permission resolution pays once per process
        # would otherwise land in the measured first window and read as a
        # query the rows cost (backend/tests/AGENTS.md: full-suite runs
        # differ from targeted ones in exactly this process state)
        self.listed(user)
        with CaptureQueriesContext(connection) as before:
            self.listed(user)
        for counter in range(4):
            self.make_service(f"Extra {counter}", self.organization_a)
        with CaptureQueriesContext(connection) as after:
            self.listed(user)
        self.assertEqual(
            len(before), len(after),
            "the role axes answer per request, not per row")
