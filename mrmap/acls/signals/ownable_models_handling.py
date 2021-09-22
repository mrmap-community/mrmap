from django.db.models.signals import post_save
from acls.models.acls import AccessControlList


def handle_instance_creation(instance, created, **kwargs):
    """append the created instance to the default acls's accessible objects list."""
    if created:
        AccessControlList.objects.append_object_to_acls(instance)


for model in AccessControlList.get_ownable_models():
    post_save.connect(receiver=handle_instance_creation,
                      sender=model,
                      dispatch_uid=f"handle_instance_creation_for_{model}")
