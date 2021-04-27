from django.db.models.signals import post_save
from acl.models.acl import AccessControlList


def handle_instance_creation(instance, created, **kwargs):
    """append the created instance to the default acl's accessible objects list."""
    if created:
        default_acls = AccessControlList.objects.filter(default_acl=True, owned_by_org=instance.owned_by_org)
        for acl in default_acls:
            field = acl.get_accessible_field_by_related_model(instance._meta.model)
            add_func = acl.get_add_function_by_field(field)
            add_func(instance)


for model in AccessControlList.get_ownable_models():
    post_save.connect(receiver=handle_instance_creation,
                      sender=model,
                      dispatch_uid=f"handle_instance_creation_for_{model}")
