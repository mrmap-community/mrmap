import datetime

from accounts.settings import DEFAULT_REQUEST_ACIVATION_TIME
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.db.models import QuerySet
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from guardian.core import ObjectPermissionChecker
from guardian.shortcuts import assign_perm, remove_perm


class Contact(models.Model):
    """
    An abstract model which adds fields to store the contact specific fields. All fields can be
    null to store bad quality metadata as well.
    """

    person_name = models.CharField(
        max_length=200,
        default="",
        blank=True,
        verbose_name=_("Contact person"),
    )
    email = models.EmailField(
        max_length=100, default="", blank=True, verbose_name=_("E-Mail")
    )
    phone = models.CharField(
        max_length=100, default="", blank=True, verbose_name=_("Phone")
    )
    facsimile = models.CharField(
        max_length=100, default="", blank=True, verbose_name=_("Facsimile")
    )
    city = models.CharField(
        max_length=100, default="", blank=True, verbose_name=_("City")
    )
    postal_code = models.CharField(
        max_length=100, default="", blank=True, verbose_name=_("Postal code")
    )
    address_type = models.CharField(
        max_length=100,
        default="",
        blank=True,
        verbose_name=_("Address type"),
    )
    address = models.CharField(
        max_length=100, default="", blank=True, verbose_name=_("Address")
    )
    state_or_province = models.CharField(
        max_length=100,
        default="",
        blank=True,
        verbose_name=_("State or province"),
    )
    country = models.CharField(
        max_length=100, default="", blank=True, verbose_name=_("Country")
    )

    def __str__(self):
        return self.person_name

    class Meta:
        abstract = True
        unique_together = (
            "person_name",
            "email",
            "phone",
            "facsimile",
            "city",
            "postal_code",
            "address_type",
            "address",
            "state_or_province",
            "country",
        )


CAN_PUBLISH_FOR_ORGANIZATION = "accounts.can_publish_for_organization"

#: the codename part of :data:`CAN_PUBLISH_FOR_ORGANIZATION`, for queries over
#: the ``Permission`` relation of the grant rows
CAN_PUBLISH_FOR_ORGANIZATION_CODENAME = "can_publish_for_organization"


