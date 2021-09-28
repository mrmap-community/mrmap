from asgiref.sync import async_to_sync
from celery import states
from channels.layers import get_channel_layer
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils.html import format_html
from django.utils.translation import gettext as _
from jobs.models import Job, Task
from django.contrib.contenttypes.models import ContentType


def update_count(channel_layer, instance):
    if instance.owned_by_org:
        async_to_sync(channel_layer.group_send)(
            f"appviewmodelconsumer_{instance.owned_by_org.pk}_observers",
            {
                "type": "update.app.view.model",
            },
        )
