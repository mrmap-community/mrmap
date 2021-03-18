"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 06.05.19

"""
from getpass import getpass

from dateutil.parser import parse
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management import BaseCommand, call_command
from django.db import transaction
from django.utils import timezone

from MrMap.management.commands.setup_settings import DEFAULT_GROUPS
from monitoring.settings import MONITORING_REQUEST_TIMEOUT, MONITORING_TIME
from service.helper.enums import OGCOperationEnum
from service.models import OGCOperation
from structure.models import MrMapGroup, Organization, MrMapUser
from structure.permissionEnums import PermissionEnum
from structure.settings import PUBLIC_GROUP_NAME, SUPERUSER_GROUP_NAME, \
    SUPERUSER_GROUP_DESCRIPTION, PUBLIC_GROUP_DESCRIPTION
from monitoring.models import MonitoringSetting


class Command(BaseCommand):
    help = "Runs an initial setup for creating the superuser on a fresh installation."

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        with transaction.atomic():
            # sec run the main setup
            self._run_superuser_default_setup()
            # then load the default categories
            call_command('load_categories')
            call_command('load_licences')

    def _run_superuser_default_setup(self):
        """ Encapsules the main setup for creating all default objects and the superuser

        Returns:
             nothing
        """
        # Check if superuser already exists
        name = input("Enter a username: ")

        if MrMapUser.objects.filter(username=name).exists():
            self.stdout.write(self.style.NOTICE("User with that name already exists! Please choose another one!"))
            exit()

        # check password
        password = getpass("Enter a password: ")
        password_conf = getpass("Enter the password again: ")
        while password != password_conf:
            self.stdout.write(self.style.ERROR("Passwords didn't match! Try again!"))
            password = getpass("Enter the password: ")
            password_conf = getpass("Enter the password again: ")

        superuser = MrMapUser.objects.create_superuser(
            name,
            "",
            password
        )
        superuser.confirmed_dsgvo = timezone.now()
        superuser.is_active = True
        superuser.save()
        msg = "Superuser '" + name + "' was created successfully!"
        self.stdout.write(self.style.SUCCESS(str(msg)))

        # handle public group
        group = self._create_public_group(superuser)
        # group.created_by = superuser
        group.user_set.add(superuser)
        group.save()

        # handle root group
        group = self._create_superuser_group(superuser)
        # group.created_by = superuser
        group.user_set.add(superuser)
        group.save()

        # handle default groups
        for setting in DEFAULT_GROUPS:
            try:
                if self._create_group_from_default_setting(setting, superuser)[1] is True:
                    group = self._create_group_from_default_setting(setting, superuser)[0]
                    msg = "Group '{}' created!".format(group.name)
                    self.stdout.write(self.style.SUCCESS(msg))
                else:
                    group = self._create_group_from_default_setting(setting, superuser)[0]
                    msg = "Group '{}' was already in Database!".format(group.name)
                    self.stdout.write(self.style.SUCCESS(msg))
            except AttributeError as e:
                msg = "Group creation error for '{}':{}".format(setting["name"], e)
                self.stdout.write(self.style.ERROR(msg))

        # handle root organization
        orga = self._create_default_organization()
        default_group = self._create_default_group(orga, superuser)
        superuser.organization = orga
        superuser.save()
        msg = "Superuser '" + name + "' added to group '" + str(group.name) + "'!"
        self.stdout.write(self.style.SUCCESS(str(msg)))
        msg = "Superuser '" + name + "' added to organization '" + str(orga.organization_name) + "'!"
        self.stdout.write(self.style.SUCCESS(msg))

        self._create_default_monitoring_setting()
        msg = (
            f"Default monitoring setting with check on {MONITORING_TIME} and "
            f"timeout {MONITORING_REQUEST_TIMEOUT} was created successfully"
        )
        self.stdout.write(self.style.SUCCESS(str(msg)))

        self._create_ogc_operations()
        msg = "OgcOperations created"
        self.stdout.write((self.style.SUCCESS(msg)))

    @staticmethod
    def _create_group_from_default_setting(setting: dict, user: MrMapUser):
        """ Creates default groups besides of Superuser group and Public group

        Args:
            setting (dict): The DEFAULT_GROUP setting
        Returns:
             group (MrMapGroup): The created group object
        """
        group_name = setting["name"]
        group_desc = setting["description"]
        group_permissions = setting["permissions"]
        parent_group = MrMapGroup.objects.filter(
            name=setting["parent_group"]
        ).first()

        try:
            group = MrMapGroup.objects.get(
                name=group_name,
                parent_group=parent_group,
                is_permission_group=True,
            )
            created = False
        except MrMapGroup.DoesNotExist:
            group = MrMapGroup.objects.create(
                name=group_name,
                parent_group=parent_group,
                created_by=user,
                is_permission_group=True,
            )
            created = True
        finally:
            for perm in group_permissions:
                perm = perm.value.split(".")[-1]
                print(perm)
                p = Permission.objects.get(codename=perm)
                group.permissions.add(p)

        group.description = group_desc
        group.save()
        return group, created

    @staticmethod
    def _create_public_group(user: MrMapUser):
        """ Creates public group

        Args:
            user (MrMapUser): The superuser object
        Returns:
             group (Group): The newly created group
        """
        try:
            group = MrMapGroup.objects.get(
                name=PUBLIC_GROUP_NAME,
                description=PUBLIC_GROUP_DESCRIPTION,
                is_public_group=True,
                is_permission_group=True,
            )
        except MrMapGroup.DoesNotExist:
            group = MrMapGroup(
                name=PUBLIC_GROUP_NAME,
                description=PUBLIC_GROUP_DESCRIPTION,
                created_by=user,
                is_public_group=True,
                is_permission_group=True,
            )
            group.save()

        return group

    @staticmethod
    def _create_superuser_group(user: MrMapUser):
        """ Creates default group, default role for group and default superuser permission for role

        Args:
            user (MrMapUser): The superuser object
        Returns:
             group (Group): The newly created group
        """
        group, created = MrMapGroup.objects.get_or_create(
            name=SUPERUSER_GROUP_NAME,
            description=SUPERUSER_GROUP_DESCRIPTION,
            is_permission_group=True,
            created_by=user,
        )
        group.permissions.add(*Permission.objects.all())
        return group

    @staticmethod
    def _create_default_organization():
        """ Create default organization for superuser

        Returns:
            orga (Organization): The default organization
        """
        orga = Organization.objects.get_or_create(organization_name="Testorganization")[0]

        return orga

    @staticmethod
    def _create_default_group(org: Organization, user: MrMapUser):

        try:
            group = MrMapGroup.objects.get(
                name="Testgroup",
                organization=org,
            )
        except MrMapGroup.DoesNotExist:
            group = MrMapGroup(
                name="Testgroup",
                organization=org,
                created_by=user,
            )
            group.save()

        group.user_set.add(user)
        return group

    @staticmethod
    def _create_default_monitoring_setting():
        """ Create default settings for monitoring

        Returns:
            nothing
        """
        mon_time = parse(MONITORING_TIME)
        monitoring_setting = MonitoringSetting.objects.get_or_create(
            check_time=mon_time, timeout=MONITORING_REQUEST_TIMEOUT
        )[0]
        monitoring_setting.save()

    @staticmethod
    def _create_ogc_operations():
        """ Create all possible OGCOperations in model ``OGCOperation´´

        Returns:
            nothing
        """
        for key, value in OGCOperationEnum.as_choices(drop_empty_choice=True):
            OGCOperation(operation=value).save()