class Organization(Group, Contact):
    """
    A organization represents a real life organization like a authority, company etc. The name of the organization can
    be null to store bad quality metadata as well.
    """

    description = models.TextField(
        default="",
        blank=True,
        verbose_name=_("description"),
        help_text=_("Describe what this organization representing"),
    )

    class Meta:
        # define default ordering for this model. This is needed for django tables2 ordering. If we use just the
        # foreignkey as column accessor the ordering will be done by the primary key. To avoid this we need to define
        # the right default way here...
        ordering = ["name"]
        verbose_name = _("Organization")
        verbose_name_plural = _("Organizations")
        permissions = [
            ('can_publish_for_organization', 'Can publish for this organization')]

    def __str__(self):
        return self.name

    @property
    def can_publish_for(self) -> QuerySet:
        """
        return all `Organization` objects which can publish for this `Organization.

        What the name on record answers - despite its wording - is the
        forward direction, pinned by ``tests/django/accounts/
        test_publishing_rights.py``: the organizations **this one is allowed
        to publish for**, read from the object grants held by its own group
        (the shape ``add_publisher`` wrote onto a whole requesting
        organization) or by the groups of its active roles (the shape an
        accepted ``PublishRequest`` writes onto the requesting
        organization's ``resource_publisher`` role group, #740). The reverse
        question - who may publish for this organization - is
        :attr:`publishers`.

        Object grants decide: the retired global permission of Q5=B opens
        nothing here, as it does nowhere in the facade.

        Returns:
            the organizations this organization may publish for (QuerySet)
        """
        # the through-model imports this module for its content_object -
        # the import goes the other way at call time
        from accounts.models.guardian import OrganizationGroupObjectPermission

        granted_by_our_groups = OrganizationGroupObjectPermission.objects.filter(
            permission__codename=CAN_PUBLISH_FOR_ORGANIZATION_CODENAME,
        ).filter(
            Q(group=self)
            | Q(group__role__organization=self, group__role__is_active=True))
        return Organization.objects.filter(
            pk__in=granted_by_our_groups.values_list(
                "content_object_id", flat=True)).exclude(pk=self.pk).distinct()

    @property
    def publishers(self) -> QuerySet:
        """The organizations which may publish for this one.

        The reverse lookup of :attr:`can_publish_for`: the organizations
        whose own group or whose role groups hold
        ``accounts.can_publish_for_organization`` over this organization
        (#740 replaces the ``Organization.objects.none()`` stub). The
        organization itself is never its own publisher answer, although the
        bootstrap of #732 grants its default role exactly that permission -
        publishing *at home* is decided by the role axes of the facade, not
        by this cross-organization statement.
        """
        return self._publishers_query().exclude(pk=self.pk).distinct()

    def _publishers_query(self) -> QuerySet:
        """Every organization a granted group of self leads to.

        Direct first (the granted group *is* the organization, the legacy
        ``add_publisher`` shape), then through the role groups (an accepted
        ``PublishRequest`` of #740 writes onto the group of the requesting
        organization's ``resource_publisher`` role). One query per shape,
        both as subqueries - the list stays lazy.
        """
        from accounts.models.roles import Role

        granted_group_ids = self._granted_publisher_groups()
        return Organization.objects.filter(
            Q(pk__in=Organization.objects.filter(
                pk__in=granted_group_ids))
            | Q(pk__in=Role.objects.filter(
                group_id__in=granted_group_ids).exclude(
                    organization_id=None).values_list(
                        "organization_id", flat=True)))

    def publisher_role_groups(self) -> QuerySet:
        """The active foreign role groups which may publish for this org.

        The grant target of the creation bootstrap of #740: a resource newly
        registered for this organization must give its view (and publishing)
        to the roles the organization has accepted as publishers - the
        active roles of *other* organizations holding the grant. Own groups
        are no answer: the members of the owning organization are managed by
        the creation grants of #732, not by this cross statement, and the
        bootstrap of #732 grants ``can_publish_for_organization`` to the own
        default role for the legacy question, not to receive resources.
        """
        from accounts.models.roles import Role

        return Role.objects.filter(
            group_id__in=self._granted_publisher_groups(),
            is_active=True).exclude(
                organization=None).exclude(
                    organization=self).select_related("group").distinct()

    def _granted_publisher_groups(self) -> QuerySet:
        """The pks of groups holding the publish-for grant over self.

        Both shapes answer: the organization group itself (the legacy
        ``add_publisher`` wrote the grant onto the whole requesting
        organization) and any role group (the shape an accepted
        ``PublishRequest`` writes since #740).
        """
        return self.group_object_permissions.filter(
            permission__codename=CAN_PUBLISH_FOR_ORGANIZATION_CODENAME,
        ).values_list("group_id", flat=True)

    def grant_publish_for_group(self, group, granted_by=None):
        """Record "this group may publish for self" with its provenance.

        The organization-level statement of the publishing right, written
        onto the **group of a role** rather than onto the whole requesting
        organization (#740): leaving the role then revokes it at once.
        Returns the grant row, existing or newly written.
        """
        # the guardian through-models import this module for their
        # ``content_object`` - the import goes the other way at call time
        from accounts.models.guardian import OrganizationGroupObjectPermission
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType

        permission = Permission.objects.get(
            codename=CAN_PUBLISH_FOR_ORGANIZATION_CODENAME,
            content_type=ContentType.objects.get_for_model(Organization))
        row, _created = OrganizationGroupObjectPermission.objects.get_or_create(
            permission=permission,
            content_object=self,
            group=group,
            defaults={"granted_by": granted_by})
        return row

    def add_publisher(self, publisher) -> None:
        if isinstance(publisher, Organization):
            assign_perm(perm=CAN_PUBLISH_FOR_ORGANIZATION,
                        user_or_group=publisher, obj=self)
        else:
            raise TypeError('given publisher is not from type Organization')

    def remove_publisher(self, publisher) -> None:
        if isinstance(publisher, Organization):
            remove_perm(perm=CAN_PUBLISH_FOR_ORGANIZATION,
                        user_or_group=publisher, obj=self)
        else:
            raise TypeError('given publisher is not from type Organization')


class BaseInternalRequest(models.Model):
    message = models.TextField(blank=True)
    activation_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self._state.adding:
            if not self.activation_until:
                self.activation_until = timezone.now() + datetime.timedelta(
                    days=DEFAULT_REQUEST_ACIVATION_TIME
                )
        else:
            if timezone.now() > self.activation_until:
                self.delete()
                raise ValidationError("REQUEST_ACTIVATION_TIMEOVER")

        super().save(*args, **kwargs)


