
# send messages via websocket

root@mrmap-backend:/opt/mrmap# python3 manage.py shell_plus

>>> from channels.layers import get_channel_layer
>>> from asgiref.sync import async_to_sync
>>> async_to_sync(get_channel_layer().group_send)("default", {"type": "send.msg", "json": {"hello": "world"}})