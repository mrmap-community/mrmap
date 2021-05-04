from django.apps import AppConfig


class AclConfig(AppConfig):
    name = 'acl'

    def ready(self):  # method just to import the signals
        import acl.signals.acl_handling  # noqa
        import acl.signals.organization_handling  # noqa
        import acl.signals.ownable_models_handling  # noqa

