from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/jobs-table/$', consumers.JobTableConsumer.as_asgi()),
    re_path(r'ws/tasks-table/$', consumers.TaskTableConsumer.as_asgi()),
]
