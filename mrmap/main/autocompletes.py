from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from guardian.shortcuts import get_objects_for_user


class CreateObjectMixin:
    add_perm = None

    def has_add_permission(self, request: HttpRequest):
        """ Checks whether the user is allowed to add new keywords

        Args:
            request (HttpRequest): THe incoming request
        Returns:
            True|False
        """
        if not self.add_perm:
            raise ImproperlyConfigured(_('If you provide add functionality you need to define `add_perm` param'))
        user = request.user
        return user.has_perm(perm=self.add_perm)


class SecuredAutocompleteMixin:
    def get_queryset(self):
        qs = super().get_queryset()
        qs = get_objects_for_user(user=self.request.user, perms=f'view_{self.model.__name__.lower()}', klass=qs)
        return qs
