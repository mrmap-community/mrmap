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
from django.db import transaction, connections, DEFAULT_DB_ALIAS, OperationalError
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from acl.models.acl import AccessControlList
from acl.settings import DEFAULT_ORGANIZATION_ADMIN_PERMISSIONS
from acl.utils import collect_default_permissions, construct_permission_query
from monitoring.settings import MONITORING_REQUEST_TIMEOUT, MONITORING_TIME
from service.helper.enums import OGCOperationEnum
from service.models import OGCOperation
from structure.models import Organization
from monitoring.models import MonitoringSetting


class Command(BaseCommand):
    help = "Resynchronizes all default permissions for all default acls."

    def add_arguments(self, parser):
        parser.add_argument('--acls', dest='acls', help="Define a list of acls which shall be resynchronized.")
        parser.add_argument('--acls-exclude', dest='acls-exclude', help="Define a list of acls which shall be not resynchronized.")

    def handle(self, *args, **options):
        if options['acls']:
            pass
            # todo
        elif options['acls-exclude']:
            pass
            # todo
        with transaction.atomic():
            self._resync()

    def _resync(self, acls=None):
        admin_perms, member_perms = collect_default_permissions()

        admin_permissions = construct_permission_query(admin_perms)
        member_permissions = construct_permission_query(member_perms)

        for acl in AccessControlList.objects.filter(default_acl=True,
                                                    description__icontains='administrators'):
            acl.permissions.remove(*acl.permissions.all())
            acl.permissions.add(*admin_permissions)
        self.stdout.write(self.style.SUCCESS(f"Permissions added: {admin_permissions}"))
        for acl in AccessControlList.objects.filter(default_acl=True,
                                                    description__icontains='members'):
            acl.permissions.remove(*acl.permissions.all())
            acl.permissions.add(*member_permissions)
        self.stdout.write(self.style.SUCCESS(f"Permissions added: {member_permissions}"))
        self.stdout.write(self.style.SUCCESS("Done"))

