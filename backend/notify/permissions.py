from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import gettext_lazy as _
from guardian.core import ObjectPermissionChecker
from rest_framework.permissions import SAFE_METHODS, BasePermission


class CanChangeRelatedResource(BasePermission):
    """Write access to a background process needs the permission on its resource.

    A background process is only the report of work which is done on another
    resource, so the user which is allowed to change that resource decides to
    abort the work. Reading is not decided here but by the queryset of the
    viewset, which only answers the processes of the resources a user sees.
    """

    message = _("You are not allowed to change the resource of this process.")

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True

        try:
            resource = obj.service
        except ObjectDoesNotExist:
            # the resource of a process is addressed by its type and id, so it
            # may be gone while the process still reports the work on it
            resource = None
        if resource is None:
            # a process which doesn't name a resource cannot be decided by a
            # resource permission: a registration learns its service while it
            # runs. Only a user which may change processes at all may abort it.
            return request.user.has_perm('notify.change_backgroundprocess')

        perm_checker = ObjectPermissionChecker(user_or_group=request.user)
        return perm_checker.has_perm(
            f'change_{resource._meta.model_name}', resource)
