"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 14.04.20

"""
from rest_framework.permissions import BasePermission

from structure.permissionEnums import PermissionEnum
from users.helper import user_helper


class CanRegisterService(BasePermission):
    """
    Allows access only to users with this permission.

    Since we use ViewSets, we can only set permission classes for the whole ViewSet class and not single methods.
    So we check whether the requested view action equals the one, we have to permission-check and perform our check,
    or otherwise we skip, since here is no permission-check needed.

    """

    def has_permission(self, request, view):
        if view.action == "create":
            user = user_helper.get_user(request)
            needed_perm = PermissionEnum.CAN_REGISTER_RESOURCE
            has_perm = user.has_perm(perm=needed_perm)
            return has_perm
        else:
            return True


class CanRemoveService(BasePermission):
    """
    Allows access only to users with this permission.

    Since we use ViewSets, we can only set permission classes for the whole ViewSet class and not single methods.
    So we check whether the requested view action equals the one, we have to permission-check and perform our check,
    or otherwise we skip, since here is no permission-check needed.

    """

    def has_permission(self, request, view):
        if view.action == "destroy":
            user = user_helper.get_user(request)
            needed_perm = PermissionEnum.CAN_REMOVE_RESOURCE
            has_perm = user.has_perm(perm=needed_perm)
            return has_perm
        else:
            return True


class CanActivateService(BasePermission):
    """
    Allows access only to users with this permission.

    Since we use ViewSets, we can only set permission classes for the whole ViewSet class and not single methods.
    So we check whether the requested view action equals the one, we have to permission-check and perform our check,
    or otherwise we skip, since here is no permission-check needed.

    """

    def has_permission(self, request, view):
        if view.action == "active_state":
            user = user_helper.get_user(request)
            needed_perm = PermissionEnum.CAN_ACTIVATE_RESOURCE
            has_perm = user.has_perm(perm=needed_perm)
            return has_perm
        else:
            return True
