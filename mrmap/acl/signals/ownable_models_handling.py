from django.db.models.signals import post_save

from acl.settings import OWNABLE_MODELS
from acl.utils import get_model_from_string
from acl.models.acl import AccessControlList


def handle_instance_delete():
    # todo: remove GenericObjectRelation object too
    pass


def handle_instance_creation(instance, created, **kwargs):
    """append the created instance to the default acl's accessible objects list."""
    if created:
        default_acls = AccessControlList.objects.filter(default_acl=True, owned_by_org=instance.owned_by_org)
        for acl in default_acls:
            acl.add_accessible_object(instance)


for model in OWNABLE_MODELS:
    model_class = get_model_from_string(model)
    post_save.connect(receiver=handle_instance_creation,
                      sender=model_class,
                      dispatch_uid=f"handle_instance_creation_for_{model}")
