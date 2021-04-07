from django.apps import AppConfig


class WebsocketsConfig(AppConfig):
    name = 'websockets'

    def ready(self):  # method just to import the signals
        import websockets.signals  # noqa
