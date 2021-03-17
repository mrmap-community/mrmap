from django.apps import AppConfig


class PermissionConfig(AppConfig):
    name = 'permission'

    def ready(self):  # method just to import the signals
        import permission.signals  # noqa
