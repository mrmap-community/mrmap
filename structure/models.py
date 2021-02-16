import uuid
from django.contrib.auth.models import AbstractUser, Group
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

import json

from django_bootstrap_swt.components import LinkButton, Tag, Badge
from django_bootstrap_swt.enums import ButtonColorEnum, TextColorEnum, BadgeColorEnum, TooltipPlacementEnum

from MrMap.icons import IconEnum
from MrMap.management.commands.setup_settings import DEFAULT_ROLE_NAME
from MrMap.themes import FONT_AWESOME_ICONS
from MrMap.validators import validate_pending_task_enum_choices
from service.helper.crypto_handler import CryptoHandler
from service.helper.enums import OGCServiceEnum, MetadataEnum, PendingTaskEnum
from structure.permissionEnums import PermissionEnum
from structure.settings import USER_ACTIVATION_TIME_WINDOW


class ErrorReport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    message = models.TextField()
    traceback = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('MrMapGroup', null=True, blank=True, on_delete=models.SET_NULL)

    def generate_report(self):
        import socket
        try:
            hostname = socket.gethostname()
        except:
            hostname = 'localhost'
        report = f"This is an error report from host '{hostname}'\n" \
                 f"The error occurs on {self.timestamp}\n" \
                 f"This report is generated by group: {self.created_by}\n"\
                 "-------------------------------------------------\n"\
                 f"{self.message}"\
                 "-------------------------------------------------\n" \
                 f"{self.traceback}"
        return report


class PendingTask(models.Model):
    task_id = models.CharField(max_length=500, null=True, blank=True)
    description = models.TextField()
    progress = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(100)], default=0.0)
    remaining_time = models.DurationField(blank=True, null=True)
    is_finished = models.BooleanField(default=False)
    created_by = models.ForeignKey('MrMapGroup', null=True, blank=True, on_delete=models.DO_NOTHING)
    error_report = models.ForeignKey('ErrorReport', null=True, blank=True, on_delete=models.SET_NULL)
    type = models.CharField(max_length=500, null=True, blank=True, choices=PendingTaskEnum.as_choices(), validators=[validate_pending_task_enum_choices])

    def __str__(self):
        return self.task_id

    @property
    def service_uri(self):
        return str(json.loads(self.description).get('service', "resource_name_missing")) if 'service' in json.loads(self.description) else _('unknown')

    @property
    def phase(self):
        return str(json.loads(self.description).get('phase', "phase_information_missing")) if 'phase' in json.loads(self.description) else _('unknown')

    @property
    def action_buttons(self):
        actions = [LinkButton(url=self.remove_view_uri,
                              content=FONT_AWESOME_ICONS["WINDOW_CLOSE"],
                              color=ButtonColorEnum.DANGER,
                              tooltip=_("Cancle this task"), )]
        if self.error_report:
            actions.append(LinkButton(url=self.error_report_uri,
                                      content=FONT_AWESOME_ICONS["CSW"],
                                      color=ButtonColorEnum.WARNING,
                                      tooltip=_("Download the error report as text file."), ))
        return actions

    @property
    def status_icons(self):
        json_description = json.loads(self.description)
        if 'ERROR' in json_description.get('phase', ""):
            status = [Tag(tag='i', attrs={"class": [IconEnum.ERROR.value, TextColorEnum.DANGER.value]},
                          tooltip='This task stopped with error.', )]
        else:
            status = [Tag(tag='i', attrs={"class": [IconEnum.PLAY.value, TextColorEnum.SUCCESS.value]},
                          tooltip='This task is still running.', )]
        return status

    @property
    def remove_view_uri(self):
        return reverse('structure:remove-task', args=(self.pk,))

    @property
    def error_report_uri(self):
        return reverse('structure:generate-error-report', args=(self.error_report.pk,))


