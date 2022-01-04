from django.db.models.query import Prefetch
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


class HistoryInformationViewSetMixin:

    def get_prefetch_related(self, include):
        prefetch_related = super().get_prefetch_related(include)
        if include == "__all__" and not prefetch_related:
            # TODO: better would be to extend the prefetch_related array
            return [
                Prefetch('change_logs', queryset=self.queryset.model.objects.filter_first_history(
                ), to_attr='first_history'),
                Prefetch('change_logs', queryset=self.queryset.model.objects.filter_last_history(
                ), to_attr='last_history')
            ]
