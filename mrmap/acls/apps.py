from django.apps import AppConfig


class AclConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'acls'

    def ready(self):  # method just to import the signals
        import acls.signals.acl_handling  # noqa
        import acls.signals.organization_handling  # noqa
        import acls.signals.ownable_models_handling  # noqa

