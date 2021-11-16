from django.core.management import BaseCommand
from django.db import transaction
from acls.models.acls import AccessControlList
from acls.utils import collect_default_permissions


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
        admin_permissions, member_permissions = collect_default_permissions()

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
