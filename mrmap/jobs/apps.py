from django.apps import AppConfig


class JobConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'jobs'

    def ready(self):  # method just to import the signals
        import jobs.signals # noqa
