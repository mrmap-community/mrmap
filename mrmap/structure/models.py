from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, QuerySet, F
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from acl.models.acl import AccessControlList
from main.models import UuidPk, CommonInfo
from django_bootstrap_swt.components import LinkButton, Tag
from django_bootstrap_swt.enums import ButtonColorEnum
from MrMap.icons import IconEnum, get_icon
from MrMap.messages import REQUEST_ACTIVATION_TIMEOVER
from structure.enums import PendingTaskEnum
from structure.permissionEnums import PermissionEnum
from users.settings import default_request_activation_time
from django_celery_results.models import TaskResult
from django.db.models import Case, When
from django.contrib.postgres.fields import ArrayField


class Contact(models.Model):
    """
    An abstract model which adds fields to store the contact specific fields. All fields can be
    null to store bad quality metadata as well.
    """
    person_name = models.CharField(max_length=200, default="", null=True, blank=True, verbose_name=_("Contact person"))
    email = models.EmailField(max_length=100, default="", null=True, blank=True, verbose_name=_('E-Mail'))
    phone = models.CharField(max_length=100, default="", null=True, blank=True, verbose_name=_('Phone'))
    facsimile = models.CharField(max_length=100, default="", null=True, blank=True, verbose_name=_("Facsimile"))
    city = models.CharField(max_length=100, default="", null=True, blank=True, verbose_name=_("City"))
    postal_code = models.CharField(max_length=100, default="", null=True, blank=True, verbose_name=_("Postal code"))
    address_type = models.CharField(max_length=100, default="", null=True, blank=True, verbose_name=_("Address type"))
    address = models.CharField(max_length=100, default="", null=True, blank=True, verbose_name=_("Address"))
    state_or_province = models.CharField(max_length=100, default="", null=True, blank=True, verbose_name=_("State or province"))
    country = models.CharField(max_length=100, default="", null=True, blank=True, verbose_name=_("Country"))

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
            "description",)


class Organization(UuidPk, CommonInfo, Contact):
    """
    A organization represents a real life organization like a authority, company etc. The name of the organization can
    be null to store bad quality metadata as well.
    """
    name = models.CharField(_('Name'),
                            default='',
                            help_text=_('The name of the organization'),
                            max_length=256)
    description = models.TextField(default="",
                                   null=True,
                                   blank=True,
                                   verbose_name=_('description'),
                                   help_text=_('Describe what this organization representing'))
    can_publish_for = models.ManyToManyField(to='self',
                                             through='OrganizationPublishRelation',
                                             related_name='publishers',
                                             related_query_name='publishers',
                                             blank=True)
    is_autogenerated = models.BooleanField(default=True)

    # todo: add parent/child field (mptt)

    class Meta:
        # define default ordering for this model. This is needed for django tables2 ordering. If we use just the
        # foreignkey as column accessor the ordering will be done by the primary key. To avoid this we need to define
        # the right default way here...
        ordering = ['name']
        verbose_name = _('Organization')
        verbose_name_plural = _('Organizations')

    def __str__(self):
        return self.name

    @property
    def icon(self):
        return get_icon(IconEnum.ORGANIZATION)

    def add_organization_publish_relation(self, to):
        relation, created = OrganizationPublishRelation.objects.get_or_create(
            from_organization=self,
            to_organization=to)
        return relation

    def remove_organization_publish_relation(self, to):
        OrganizationPublishRelation.objects.filter(
            from_organization=self,
            to_organization=to).delete()

    def get_publishers(self) -> QuerySet:
        """
        return all `Organization` objects which can publish for this `Organization.

        Returns:
            all publishers for this organization (QuerySet)
        """
        return self.can_publish_for.filter(from_organizations__to_organization=self)

    def get_publish_ables(self) -> QuerySet:
        """
        return all `Organization` objects which this `Organization` can publish for.

        Returns:
            all publish able organizations (QuerySet)
        """
        return self.can_publish_for.filter(to_organizations__from_organization=self)

    def get_acls(self) -> QuerySet:
        return AccessControlList.objects.filter(owned_by_org__pk=self.pk)

    def get_absolute_url(self) -> str:
        return reverse('structure:organization_view', args=[self.pk, ])

    @property
    def publishers_uri(self):
        return reverse('structure:organization_publisher_overview', args=[self.pk, ])

    @property
    def acls_uri(self):
        return reverse('structure:organization_acl_overview', args=[self.pk, ])


