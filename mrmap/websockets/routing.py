from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/pending-tasks-table/$', consumers.PendingTaskTableConsumer.as_asgi()),
    re_path(r'ws/pending-tasks-count/$', consumers.PendingTaskCountConsumer.as_asgi()),
]
