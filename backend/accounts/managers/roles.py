"""The querysets and the managers of the roles of #732.

The selection logic of ``Role`` and ``RoleMembership`` lives here, next to
the managers built from it, the way ``accounts.managers.users`` holds
``UserQuerySet`` and ``CustomUserManager``.
"""

from django.contrib.auth.models import Group
from django.db import models
from django.db.models.query import QuerySet
from django.utils import timezone


class RoleQuerySet(models.QuerySet):
    """The only way which finds a role without naming its group.

    Until #732 the answer to "who administers this organization" was a
    name built from the name of the organization, so renaming it detached
    every role. Every lookup of a role therefore goes through this
    queryset: by key, by definition slug, never by the string in
    ``auth_group.name``.
    """

    def active(self) -> QuerySet:
        """The roles which are not waiting for their retirement (#741)."""
        return self.filter(is_active=True)

    def retired(self) -> QuerySet:
        """The role groups which are retired: the work list of #741.

        These are the per-model ``<Org> <model> Admins`` groups a
        deployment already had, which #732 reuses as inactive roles
        instead of deleting them: guardian's rows point at the group, so
        the group has to outlive the bootstrap which created it.

        #741 added a second kind of inactive role: a person may retire a role
        over the api to take it out of the member picker without deleting it.
        Deleting those is never this list's purpose, so the retirement itself
        asks ``accounts.retirement.is_legacy_model_group`` of every row it is
        handed here.
        """
        return self.filter(is_active=False)

    def for_org(self, organization) -> QuerySet:
        """The roles of one organization.

        A platform role belongs to no organization and is never an answer
        here, whatever organization is asked for (#727 decision Q3:
        membership in one organization says nothing about another).
        """
        return self.filter(organization=organization)

    def with_definition(self, slug) -> QuerySet:
        """The role of one definition.

        Active roles only: while the retired groups of #741 are still
        there, the retired duplicates of a definition must not be an
        answer to "the resource editor of this organization"; they are
        reached through ``retired()``.
        """
        return self.active().filter(role_definition__slug=slug)

    def managing(self, model) -> QuerySet:
        """The roles whose definition may change instances of ``model``.

        The question the permission bootstrap asks for a newly registered
        resource: which role of the owning organization is the one which
        edits this kind of thing? The answer is read from the catalogue -
        the role definition which holds ``change_<model>`` - rather than
        from a group named after the model, which is why adding a
        role-managed model needs no new group and no migration for the
        existing organizations (#727).

        Args:
            model: the model class whose instances the role manages

        Returns:
            QuerySet: the active roles of this queryset's organizations
        """
        return self.active().filter(
            role_definition__permissions__codename=(
                f'change_{model._meta.model_name}'),
            role_definition__permissions__content_type__app_label=(
                model._meta.app_label),
            role_definition__permissions__content_type__model=(
                model._meta.model_name),
        ).distinct()

    def create_for_organization(self, organization,
                                created_by=None) -> list:
        """Create every role of the catalogue for one organization.

        Idempotent: an organization which already holds the role of a
        definition keeps it, so a half-finished bootstrap - or an
        organization created before a definition was added to the
        catalogue - is completed rather than doubled. A new role gets a
        new group, and only the roles which are missing create one: the
        name of a ``Group`` is unique, so a group written before the check
        would stay behind as an orphan.

        Args:
            organization: the organization to give roles to
            created_by: the user the role instances are credited to, if any

        Returns:
            list: every role of the organization, in the order of the
            catalogue
        """
        # the catalogue and the group-name helper live in
        # ``accounts.models.roles``, which imports this module for its
        # managers; importing them at the module level would cycle
        from accounts.models.roles import (RoleDefinition, RoleScope,
                                           free_role_group_name)

        manager = self.model._default_manager
        roles = []
        for definition in RoleDefinition.objects.filter(
                scope=RoleScope.ORGANIZATION):
            role = manager.filter(
                role_definition=definition,
                organization=organization).first()
            if role is None:
                role = manager.create(
                    role_definition=definition,
                    organization=organization,
                    group=Group.objects.create(
                        name=free_role_group_name(organization,
                                                  definition.slug)),
                    created_by=created_by)
            roles.append(role)
        return roles


class RoleManager(models.Manager.from_queryset(RoleQuerySet)):
    """The default manager of ``Role``: its queryset, as methods"""


class RoleMembershipQuerySet(models.QuerySet):
    """The memberships, deleting one by one so the group follows."""

    def for_revocation_task(self, now=None) -> QuerySet:
        """The memberships the revoking task of #741 has to take back.

        Named for its consumer (``accounts.tasks.
        revoke_expired_role_memberships``), which is the convention of
        #1397: the selection - a ``valid_until`` which has passed - and the
        relations the revocation reads are stated once, where they can be
        reviewed. A membership without a ``valid_until`` never expires and is
        never an answer; ``None`` asks the clock, so a caller may name the
        moment it judges (the test of the task does).

        ``role__group`` is in the plan because deleting a membership takes the
        user out of the group of its role: without it the sweep pays one query
        per revoked row.
        """
        if now is None:
            now = timezone.now()
        return self.filter(
            valid_until__isnull=False,
            valid_until__lte=now,
        ).select_related("role__group", "user")

    def delete(self):
        """Delete the memberships instance by instance.

        ``QuerySet.delete()`` is a single ``DELETE`` and would leave the
        users in the groups of the roles it removes the memberships of - a
        grant which no membership explains. Memberships are few, so the
        rows are deleted through the model, whose ``delete()`` maintains
        the group.
        """
        removed = 0
        for membership in self:
            membership.delete()
            removed += 1
        return (removed, {})


class RoleMembershipManager(models.Manager.from_queryset(
        RoleMembershipQuerySet)):
    """The default manager of ``RoleMembership``: its queryset, as methods"""
