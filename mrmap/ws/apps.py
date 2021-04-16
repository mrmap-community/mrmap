from django.apps import AppConfig


class WebsocketsConfig(AppConfig):
    name = 'ws'

    def ready(self):  # method just to import the signals
        import ws.signals  # noqa
