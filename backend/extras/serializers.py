from django.conf import settings
from guardian.core import ObjectPermissionChecker


class ObjectPermissionCheckerSerializerMixin:
    def get_perm_checker(self):
        perm_checker = self.context.get('perm_checker', None)
        if not perm_checker and 'request' in self.context:
            # fallback with slow solution if no perm_checker is in the context
            perm_checker = ObjectPermissionChecker(
                user_or_group=self.context['request']['user'])
            settings.ROOT_LOGGER.warning(
                "slow handling of object permissions detected. Optimize your view by adding a permchecker in your view.")
        return perm_checker
