from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import gettext_lazy as _
from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
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


class CanRetryRegistrationReference(BasePermission):
    """Write access to a registration work row needs the permission of its process' resource.

    A registration reference is the retained work item of one background
    process, so the question of its retry is decided exactly like the abort
    of that process: by whoever may change the resource the process reports
    on (#1265). This class composes the two existing answers instead of
    inventing a third one:

    * reading stays as it was - the endpoint answered its work rows to
      everybody already, and the retry feature changes nothing about that;
    * ``PATCH`` - the one write the retry of #1265 is - is decided by
      :class:`CanChangeRelatedResource`, asked of the process the row
      belongs to. A harvesting row answers False: that flow reschedules
      through its own run, never through this endpoint's retry;
    * every other write (``POST``, ``PUT``, ``DELETE``) stays decided by the
      class the endpoint used before: the work row is the permit store of
      the queue, a client must not add rows to it or take them away.
    """

    message = _("You are not allowed to retry the references of this process.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # the answers this class composes: unchanged for every method but PATCH
        self._reads_and_other_writes = DjangoObjectPermissionsOrAnonReadOnly()
        self._process_decision = CanChangeRelatedResource()

    def has_permission(self, request, view):
        if request.method == "PATCH":
            return self._process_decision.has_permission(request, view)
        return self._reads_and_other_writes.has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        if request.method == "PATCH":
            if request.user.is_superuser:
                # like every other write of the api, the deployment's admin
                # is not decided by one resource's permission
                return True
            process = getattr(obj, "background_process", None)
            if process is None:
                # a harvesting row (or a legacy ownerless one): its retry is
                # not this endpoint's contract, whatever resource a process
                # might have named
                return False
            return self._process_decision.has_object_permission(
                request, view, process)
        return self._reads_and_other_writes.has_object_permission(
            request, view, obj)
