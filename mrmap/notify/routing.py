from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path('ws/default/', consumers.DefaultConsumer.as_asgi()),
]