class Permission(models.Model):
    name = models.CharField(max_length=500, choices=PermissionEnum.as_choices(), unique=True)

    def __str__(self):
        return str(self.name)

    def get_permission_set(self) -> set:
        p_list = set()
        perms = self.__dict__
        if perms.get("id", None) is not None:
            del perms["id"]
        if perms.get("_state", None) is not None:
            del perms["_state"]
        for perm_key, perm_val in perms.items():
            if perm_val:
                p_list.add(perm_key)
        return p_list


class Role(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    permissions = models.ManyToManyField(Permission)

    def __str__(self):
        return self.name

    def has_permission(self, perm: PermissionEnum):
        """ Checks whether a permission can be found inside this role

        Args:
            perm (PermissionEnum): The permission to be checked
        Returns:
             bool
        """
        return self.permissions.filter(
            name=perm.value
        ).exists()


class Contact(models.Model):
    person_name = models.CharField(max_length=200, default="", null=True, blank=True, verbose_name=_("Contact person"))
    email = models.CharField(max_length=100, default="", null=True, blank=True, verbose_name=_('E-Mail'))
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


class Organization(Contact):
    organization_name = models.CharField(max_length=255, null=True, default="", verbose_name=_('Organization name'))
    description = models.TextField(default="",
                                   null=True,
                                   blank=True,
                                   verbose_name=_('description'),)
    parent = models.ForeignKey('self',
                               on_delete=models.DO_NOTHING,
                               blank=True,
                               null=True,
                               verbose_name=_('Parent organization'),
                               help_text=_('Configure a inheritance structure for this Organization'))
    is_auto_generated = models.BooleanField(default=True,
                                            verbose_name=_('autogenerated'),
                                            help_text=_('Autogenerated organizations are resolved from registered resources.'))
    created_by = models.ForeignKey('MrMapUser',
                                   related_name='created_by',
                                   on_delete=models.SET_NULL,
                                   null=True,
                                   blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "organization_name",
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
                    "description",
                ],
                name="unique organizations"
            )
        ]

    def __str__(self):
        if self.organization_name is None:
            return ""
        return self.organization_name

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        self.check_circular_configuration(self)
        super().save(force_insert, force_update, using, update_fields)

    @classmethod
    def check_circular_configuration(cls, instance):
        if instance.parent is not None:
            if instance == instance.parent:
                raise ValidationError(_("Circular configuration of parent organization detected."))
            else:
                _parent = instance.parent.parent
                while _parent is not None:
                    if instance == _parent:
                        raise ValidationError(_("Circular configuration of parent organization detected."))
                    else:
                        _parent = _parent.parent

    def get_absolute_url(self):
        return self.detail_view_uri

    @classmethod
    def get_add_action(cls):
        icon = Tag(tag='i', attrs={"class": [IconEnum.ADD.value]}).render()
        st_text = Tag(tag='div', attrs={"class": ['d-lg-none']}, content=icon).render()
        gt_text = Tag(tag='div', attrs={"class": ['d-none', 'd-lg-block']},
                      content=icon + _(' new organization').__str__()).render()
        return LinkButton(content=st_text + gt_text,
                          color=ButtonColorEnum.SUCCESS,
                          url=reverse('structure:organization_new'),
                          needs_perm=PermissionEnum.CAN_EDIT_GROUP.value)

    @property
    def detail_view_uri(self):
        return reverse('structure:organization_details', args=[self.pk, ])

    @property
    def add_view_uri(self):
        return reverse('structure:organization_new', args=[self.pk, ])

    @property
    def edit_view_uri(self):
        return reverse('structure:organization_edit', args=[self.pk, ])

    @property
    def remove_view_uri(self):
        return reverse('structure:organization_remove', args=[self.pk, ])

    def get_actions(self):
        add_icon = Tag(tag='i', attrs={"class": [IconEnum.ADD.value]}).render()
        st_pub_text = Tag(tag='div', attrs={"class": ['d-lg-none']}, content=add_icon).render()
        gt_pub_text = Tag(tag='div', attrs={"class": ['d-none', 'd-lg-block']},
                          content=add_icon + _(' become publisher').__str__()).render()
        edit_icon = Tag(tag='i', attrs={"class": [IconEnum.EDIT.value]}).render()
        st_edit_text = Tag(tag='div', attrs={"class": ['d-lg-none']}, content=edit_icon).render()
        gt_edit_text = Tag(tag='div', attrs={"class": ['d-none', 'd-lg-block']},
                           content=edit_icon + _(' edit').__str__()).render()
        actions = [
            LinkButton(url=f"{reverse('structure:publish_request_new',)}?organization={self.id}",
                       content=st_pub_text + gt_pub_text,
                       color=ButtonColorEnum.SUCCESS,
                       tooltip=format_html(
                           _(f"Become publisher for organization <strong>{self.organization_name} [{self.id}]</strong>")),
                       tooltip_placement=TooltipPlacementEnum.LEFT,
                       needs_perm=PermissionEnum.CAN_REQUEST_TO_BECOME_PUBLISHER.value),
            LinkButton(url=self.edit_view_uri,
                       content=st_edit_text + gt_edit_text,
                       color=ButtonColorEnum.WARNING,
                       tooltip=format_html(_(f"Edit <strong>{self.organization_name} [{self.id}]</strong> organization")),
                       tooltip_placement=TooltipPlacementEnum.LEFT,
                       needs_perm=PermissionEnum.CAN_EDIT_ORGANIZATION.value),
        ]

        if not self.is_auto_generated:
            remove_icon = Tag(tag='i', attrs={"class": [IconEnum.DELETE.value]}).render()
            st_remove_text = Tag(tag='div', attrs={"class": ['d-lg-none']}, content=remove_icon).render()
            gt_remove_text = Tag(tag='div', attrs={"class": ['d-none', 'd-lg-block']},
                                 content=remove_icon + _(' remove').__str__()).render()
            actions.append(LinkButton(url=self.remove_view_uri,
                                      content=st_remove_text + gt_remove_text,
                                      color=ButtonColorEnum.DANGER,
                                      tooltip=format_html(_(f"Remove <strong>{self.organization_name} [{self.id}]</strong> organization")),
                                      tooltip_placement=TooltipPlacementEnum.LEFT,
                                      needs_perm=PermissionEnum.CAN_DELETE_ORGANIZATION.value))
        return actions


