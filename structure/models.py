import datetime
from django.contrib.auth.hashers import check_password
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone

from service.helper.crypto_handler import CryptoHandler
from service.helper.enums import OGCServiceEnum
from structure.settings import USER_ACTIVATION_TIME_WINDOW


class PendingTask(models.Model):
    task_id = models.CharField(max_length=500, null=True, blank=True)
    description = models.TextField()
    progress = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(100)])
    is_finished = models.BooleanField(default=False)
    created_by = models.ForeignKey('Group', null=True, blank=True, on_delete=models.DO_NOTHING)

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

    can_toggle_publish_requests = models.BooleanField(default=False)
    can_remove_publisher = models.BooleanField(default=True)
    can_request_to_become_publisher = models.BooleanField(default=True)
    # more permissions coming

    def __str__(self):
        return str(self.id)

    def get_permission_list(self):
        p_list = []
        perms = self.__dict__
        if perms.get("id", None) is not None:
            del perms["id"]
        if perms.get("_state", None) is not None:
            del perms["_state"]
        for perm_key, perm_val in perms.items():
            if perm_val:
                p_list.append(perm_key)
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
    created_by = models.ForeignKey('User', related_name='created_by', on_delete=models.DO_NOTHING, null=True, blank=True)

    def __str__(self):
        if self.organization_name is None:
            return ""
        return self.organization_name


class Group(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    parent = models.ForeignKey('self', on_delete=models.DO_NOTHING, blank=True, null=True, related_name="children")
    organization = models.ForeignKey(Organization, on_delete=models.DO_NOTHING, null=True, blank=True, related_name="groups")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, null=True)
    publish_for_organizations = models.ManyToManyField('Organization', related_name='can_publish_for', blank=True)
    created_by = models.ForeignKey('User', on_delete=models.DO_NOTHING)

    def __str__(self):
        return self.name


class User(Contact):
    username = models.CharField(max_length=50)
    logged_in = models.BooleanField(default=False)
    salt = models.CharField(max_length=500)
    password = models.CharField(max_length=500)
    last_login = models.DateTimeField(null=True)
    created_on = models.DateTimeField(auto_now_add=True)
    groups = models.ManyToManyField('Group', related_name='users')
    organization = models.ForeignKey('Organization', related_name='primary_users', on_delete=models.DO_NOTHING, null=True, blank=True)
    confirmed_newsletter = models.BooleanField(default=False)
    confirmed_survey = models.BooleanField(default=False)
    confirmed_dsgvo = models.DateTimeField(null=True, blank=True) # ToDo: For production this is not supposed to be nullable!!!
    is_active = models.BooleanField(default=False)

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
            created_by__in=self.groups.all(),
            service__is_deleted=False,
        ).order_by("title")
        if type is not None:
            md_list = md_list.filter(service__servicetype__name=type.name.lower())
        return md_list



    def get_permissions(self, group: Group = None):
        """ Overloaded function. Returns a list containing all permission identifiers as strings in a list.

        The list is generated by fetching all permissions from all groups the user is part of.
        Alternatively the list is generated by fetching all permissions from a special group.

        Args:
            user: The user object
            group: The group object
        Returns:
             A list of permission strings
        """
        all_perm = []
        groups = []
        if group is not None:
            groups = [group]
        else :
            groups = self.groups.all()

        for group in groups:
            perm = group.role.permission
            for field_key, field_val in perm.__dict__.items():
                if field_val is True and field_key not in all_perm:
                    all_perm.append(field_key)
        return all_perm

    def has_permission(self, permission_needed: Permission):
        """ Checks if needed permissions are provided by the users permission

        Args:
            user: The user object
            permission_needed: The permission that is needed
        Returns:
             True if all permissions are satisfied. False otherwise
        """
        all_perms = self.get_permissions()
        permissions_needed = permission_needed.get_permission_list()
        for p_n in permissions_needed:
            if p_n not in all_perms:
                return False
        return True

    def is_password_valid(self, password: str):
        """ Checks if the incoming password is valid for the user

        Args:
            user: The user object which needs to be checked against
            password: The password that might match to the user
        Returns:
             True or False
        """
        return check_password(password, self.password)

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
        user_activation.activation_hash = sec_handler.sha256(self.username + self.salt + str(user_activation.activation_until))
        user_activation.save()



class UserActivation(models.Model):
    user = models.ForeignKey(User, null=False, blank=False, on_delete=models.DO_NOTHING)
    activation_until = models.DateTimeField(null=True)
    activation_hash = models.CharField(max_length=500, null=False, blank=False)

    def __str__(self):
        return self.user.username


class GroupActivity(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE)
    description = models.CharField(max_length=255, blank=True, null=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, null=True)
    metadata = models.CharField(max_length=255, blank=True, null=True)
    created_on = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.description


class PendingRequest(models.Model):
    type = models.CharField(max_length=255) # defines what type of request this is
    group = models.ForeignKey(Group, related_name="pending_publish_requests", on_delete=models.DO_NOTHING)
    organization = models.ForeignKey(Organization, related_name="pending_publish_requests", on_delete=models.DO_NOTHING)
    message = models.TextField(null=True, blank=True)
    activation_until = models.DateTimeField(null=True)
    created_on = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.group.name + " > " + self.organization.organization_name
