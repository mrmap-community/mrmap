import datetime

from django.contrib.auth.models import AbstractUser, Group
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone

from service.helper.crypto_handler import CryptoHandler
from service.helper.enums import OGCServiceEnum, MetadataEnum
from structure.settings import USER_ACTIVATION_TIME_WINDOW


class PendingTask(models.Model):
    task_id = models.CharField(max_length=500, null=True, blank=True)
    description = models.TextField()
    progress = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(100)])
    remaining_time = models.DurationField(blank=True, null=True)
    is_finished = models.BooleanField(default=False)
    created_by = models.ForeignKey('MrMapGroup', null=True, blank=True, on_delete=models.DO_NOTHING)

    def __str__(self):
        return self.task_id


class Permission(models.Model):
    can_create_organization = models.BooleanField(default=False)
    can_edit_organization = models.BooleanField(default=False)
    can_delete_organization = models.BooleanField(default=False)

    can_create_group = models.BooleanField(default=False)
    can_delete_group = models.BooleanField(default=False)
    can_edit_group = models.BooleanField(default=False)

    can_add_user_to_group = models.BooleanField(default=False)
    can_remove_user_from_group = models.BooleanField(default=False)

    can_edit_group_role = models.BooleanField(default=False)

    can_activate_service = models.BooleanField(default=False)
    can_update_service = models.BooleanField(default=False)
    can_register_service = models.BooleanField(default=False)
    can_remove_service = models.BooleanField(default=False)
    can_edit_metadata_service = models.BooleanField(default=False)
    can_edit_metadata_public_id = models.BooleanField(default=False)

    can_add_dataset_metadata = models.BooleanField(default=False)
    can_edit_dataset_metadata = models.BooleanField(default=False)
    can_remove_dataset_metadata = models.BooleanField(default=False)
    can_restore_dataset_metadata = models.BooleanField(default=False)

    can_toggle_publish_requests = models.BooleanField(default=False)

    can_create_monitoring_setting = models.BooleanField(default=False)
    can_edit_monitoring_setting = models.BooleanField(default=False)
    can_delete_monitoring_setting = models.BooleanField(default=False)

    can_remove_publisher = models.BooleanField(default=False)
    can_request_to_become_publisher = models.BooleanField(default=False)

    can_generate_api_token = models.BooleanField(default=False)

    can_access_logs = models.BooleanField(default=False)
    can_download_logs = models.BooleanField(default=False)

    # more permissions coming

    def __str__(self):
        return str(self.id)

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
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, null=True)

    def __str__(self):
        return self.name


class Contact(models.Model):
    person_name = models.CharField(max_length=200, default="", null=True, blank=True)
    email = models.CharField(max_length=100, null=True, blank=True)
    phone = models.CharField(max_length=100, null=True, blank=True)
    facsimile = models.CharField(max_length=100, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    postal_code = models.CharField(max_length=100, null=True, blank=True)
    address_type = models.CharField(max_length=100, null=True, blank=True)
    address = models.CharField(max_length=100, null=True, blank=True)
    state_or_province = models.CharField(max_length=100, null=True, blank=True)
    country = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        return self.person_name

    class Meta:
        abstract = True


class Organization(Contact):
    organization_name = models.CharField(max_length=255, null=True, default="")
    description = models.TextField(null=True, blank=True)
    parent = models.ForeignKey('self', on_delete=models.DO_NOTHING, blank=True, null=True)
    is_auto_generated = models.BooleanField(default=True)
    created_by = models.ForeignKey('MrMapUser', related_name='created_by', on_delete=models.SET_NULL, null=True,
                                   blank=True)

    def __str__(self):
        if self.organization_name is None:
            return ""
        return self.organization_name


class MrMapGroup(Group):
    description = models.TextField(blank=True, null=True)
    parent_group = models.ForeignKey('self', on_delete=models.DO_NOTHING, blank=True, null=True,
                                     related_name="children_groups")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True,
                                     related_name="organization_groups")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, null=True)
    publish_for_organizations = models.ManyToManyField('Organization', related_name='can_publish_for', blank=True)
    created_by = models.ForeignKey('MrMapUser', on_delete=models.DO_NOTHING)
    is_public_group = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class Theme(models.Model):
    name = models.CharField(max_length=10, unique=True)

    def __str__(self):
        return self.name


class MrMapUser(AbstractUser):
    salt = models.CharField(max_length=500)
    organization = models.ForeignKey('Organization', related_name='primary_users', on_delete=models.SET_NULL, null=True,
                                     blank=True)
    confirmed_newsletter = models.BooleanField(default=False)
    confirmed_survey = models.BooleanField(default=False)
    confirmed_dsgvo = models.DateTimeField(auto_now_add=True, null=True,
                                           blank=True)  # ToDo: For production this is not supposed to be nullable!!!
    theme = models.ForeignKey('Theme', related_name='user_theme', on_delete=models.DO_NOTHING, null=True, blank=True)
    permissions_cache = None
    groups_cache = None

    def __str__(self):
        return self.username

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
                "related_metadata"
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

        Returns:
             queryset
        """
        if self.groups_cache is not None:
            return self.groups_cache

        groups = MrMapGroup.objects.filter(
            id__in=self.groups.all().values('id')
        ).filter(
            **filter_by
        ).prefetch_related(
            "role",
            "role__permission",
        )

        # Hold these data for more actions so we do not need to fetch it again from the db
        self.groups_cache = groups
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
        if self.permissions_cache is not None:
            return self.permissions_cache

        all_perm = set()
        if group is not None:
            groups = [group]
        else:
            groups = self.get_groups()

        for group in groups:
            perm = group.role.permission
            for field_key, field_val in perm.__dict__.items():
                if field_val is True:
                    all_perm.add(field_key)

        # Hold these data for more actions so we do not need to fetch it again from the db
        self.permissions_cache = all_perm
        return all_perm

    def has_permission(self, permission_needed: Permission):
        """ Checks if needed permissions are provided by the users permission

        Args:
            permission_needed: The permission that is needed
        Returns:
             True if all permissions are satisfied. False otherwise
        """
        if permission_needed is None:
            return True

        all_perms = self.get_permissions()
        permissions_needed = permission_needed.get_permission_set()

        return permissions_needed.issubset(all_perms)

    def create_activation(self):
        """ Create an activation object

        Returns:
             nothing
        """
        # user does not exist yet! We need to create an activation object
        user_activation = UserActivation()
        user_activation.user = self
        user_activation.activation_until = timezone.now() + datetime.timedelta(hours=USER_ACTIVATION_TIME_WINDOW)
        sec_handler = CryptoHandler()
        user_activation.activation_hash = sec_handler.sha256(
            self.username + self.salt + str(user_activation.activation_until))
        user_activation.save()


class UserActivation(models.Model):
    user = models.ForeignKey(MrMapUser, null=False, blank=False, on_delete=models.CASCADE)
    activation_until = models.DateTimeField(null=True)
    activation_hash = models.CharField(max_length=500, null=False, blank=False)

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


class PendingRequest(models.Model):
    type = models.CharField(max_length=255)  # defines what type of request this is
    group = models.ForeignKey(MrMapGroup, related_name="pending_publish_requests", on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, related_name="pending_publish_requests", on_delete=models.CASCADE)
    message = models.TextField(null=True, blank=True)
    activation_until = models.DateTimeField(null=True)
    created_on = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.group.name + " > " + self.organization.organization_name
