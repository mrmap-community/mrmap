from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/pending-tasks/$', consumers.PendingTaskConsumer.as_asgi()),
]
