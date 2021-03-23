from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ImproperlyConfigured
from django.db.models.signals import post_save, post_delete
from guardian.shortcuts import assign_perm

from guardian_roles.conf import settings as guardina_roles_settings
from guardian_roles.models.core import TemplateRole, ObjectBasedTemplateRole, OwnerBasedTemplateRole
from guardian_roles.utils import get_model_from_string


def _generate_object_based_template_roles(instance):
    """generate one `ObjectBasedTemplateRole` per `TemplateRole` for given instance

    Args:
        instance: the instance for that the `ObjectBasedTemplateRole` instances shall be generated.

    Returns:
        object_based_template_roles (list): a list of all generated `ObjectBasedTemplateRole` objects
    """
    content_type = ContentType.objects.get_for_model(instance)
    object_based_template_roles = []
    for role in TemplateRole.objects.filter(permissions__content_type=content_type):
        object_based_template_roles.append(ObjectBasedTemplateRole.objects.get_or_create(object_pk=instance.pk,
                                           content_type=content_type,
                                           based_template=role)[0])
    return object_based_template_roles


def assign_perm_to_object(sender, instance, created, **kwargs):
    """assign guardian user and group permissions on created instance

    Args:
        sender: the model from the guardina_roles_settings.OWNABLE_MODELS list
        instance: the instance of the given sender model
        created: boolean flag which is True if the instance is new

    Returns:
        None
    """
    if created:
        content_type = ContentType.objects.get_for_model(instance)
        for obj in _generate_object_based_template_roles(instance):
            users = get_user_model().objects.filter(role__based_template=obj.based_template)
            obj.user_set.add(*users)
            for perm in obj.based_template.permissions.filter(content_type=content_type):
                assign_perm(perm=perm, user_or_group=obj, obj=instance)


def handle_owner_change(sender, instance, created, update_fields, **kwargs):
    """handle owner changes for the given instance

    Args:
        sender: the model class of the given instance
        instance: the instance of the given sender model
        created: boolean flag which is True if the instance is new
        update_fields: The set of fields to update as passed to Model.save(), or None if update_fields wasn’t passed
                        to save().
    Returns:
        None

    """
    if not created:
        if not hasattr(instance, guardina_roles_settings.OWNER_FIELD_ATTRIBUTE):
            raise ImproperlyConfigured(f'You need to configure the {guardina_roles_settings.OWNER_FIELD_ATTRIBUTE} field on the given '
                                       f'model: {instance._meta.model}')
        if not hasattr(instance, guardina_roles_settings.OLD_OWNER_FIELD_ATTRIBUTE):
            raise ImproperlyConfigured(f'You need to configure the {guardina_roles_settings.OLD_OWNER_FIELD_ATTRIBUTE} on the given '
                                       f'model: {instance._meta.model}')
        owner = getattr(instance, guardina_roles_settings.OWNER_FIELD_ATTRIBUTE)
        old_owner = getattr(instance, guardina_roles_settings.OLD_OWNER_FIELD_ATTRIBUTE)
        if old_owner and owner != old_owner:
            print(update_fields)
            print(owner)
            print(old_owner)
            # owner becomes changed, move users from old owner based templates to the new
            owner_based_roles = OwnerBasedTemplateRole.objects.filter(content_object=owner)
            for owner_based_role in owner_based_roles:
                old_owner_based_role = OwnerBasedTemplateRole.objects.get(content_object=old_owner,
                                                                          based_template=owner_based_role.based_template)
                owner_based_role.users.add(*old_owner_based_role.users)


def handle_instance_delete(sender, instance, **kwargs):
    # delete all `ObjectBasedTemplateRole` objects. This is needed cause the `GenericForeignKey` does not support
    # on_delete=models.CASCADE method.
    ObjectBasedTemplateRole.objects.filter(object_pk=instance.pk).delete()


for model in guardina_roles_settings.OWNABLE_MODELS:
    model_class = get_model_from_string(model)
    post_save.connect(receiver=assign_perm_to_object,
                      sender=model_class,
                      dispatch_uid=f"assign_perm_to_object_for_{model}")
    post_save.connect(receiver=handle_owner_change,
                      sender=model_class,
                      dispatch_uid=f"handle_owner_change_for_{model}")
    post_delete.connect(receiver=handle_instance_delete,
                        sender=model_class,
                        dispatch_uid=f"handle_instance_delete_for_{model}")