class PublishRequest(BaseInternalRequest):
    from_organization = models.ForeignKey(
        Organization,
        verbose_name=_("requesting organization"),
        related_name="from_pending_publish_requests",
        on_delete=models.CASCADE,
    )
    to_organization = models.ForeignKey(
        Organization,
        verbose_name=_("requested organization"),
        related_name="to_pending_publish_requests",
        on_delete=models.CASCADE,
    )
    is_accepted = models.BooleanField(
        verbose_name=_("accepted"), default=False)

    class Meta:
        # It shall be restricted to create multiple requests objects for the same organization per group. This unique
        # constraint will also raise a form error if a user trays to add duplicates.
        unique_together = (
            "from_organization",
            "to_organization",
        )
        verbose_name = _("Pending publish request")
        verbose_name_plural = _("Pending publish requests")

    def __str__(self):
        return (
            f"{self.from_organization} would like to publish for {self.to_organization}"
        )

    def clean(self):
        errors = []
        perm_checker = ObjectPermissionChecker(
            user_or_group=self.from_organization)
        if perm_checker.has_perm(perm='accounts.can_publish_for', obj=self.to_organization):
            errors.append(
                str(self.from_organization)
                + _(" can already publish for ")
                + str(self.to_organization)
            )

        if self.from_organization == self.to_organization:
            errors.append(
                "You can not request publishing rights for two equal organizations."
            )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self._state.adding:
            super().save(*args, **kwargs)
        elif self.is_accepted:
            # acceptance is a decision with consequences, not a field
            # update: ``accept`` records it, grants through the requesting
            # organization's publisher role and retires the request row -
            # the shape ``save()`` already had, with the two warts of the
            # old shortcut gone (it granted the reverse direction and to the
            # whole organization, #740)
            self.accept()
        # an update which is neither creation nor acceptance changes
        # nothing: the request row carries no editable state after it is
        # stored - the activation window of ``BaseInternalRequest`` still
        # expires it on the next save attempt.

    def accept(self, granted_by=None):
        """Grant what the request asked for, then retire the request row.

        ``from_organization`` asked to publish for ``to_organization``; after
        acceptance (decision Q2 and the story of #740):

        * ``to_organization`` answers ``publishers`` with
          ``from_organization``, because the grant
          ``accounts.can_publish_for_organization`` over it now sits on the
          **group of the requesting organization's ``resource_publisher``
          role** - role-scoped, so leaving the role revokes everything at
          once, instead of the old grant onto the whole organization;
        * the existing services of ``to_organization`` carry the object
          grants of ``registry.models.shares.publisher_actions`` onto that
          same role group - ``view`` so the publisher reaches the object
          through the facade's object axis, ``publish`` on the capability
          carrier; services registered for ``to_organization`` afterwards
          receive the same grants from the creation bootstrap of
          ``accounts.signals``;
        * the request row is gone, as it was before this issue - its
            decision now lives in the grant rows with ``granted_by`` and
            ``created_at`` next to them (#741 reads those back).

        The write is one transaction: an acceptance which granted some
        resources and then died is the split state #727 retires. A role
        which does not exist refuses with a ``ValidationError`` - silence
        would answer the requester with "accepted" and nothing behind it.
        """
        # late imports: ``accounts.models.roles`` imports this module, and
        # the registry models reach back into accounts for their owner
        from accounts.models.roles import RESOURCE_PUBLISHER_ROLE, Role
        from registry.models.service import (WebFeatureService,
                                             WebMapService)
        from registry.models.shares import grant_actions, publisher_actions

        publisher_role = Role.objects.for_org(
            self.from_organization).with_definition(
                RESOURCE_PUBLISHER_ROLE).first()
        if publisher_role is None:
            raise ValidationError(
                _("The requesting organization %(from_organization)s has "
                  "no active publisher role to accept the publishing "
                  "request of %(to_organization)s with."),
                code="no_publisher_role",
                params={"from_organization": str(self.from_organization),
                        "to_organization": str(self.to_organization)})

        with transaction.atomic():
            self.to_organization.grant_publish_for_group(
                publisher_role.group, granted_by=granted_by)
            services = list(
                WebMapService.objects.filter(owner=self.to_organization))
            services += list(
                WebFeatureService.objects.filter(
                    owner=self.to_organization))
            for service in services:
                grant_actions(service, publisher_role.group,
                              publisher_actions(service),
                              granted_by=granted_by)
            self.delete()
        return publisher_role