class MrMapGroup(Group):
    description = models.TextField(blank=True, verbose_name=_('Description'))
    parent_group = models.ForeignKey('self', on_delete=models.DO_NOTHING, blank=True, null=True,
                                     related_name="children_groups")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True,
                                     related_name="organization_groups")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, null=True)
    publish_for_organizations = models.ManyToManyField('Organization', related_name='publishers', blank=True)
    created_by = models.ForeignKey('MrMapUser', on_delete=models.DO_NOTHING)
    is_public_group = models.BooleanField(default=False)
    is_permission_group = models.BooleanField(default=False)

    def __str__(self):
        return self.name

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None, user=None):
        # todo: check if this could be done with the default attribute of the role field
        from MrMap.management.commands.setup_settings import DEFAULT_ROLE_NAME
        if self.role is None:
            default_role = Role.objects.get(name=DEFAULT_ROLE_NAME)
            self.role = default_role

        is_new = False
        if self._state.adding:
            is_new = True
            if user:
                self.created_by = user
            else:
                raise ValidationError('user must be passed to this save function for new instances')

        super().save(force_insert, force_update, using, update_fields)
        if is_new:
            self.user_set.add(user)

    def delete(self, using=None, keep_parents=False, force=False):
        if (self.is_permission_group or self.is_public_group) and not force:
            raise ValidationError(_("Group {} is an important main group and therefore can not be removed.").format(_(self.name)))
        return super().delete(using=using, keep_parents=keep_parents)

    def get_absolute_url(self):
        return self.detail_view_uri

    @classmethod
    def get_add_action(cls):
        return LinkButton(content=FONT_AWESOME_ICONS['ADD'] + _(' New group').__str__(),
                          color=ButtonColorEnum.SUCCESS,
                          url=reverse('structure:group_new'),
                          needs_perm=PermissionEnum.CAN_EDIT_GROUP.value)

    @property
    def detail_view_uri(self):
        return reverse('structure:group_details', args=[self.pk, ])

    @property
    def add_view_uri(self):
        return reverse('structure:group_new')

    @property
    def edit_view_uri(self):
        return reverse('structure:group_edit', args=[self.pk, ])

    @property
    def remove_view_uri(self):
        return reverse('structure:group_remove', args=[self.pk, ])

    def remove_member_view_uri(self, user):
        return reverse('structure:group_members_remove', args=[self.pk, user.id])

    @property
    def new_publisher_requesst_uri(self):
        return f"{reverse('structure:publish_request_new')}?group={self.pk}"

    def get_actions(self):
        actions = []
        if not self.is_permission_group:
            edit_icon = Tag(tag='i', attrs={"class": [IconEnum.EDIT.value]}).render()
            st_edit_text = Tag(tag='div', attrs={"class": ['d-lg-none']}, content=edit_icon).render()
            gt_edit_text = Tag(tag='div', attrs={"class": ['d-none', 'd-lg-block']}, content=edit_icon + _(' Edit').__str__()).render()
            actions.append(LinkButton(url=self.edit_view_uri,
                                      content=st_edit_text + gt_edit_text,
                                      color=ButtonColorEnum.WARNING,
                                      tooltip=_(f"Edit <strong>{self.name}</strong>"),
                                      needs_perm=PermissionEnum.CAN_EDIT_GROUP.value))
            delete_icon = Tag(tag='i', attrs={"class": [IconEnum.DELETE.value]}).render()
            st_delete_text = Tag(tag='div', attrs={"class": ['d-lg-none']}, content=delete_icon).render()
            gt_delete_text = Tag(tag='div', attrs={"class": ['d-none', 'd-lg-block']}, content=delete_icon + _(' Delete').__str__()).render()
            actions.append(LinkButton(url=self.remove_view_uri,
                                      content=st_delete_text + gt_delete_text,
                                      color=ButtonColorEnum.DANGER,
                                      tooltip=_(f"Remove <strong>{self.name}</strong>"),
                                      needs_perm=PermissionEnum.CAN_DELETE_GROUP.value))
        return actions

    @property
    def new_publisher_request_action(self):
        add_icon = Tag(tag='i', attrs={"class": [IconEnum.ADD.value]}).render()
        st_text = Tag(tag='div', attrs={"class": ['d-lg-none']}, content=add_icon).render()
        gt_text = Tag(tag='div', attrs={"class": ['d-none', 'd-lg-block']}, content=add_icon + _(' become publisher').__str__()).render()
        return LinkButton(url=self.new_publisher_requesst_uri,
                          content=st_text + gt_text,
                          color=ButtonColorEnum.SUCCESS,
                          tooltip=_("Become rights to publish"),
                          needs_perm=PermissionEnum.CAN_REQUEST_TO_BECOME_PUBLISHER.value)

    @property
    def show_pending_requests(self):
        icon = Tag(tag='i', attrs={"class": [IconEnum.PUBLISHERS.value]}).render()
        count = Badge(content=f" {PublishRequest.objects.filter(group=self).count()}", color=BadgeColorEnum.SECONDARY).render()
        st_text = Tag(tag='div', attrs={"class": ['d-lg-none']}, content=icon + count).render()
        gt_text = Tag(tag='div', attrs={"class": ['d-none', 'd-lg-block']},
                      content=icon + _(' pending requests').__str__() + count).render()
        return LinkButton(url=f"{reverse('structure:publish_request_overview')}?group={self.pk}",
                          content=f"{st_text}{gt_text}",
                          color=ButtonColorEnum.INFO,
                          tooltip=_(f"see pending requests for {self}"),
                          needs_perm=PermissionEnum.CAN_REQUEST_TO_BECOME_PUBLISHER.value)


