import django_tables2 as tables
from guardian.core import ObjectPermissionChecker


class SecuredTable(tables.Table):

    def before_render(self, request):
        self.perm_checker = ObjectPermissionChecker(request.user)
        # if we call self.data, all object from the underlying queryset will be selected. But in case of paging, only a
        # subset of the self.data is needed. django tables2 doesn't provide any way to get the cached qs of the current
        # page. So the following code snippet is a workaround to collect the current presented objects of the table
        # to avoid calling the database again.
        objs = []
        for obj in self.page.object_list:
            objs.append(obj.record)
        # for all objects of the current page, we prefetch all permissions for the given user. This optimizes the
        # rendering of the action column, cause we need to check if the user has the permission to perform the given
        # action. If we don't prefetch the permissions, any permission check in the template will perform one db query
        # for each object.
        if objs:
            self.perm_checker.prefetch_perms(objs)
        return super().before_render(request=request)

    def __init__(self, *args, **kwargs):
        self.perm_checker = None
        super().__init__(*args, **kwargs)
        self.template_name = "skeletons/django_tables2_bootstrap4_custom.html"
