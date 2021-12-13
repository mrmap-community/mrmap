from accounts.settings import DEFAULT_REQUEST_ACIVATION_TIME
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import QuerySet
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from extras.models import CommonInfo

from guardian.core import ObjectPermissionChecker
from guardian.shortcuts import assign_perm, get_objects_for_group, remove_perm


class Contact(models.Model):
    """
    An abstract model which adds fields to store the contact specific fields. All fields can be
    null to store bad quality metadata as well.
    """

    person_name = models.CharField(
        max_length=200,
        default="",
        null=True,
        blank=True,
        verbose_name=_("Contact person"),
    )
    email = models.EmailField(
        max_length=100, default="", null=True, blank=True, verbose_name=_("E-Mail")
    )
    phone = models.CharField(
        max_length=100, default="", null=True, blank=True, verbose_name=_("Phone")
    )
    facsimile = models.CharField(
        max_length=100, default="", null=True, blank=True, verbose_name=_("Facsimile")
    )
    city = models.CharField(
        max_length=100, default="", null=True, blank=True, verbose_name=_("City")
    )
    postal_code = models.CharField(
        max_length=100, default="", null=True, blank=True, verbose_name=_("Postal code")
    )
    address_type = models.CharField(
        max_length=100,
        default="",
        null=True,
        blank=True,
        verbose_name=_("Address type"),
    )
    address = models.CharField(
        max_length=100, default="", null=True, blank=True, verbose_name=_("Address")
    )
    state_or_province = models.CharField(
        max_length=100,
        default="",
        null=True,
        blank=True,
        verbose_name=_("State or province"),
    )
    country = models.CharField(
        max_length=100, default="", null=True, blank=True, verbose_name=_("Country")
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


class Organization(Group, CommonInfo, Contact):
    """
    A organization represents a real life organization like a authority, company etc. The name of the organization can
    be null to store bad quality metadata as well.
    """

    description = models.TextField(
        default="",
        null=True,
        blank=True,
        verbose_name=_("description"),
        help_text=_("Describe what this organization representing"),
    )

    class Meta(CommonInfo.Meta):
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

        Returns:
            all publishers for this organization (QuerySet)
        """
        return get_objects_for_group(group=self,
                                     perms='accounts.can_publish_for_organization',
                                     klass=Organization,
                                     accept_global_perms=False).exclude(pk=self.pk)

    @property
    def publishers(self) -> QuerySet:
        # TODO:
        return Organization.objects.none()

    def add_publisher(self, publisher) -> None:
        if isinstance(publisher, Organization):
            assign_perm(perm='accounts.can_publish_for_organization',
                        user_or_group=publisher, obj=self)
        else:
            raise TypeError('given publisher is not from type Organization')

    def remove_publisher(self, publisher) -> None:
        if isinstance(publisher, Organization):
            remove_perm(perm='accounts.can_publish_for_organization',
                        user_or_group=publisher, obj=self)
        else:
            raise TypeError('given publisher is not from type Organization')


class BaseInternalRequest(CommonInfo):
    message = models.TextField(null=True, blank=True)
    activation_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self._state.adding:
            if not self.activation_until:
                self.activation_until = timezone.now() + timezone.timedelta(
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

    class Meta(CommonInfo.Meta):
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
                self.from_organization.__str__()
                + _(" can already publish for ").__str__()
                + self.to_organization.__str__()
            )

        if self.from_organization == self.to_organization:
            errors.append(
                "You can not request publishing rights for two equal organizations."
            )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            if self.is_accepted:
                self.from_organization.add_publisher(self.to_organization)
                self.delete()
        else:
            super().save(*args, **kwargs)
