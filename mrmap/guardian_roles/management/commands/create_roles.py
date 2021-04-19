from enum import Enum

from django.conf import settings
from django.contrib.auth.models import Permission
from django.core.management import BaseCommand
from django.db import transaction
from django.db.models import Q
from guardian_roles.models.core import TemplateRole


class Command(BaseCommand):
    help = "Creates default `TemplateRole` objects based on the `DEFAULT_ROLES` settings from settings.py"

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        with transaction.atomic():
            for setting in getattr(settings, 'GUARDIAN_ROLES_DEFAULT_ROLES', []):
                self._create_role_from_default_setting(setting=setting)

    def _create_role_from_default_setting(self, setting: dict):
        """ Creates default `Role` objects

        Args:
            setting (dict): The DEFAULT_ROLES setting
        Returns:
             role (Role): The created group object
        """
        query = None

        for permission in setting["permissions"]:
            if isinstance(permission, Enum):
                perm = permission.value
            else:
                perm = permission
            try:
                app_label, codename = perm.split('.', 1)
            except ValueError:
                raise ValueError("For global permissions, first argument must be in"
                                 " format: 'app_label.codename' (is %r)" % permission)
            _query = Q(content_type__app_label=app_label, codename=codename)

            if query:
                query |= _query
            else:
                query = _query

        role, created = TemplateRole.objects.get_or_create(name=setting["name"],
                                                           verbose_name=setting["verbose_name"],
                                                           description=setting["description"],)

        if created:
            role.permissions.add(*Permission.objects.filter(query))
            self.stdout.write(self.style.SUCCESS(f"Template role '{role.name}' created."))
        else:
            if role.permissions.all():
                role.permissions.remove(*role.permissions.all())
            role.permissions.add(*Permission.objects.filter(query))
            self.stdout.write(self.style.SUCCESS(f"Permission list updated for template role '{role.name}'."))
        return role
