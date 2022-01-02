from guardian.core import ObjectPermissionChecker


class ObjectPermissionCheckerViewSetMixin:
    """add a ObjectPermissionChecker based on the accessing user to the serializer context."""

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.request:
            perm_checker = ObjectPermissionChecker(
                user_or_group=self.request.user)
            perm_checker.prefetch_perms(
                self.get_queryset().prefetch_related(None))
            context.update({'perm_checker': perm_checker})
        return context
