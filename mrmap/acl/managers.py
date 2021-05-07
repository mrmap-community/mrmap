from django.contrib.gis.db import models


class AppendToAclManager(models.Manager):
    """
    handles the creation of objects which shall be secured.
    """

    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False, add_to_acl=True):
        """ overrides the default bulk_create handling cause bulk_create will not call save() and pre_save/post_save
            signal also not. see docs: https://docs.djangoproject.com/en/3.2/ref/models/querysets/#bulk-create

            Since we implement acl app which implements signals to handle appending of created objects to the acl AND
            we need to use bulk_create to speed up the persisting process in service parser, we need to implement the
            behaviour of auto adding to acl here.
        """
        from acl.models.acl import AccessControlList  # to prevent from circular import
        _objs = super().bulk_create(objs=objs, batch_size=batch_size, ignore_conflicts=ignore_conflicts)
        if add_to_acl:
            for obj in _objs:
                AccessControlList.objects.append_object_to_acls(obj)
        return _objs


class AclManager(models.Manager):
    """Custom manager class to handle default behaviours like appending object to acl"""
    def append_object_to_acls(self, obj):
        """append the given object to all default acl where the owner is the same

            Args:
                obj: the given object instance which shall be secured by an acl.
        """
        default_acls = super().get_queryset().filter(default_acl=True, owned_by_org=obj.owned_by_org)
        for acl in default_acls:
            field = acl.get_accessible_field_by_related_model(obj._meta.model)
            add_func = acl.get_add_function_by_field(field)
            add_func(obj)
