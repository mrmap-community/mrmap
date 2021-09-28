from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from guardian.shortcuts import assign_perm, remove_perm
from acls.models.acls import AccessControlList


def catch_unsupported_actions(action):
    if action == 'pre_clear':
        # while the pk_set will be None if clear() is called, we losing track of removed permissions/accessible_object.
        # So we can't allow the clear() function.
        raise IntegrityError('clear() function is not supported. If you like to remove all objects, you have to '
                             'remove them by using the remove() function like '
                             'role.permissions.remove(*role.permissions.all().')

    skip_actions = ['pre_add', 'pre_remove']
    if action in skip_actions:
        # prevent this signal of calling multiple times for different m2m actions
        return True


def perform_permission_change(action, perm, acl):
    for accessible_field in acl.get_accessible_fields():
        _accessible_field = getattr(acl, accessible_field.name)
        for accessible_object in _accessible_field.all():
            if perm.content_type != ContentType.objects.get_for_model(accessible_object):
                continue
            if action == 'post_add':
                assign_perm(perm=perm,
                            user_or_group=acl,
                            obj=accessible_object)
            elif action == 'post_remove':
                remove_perm(perm=perm,
                            user_or_group=acl,
                            obj=accessible_object)


def perform_accessible_object_change(action, permissions, accessible_object, acl):
    content_type = ContentType.objects.get_for_model(accessible_object)
    for perm in permissions:
        if perm.content_type != content_type:
            continue
        if action == 'post_add':
            assign_perm(perm=perm,
                        user_or_group=acl,
                        obj=accessible_object)
        elif action == 'post_remove':
            remove_perm(perm=perm,
                        user_or_group=acl,
                        obj=accessible_object)


@receiver(m2m_changed, sender=AccessControlList.permissions.through)
def handle_permission_changed(sender, instance, action, reverse, model, pk_set, **kwargs):
    """handle the change of permissions on `AccessControlList` instances.

    If a permission is added or removed, all `GroupObjectPermission` that related to all given `AccessControlList`
    instances need to become edited.

    Args:
        sender: the permissions field of `AccessControlList` instance
        instance: instance of model `Permission` (reverse) | `AccessControlList` (! reverse)
        action (str): pre_add | post_add | pre_remove | post_remove | pre_clear | post_clear
        reverse: boolean flag which is True if reverse relation was used
        model: `AccessControlList` (reverse) | `Permission` (! reverse)
        pk_set: list of `AccessControlList` (reverse) | list of `Permission` (! reverse)
    Returns:
        None
    """
    if catch_unsupported_actions(action):
        return

    if reverse:
        # one permission where changed on multiple AccessControlList
        acls = AccessControlList.objects.filter(pk__in=pk_set).prefetch_related('accessible_objects')
        perm = instance  # only for better ready
        for acl in acls:
            perform_permission_change(action, perm, acl)
    else:
        # multiple permissions where changed in one AccessControlList
        acl = instance  # only for better ready
        permissions = Permission.objects.filter(pk__in=pk_set)
        for perm in permissions:
            perform_permission_change(action, perm, acl)


#@receiver(m2m_changed, sender=AccessControlList.accessible_metadata.through)
def handle_accessible_objects_changed(sender, instance, action, reverse, model, pk_set, **kwargs):
    """handle the change of permissions on `AccessControlList` instances.

    If a permission is added or removed, all `GroupObjectPermission` that related to all given `AccessControlList`
    instances need to become edited.

    Args:
        sender: the accessible_objects field of `AccessControlList` instance
        instance: instance of the changed related model (reverse) | `AccessControlList` (! reverse)
        action (str): pre_add | post_add | pre_remove | post_remove | pre_clear | post_clear
        reverse: boolean flag which is True if reverse relation was used
        model: `AccessControlList` (reverse) | The model of `instance` (! reverse)
        pk_set: list of `AccessControlList` (reverse) | list of pk's of the given `model` (! reverse)
    Returns:
        None
    """
    if catch_unsupported_actions(action):
        return

    if reverse:
        # one accessible_object where changed on multiple AccessControlList
        accessible_object = instance  # only for better ready
        for acl in AccessControlList.objects.filter(pk__in=pk_set).prefetch_related('permissions'):
            perform_accessible_object_change(action, acl.permissions.all(), accessible_object, acl)

    else:
        # multiple accessible_object where changed in one AccessControlList
        acl = instance  # only for better ready
        permissions = acl.permissions.all()
        for accessible_object in model.objects.filter(pk__in=pk_set):
            perform_accessible_object_change(action, permissions, accessible_object, acl)


for field in AccessControlList.get_accessible_fields():
    _field = getattr(AccessControlList, field.name)
    m2m_changed.connect(receiver=handle_accessible_objects_changed,
                        sender=_field.through,
                        dispatch_uid=f"handle_instance_creation_for_{_field}")
