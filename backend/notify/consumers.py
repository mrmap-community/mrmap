from notify.auth import NonAnonymousJsonWebsocketConsumer


class DefaultConsumer(NonAnonymousJsonWebsocketConsumer):
    groups = ['default']
