from django.contrib.auth.models import Permission
from django.db import IntegrityError
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from guardian.shortcuts import assign_perm, remove_perm
from guardian_roles.models.acl import AccessControlList, ObjectRelation


def catch_unsupported_actions(action):
    if action == 'pre_clear':
        # while the pk_set will be None if clear() is called, we losing track of removed permissions/secured_objects.
        # So we can't allow the clear() function.
        raise IntegrityError('clear() function is not supported. If you like to remove all objects, you have to '
                             'remove them by using the remove() function like '
                             'role.permissions.remove(*role.permissions.all().')

    skip_actions = ['pre_add', 'pre_remove']
    if action in skip_actions:
        # prevent this signal of calling multiple times for different m2m actions
        return True


def perform_permission_change(action, perm, acl):
    for secured_object in acl.secured_objects.all():
        secured_object = secured_object.content_object  # only for better ready
        if action == 'post_add':
            assign_perm(perm=perm,
                        user_or_group=acl,
                        obj=secured_object)
        elif action == 'post_remove':
            remove_perm(perm=perm,
                        user_or_group=acl,
                        obj=secured_object)


def perform_secured_object_change(action, permissions, secured_object, acl):
    for perm in permissions:
        if action == 'post_add':
            assign_perm(perm=perm,
                        user_or_group=acl,
                        obj=secured_object)
        elif action == 'post_remove':
            remove_perm(perm=perm,
                        user_or_group=acl,
                        obj=secured_object)


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
        acls = AccessControlList.objects.filter(pk__in=pk_set).prefetch_related('secured_objects')
        perm = instance  # only for better ready
        for acl in acls:
            perform_permission_change(action, perm, acl)
    else:
        # multiple permissions where changed in one AccessControlList
        acl = instance  # only for better ready
        permissions = Permission.objects.filter(pk__in=pk_set)
        for perm in permissions:
            perform_permission_change(action, perm, acl)


@receiver(m2m_changed, sender=AccessControlList.secured_objects.through)
def handle_secured_objects_changed(sender, instance, action, reverse, model, pk_set, **kwargs):
    """handle the change of permissions on `AccessControlList` instances.

    If a permission is added or removed, all `GroupObjectPermission` that related to all given `AccessControlList`
    instances need to become edited.

    Args:
        sender: the secured_objects field of `AccessControlList` instance
        instance: instance of model `ObjectRelation` (reverse) | `AccessControlList` (! reverse)
        action (str): pre_add | post_add | pre_remove | post_remove | pre_clear | post_clear
        reverse: boolean flag which is True if reverse relation was used
        model: `AccessControlList` (reverse) | `ObjectRelation` (! reverse)
        pk_set: list of `AccessControlList` (reverse) | list of `ObjectRelation` (! reverse)
    Returns:
        None
    """
    if catch_unsupported_actions(action):
        return

    if reverse:
        # one secured_object where changed on multiple AccessControlList
        secured_object = instance.content_object  # only for better ready
        for acl in AccessControlList.objects.filter(pk__in=pk_set).prefetch_related('permissions'):
            perform_secured_object_change(action, acl.permissions.all(), secured_object, acl)

    else:
        # multiple secured_object where changed in one AccessControlList
        acl = instance  # only for better ready
        permissions = acl.permissions.all()
        for secured_object in ObjectRelation.objects.filter(pk__in=pk_set):
            perform_secured_object_change(action, permissions, secured_object, acl)
