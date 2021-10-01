from asgiref.sync import async_to_sync


def update_count(channel_layer, instance):
    if instance.owned_by_org:
        async_to_sync(channel_layer.group_send)(
            f"appviewmodelconsumer_{instance.owned_by_org.pk}_observers",
            {
                "type": "update.app.view.model",
            },
        )
