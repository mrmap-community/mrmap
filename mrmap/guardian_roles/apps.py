from django.apps import AppConfig


class PermissionConfig(AppConfig):
    name = 'guardian_roles'

    def ready(self):  # method just to import the signals
        import guardian_roles.signals.acl  # noqa
        import guardian_roles.signals.object_perms  # noqa
