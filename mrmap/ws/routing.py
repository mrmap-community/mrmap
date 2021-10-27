from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/object-counts/$', consumers.ObjectCountsConsumer.as_asgi()),
    re_path(r'ws/toasts/$', consumers.ToastConsumer.as_asgi()),
]
