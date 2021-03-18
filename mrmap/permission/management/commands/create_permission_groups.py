from django.contrib.auth.models import Permission
from django.core.management import BaseCommand
from django.db import transaction
from django.db.models import Q
from permission.models import TemplateRole
from permission.settings import DEFAULT_ROLES


class Command(BaseCommand):
    help = "Creates default `Role` objects based on the `DEFAULT_ROLES` settings from settings.py"

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        with transaction.atomic():
            for setting in DEFAULT_ROLES:
                self._create_role_from_default_setting(setting=setting)

    @staticmethod
    def _create_role_from_default_setting(setting: dict):
        """ Creates default `Role` objects

        Args:
            setting (dict): The DEFAULT_ROLES setting
        Returns:
             role (Role): The created group object
        """
        query = None
        for permission in setting["permissions"]:
            perm = permission.value
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
                                                           description=setting["description"])
        if created:
            role.permissions.add(*Permission.objects.filter(query))
        else:
            role.permissions.clear()
            role.permissions.add(*Permission.objects.filter(query))
        return role