class Theme(models.Model):
    objects = None
    name = models.CharField(max_length=10, unique=True)

    def __str__(self):
        return self.name


class MrMapUser(AbstractUser):
    salt = models.CharField(max_length=500)
    organization = models.ForeignKey('Organization', related_name='primary_users', on_delete=models.SET_NULL, null=True,
                                     blank=True)
    confirmed_newsletter = models.BooleanField(default=False, verbose_name=_("I want to sign up for the newsletter"))
    confirmed_survey = models.BooleanField(default=False, verbose_name=_("I want to participate in surveys"))
    confirmed_dsgvo = models.DateTimeField(auto_now_add=True,
                                           verbose_name=_("I understand and accept that my data will be automatically processed and securely stored, as it is stated in the general data protection regulation (GDPR)."))
    theme = models.ForeignKey('Theme', related_name='user_theme', on_delete=models.DO_NOTHING, null=True, blank=True)

    def __str__(self):
        return self.username

    def get_absolute_url(self):
        return reverse('password_change_done')

    def get_services(self, type: OGCServiceEnum = None):
        """ Returns all services which are related to the user

        Returns:
             md_list (list): A list containing all services related to the user
        """
        return list(self.get_services_as_qs(type))

    def get_services_as_qs(self, type: OGCServiceEnum = None):
        """ Returns all services which are related to the user

        Returns:
             md_list:
        """
        from service.models import Metadata
        md_list = Metadata.objects.filter(
            service__is_root=True,
            created_by__in=self.get_groups(),
            service__is_deleted=False,
        ).order_by("title")
        if type is not None:
            md_list = md_list.filter(service__service_type__name=type.name.lower())
        return md_list

    def get_metadatas_as_qs(self, type: MetadataEnum = None, inverse_match: bool = False):
        """ Returns all metadatas which are related to the user

        Returns:
             md_list:
        """
        from service.models import Metadata

        md_list = Metadata.objects.filter(
            created_by__in=self.get_groups(),
        ).order_by("title")
        if type is not None:
            if inverse_match:
                md_list = md_list.all().exclude(metadata_type=type.name.lower())
            else:
                md_list = md_list.filter(metadata_type=type.name.lower())
        return md_list

    def get_datasets_as_qs(self, user_groups=None, count=False):
        """ Returns all datasets which are related to the user

        Returns:
             md_list:
        """
        from service.models import Metadata
        if user_groups is None:
            user_groups = self.get_groups()

        if count:
            md_list = Metadata.objects.filter(
                metadata_type=MetadataEnum.DATASET.value,
                created_by__in=user_groups,
            ).count()
        else:
            md_list = Metadata.objects.filter(
                metadata_type=MetadataEnum.DATASET.value,
                created_by__in=user_groups,
            ).prefetch_related(
                "related_metadata",
                "related_metadata__metadata_to",
            ).order_by("title")
        return md_list

    def get_groups(self, filter_by: dict = {}):
        """ Returns a queryset of all MrMapGroups related to the user

        filter_by takes the same attributes and properties as a regular queryset filter call.
        So 'name__icontains=test' becomes 'name__icontains: test'

        Example filter_by:
            filter_by = {
                "name__icontains": "test",
            }

        Args:
            filter_by (dict): Accepts a dict for pre-filtering before returning a queryset
        Returns:
             queryset
        """
        groups = MrMapGroup.objects.filter(
            id__in=self.groups.all().values('id')
        ).filter(
            **filter_by
        ).prefetch_related(
            "role__permissions",
        )
        return groups

    def get_permissions(self, group: MrMapGroup = None) -> set:
        """Returns a set containing all permission identifiers as strings in a list.

        The list is generated by fetching all permissions from all groups the user is part of.
        Alternatively the list is generated by fetching all permissions from a special group.

        Args:
            group: The group object
        Returns:
             A set of permission strings
        """
        if group is not None:
            groups = MrMapGroup.objects.filter(id=group.id)
        else:
            groups = self.get_groups().prefetch_related("role__permissions")

        all_perm = set(groups.values_list("role__permissions__name", flat=True))

        return all_perm

    def has_perm(self, perm, obj=None) -> bool:
        # Active superusers have all permissions.
        if self.is_active and self.is_superuser:
            return True

        has_perm = self.get_groups().filter(
            role__permissions__name=perm
        )
        has_perm = has_perm.exists()
        return has_perm

    def has_perms(self, perm_list, obj=None) -> bool:
        has_perm = self.get_groups().filter(
            role__permissions__name__in=perm_list
        )
        has_perm = has_perm.exists()
        return has_perm

    def create_activation(self):
        """ Create an activation object

        Returns:
             nothing
        """
        # user does not exist yet! We need to create an activation object
        user_activation = UserActivation()
        user_activation.user = self
        user_activation.activation_until = timezone.now() + timezone.timedelta(hours=USER_ACTIVATION_TIME_WINDOW)
        sec_handler = CryptoHandler()
        user_activation.activation_hash = sec_handler.sha256(
            self.username + self.salt + str(user_activation.activation_until))
        user_activation.save()


