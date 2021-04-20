"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 14.04.20

"""
from rest_framework.permissions import BasePermission

from structure.permissionEnums import PermissionEnum

class DefaultPermission(BasePermission):
    """
    Allows access only to users with this permission.

    Since we use ViewSets, we can only set permission classes for the whole ViewSet class and not single methods.
    So we check whether the requested view action equals the one, we have to permission-check and perform our check,
    or otherwise we skip, since here is no permission-check needed.

    """

    view_action = 'create'
    needed_perm = '' # PermissionEnum.CAN_REGISTER_RESOURCE

    def has_permission(self, request, view):
        if view.action == self.view_action:
            user = request.user
            needed_perm = self.needed_perm
            has_perm = user.has_perm(perm=needed_perm)
            return has_perm
        else:
            return True

class CanRegisterService(DefaultPermission):
    """
    Allows access only to users with this permission.

    Since we use ViewSets, we can only set permission classes for the whole ViewSet class and not single methods.
    So we check whether the requested view action equals the one, we have to permission-check and perform our check,
    or otherwise we skip, since here is no permission-check needed.

    """

    view_action = 'create'
    needed_perm = PermissionEnum.CAN_REGISTER_RESOURCE


class CanRemoveService(DefaultPermission):
    """
    Allows access only to users with this permission.

    Since we use ViewSets, we can only set permission classes for the whole ViewSet class and not single methods.
    So we check whether the requested view action equals the one, we have to permission-check and perform our check,
    or otherwise we skip, since here is no permission-check needed.

    """

    view_action = 'destroy'
    needed_perm = PermissionEnum.CAN_REMOVE_RESOURCE


class CanActivateService(DefaultPermission):
    """
    Allows access only to users with this permission.

    Since we use ViewSets, we can only set permission classes for the whole ViewSet class and not single methods.
    So we check whether the requested view action equals the one, we have to permission-check and perform our check,
    or otherwise we skip, since here is no permission-check needed.

    """
    view_action = 'active_state'
    needed_perm = PermissionEnum.CAN_ACTIVATE_RESOURCE