class OrganizationPublishRelation(models.Model):
    from_organization = models.ForeignKey(to=Organization, on_delete=models.CASCADE, related_name='from_organizations')
    to_organization = models.ForeignKey(to=Organization, on_delete=models.CASCADE, related_name='to_organizations')


class BaseInternalRequest(UuidPk, CommonInfo):
    message = models.TextField(null=True, blank=True)
    activation_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self._state.adding:
            if not self.activation_until:
                self.activation_until = timezone.now() + timezone.timedelta(days=default_request_activation_time)
        else:
            if timezone.now() > self.activation_until:
                self.delete()
                raise ValidationError(REQUEST_ACTIVATION_TIMEOVER)

        super().save(*args, **kwargs)


class PublishRequest(BaseInternalRequest):
    from_organization = models.ForeignKey(Organization,
                                          verbose_name=_('requesting organization'),
                                          related_name="from_pending_publish_requests",
                                          on_delete=models.CASCADE)
    to_organization = models.ForeignKey(Organization,
                                        verbose_name=_('requested organization'),
                                        related_name="to_pending_publish_requests",
                                        on_delete=models.CASCADE)
    is_accepted = models.BooleanField(verbose_name=_('accepted'), default=False)

    class Meta:
        # It shall be restricted to create multiple requests objects for the same organization per group. This unique
        # constraint will also raise a form error if a user trays to add duplicates.
        unique_together = ('from_organization', 'to_organization',)
        verbose_name = _('Pending publish request')
        verbose_name_plural = _('Pending publish requests')

    @property
    def icon(self):
        return get_icon(IconEnum.PUBLISHERS)

    def __str__(self):
        return f"{self.from_organization} would like to publish for {self.to_organization}"

    def get_absolute_url(self):
        return f"{reverse('structure:publish_request_overview')}?from_organization={self.from_organization.pk}&to_organization={self.to_organization.pk}"

    @property
    def accept_request_uri(self):
        return reverse('structure:publish_request_accept', args=[self.pk])

    @classmethod
    def get_add_action(cls):
        icon = Tag(tag='i', attrs={"class": [IconEnum.ADD.value]}).render()
        st_text = Tag(tag='div', attrs={"class": ['d-lg-none']}, content=icon).render()
        gt_text = Tag(tag='div', attrs={"class": ['d-none', 'd-lg-block']},
                      content=icon + _(' new publisher request').__str__()).render()
        return LinkButton(content=st_text + gt_text,
                          color=ButtonColorEnum.SUCCESS,
                          url=reverse('structure:publish_request_new'),
                          needs_perm=PermissionEnum.CAN_ADD_PUBLISH_REQUEST.value)

    def clean(self):
        errors = []
        if self.from_organization.can_publish_for.filter(id=self.to_organization.id).exists():
            errors.append(self.from_organization.__str__() + _(f' can already publish for ').__str__() + self.to_organization.__str__())
        if self.from_organization == self.to_organization:
            errors.append("You can not request publishing rights for two equal organizations.")
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            if self.is_accepted:
                self.from_organization.add_organization_publish_relation(self.to_organization)
                self.delete()
        else:
            super().save(*args, **kwargs)


class PendingTask(CommonInfo):
    status = models.CharField(
        max_length=50,
        default=PendingTaskEnum.PENDING.value,
        choices=PendingTaskEnum.as_choices(),
        verbose_name=_('task state'),
        help_text=_('Current state of the task being run'))
    sub_tasks = models.ManyToManyField(to=TaskResult,
                                       blank=True)
    phase = models.CharField(max_length=256,
                             default="")
    progress = models.FloatField(default=0.0,
                                 )
    done_at = models.DateTimeField(null=True,
                                   blank=True)

    class Meta:
        ordering = ["-done_at"]