class UserActivation(models.Model):
    user = models.ForeignKey(MrMapUser, null=False, blank=False, on_delete=models.CASCADE)
    activation_until = models.DateTimeField(null=True)
    activation_hash = models.CharField(primary_key=True, max_length=500, null=False, blank=False)

    def __str__(self):
        return self.user.username


class GroupActivity(models.Model):
    group = models.ForeignKey(MrMapGroup, on_delete=models.CASCADE)
    description = models.CharField(max_length=255, blank=True, null=True)
    user = models.ForeignKey(MrMapUser, on_delete=models.CASCADE, blank=True, null=True)
    metadata = models.CharField(max_length=255, blank=True, null=True)
    created_on = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.description


class BaseInternalRequest(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True)
    message = models.TextField(null=True, blank=True)
    activation_until = models.DateTimeField(null=True)
    created_on = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(MrMapUser, on_delete=models.SET_NULL, null=True)

    class Meta:
        abstract = True


class PublishRequest(BaseInternalRequest):
    group = models.ForeignKey(MrMapGroup, verbose_name=_('group'), related_name="publish_requests", on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, verbose_name=_('organization'), related_name="publish_requests", on_delete=models.CASCADE)
    is_accepted = models.BooleanField(verbose_name=_('accepted'), default=False)

    class Meta:
        # It shall be restricted to create multiple requests objects for the same organization per group. This unique
        # constraint will also raise a form error if a user trays to add duplicates.
        unique_together = ('group', 'organization',)

    def __str__(self):
        return "{} > {}".format(self.group.name, self.organization.organization_name)

    def get_absolute_url(self):
        return f"{reverse('structure:publish_request_overview')}?group={self.group.id}&organization={self.organization.id}"

    @property
    def accept_publish_request_uri(self):
        return reverse('structure:publish_request_accept', args=[self.pk])

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        if not self._state.adding:
            if self.is_accepted:
                self.group.publish_for_organizations.add(self.organization)
            self.delete()
        else:
            super().save(force_insert, force_update, using, update_fields)


class GroupInvitationRequest(BaseInternalRequest):
    invited_user = models.ForeignKey(MrMapUser, on_delete=models.CASCADE, related_name="group_invitations")
    to_group = models.ForeignKey(MrMapGroup, on_delete=models.CASCADE)

    def __str__(self):
        return "{} > {}".format(self.invited_user.username, self.to_group)

