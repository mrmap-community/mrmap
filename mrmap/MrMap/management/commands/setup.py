"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 06.05.19

"""
from getpass import getpass

from dateutil.parser import parse
from django.contrib.auth import get_user_model
from django.core.management import BaseCommand, call_command
from django.db import transaction
from django.utils import timezone

from monitoring.settings import MONITORING_REQUEST_TIMEOUT, MONITORING_TIME
from service.helper.enums import OGCOperationEnum
from service.models import OGCOperation
from structure.models import Organization
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

        if get_user_model().objects.filter(username=name).exists():
            self.stdout.write(self.style.NOTICE("User with that name already exists! Please choose another one!"))
            exit()

        # check password
        password = getpass("Enter a password: ")
        password_conf = getpass("Enter the password again: ")
        while password != password_conf:
            self.stdout.write(self.style.ERROR("Passwords didn't match! Try again!"))
            password = getpass("Enter the password: ")
            password_conf = getpass("Enter the password again: ")

        superuser = get_user_model().objects.create_superuser(
            name,
            "",
            password
        )
        superuser.confirmed_dsgvo = timezone.now()
        superuser.is_active = True
        superuser.save()
        msg = "Superuser '" + name + "' was created successfully!"
        self.stdout.write(self.style.SUCCESS(str(msg)))

        # handle root organization
        orga = self._create_default_organization()
        superuser.organization = orga
        superuser.save()
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
    def _create_default_organization():
        """ Create default organization for superuser

        Returns:
            orga (Organization): The default organization
        """
        orga = Organization.objects.get_or_create(organization_name="Testorganization")[0]

        return orga

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
