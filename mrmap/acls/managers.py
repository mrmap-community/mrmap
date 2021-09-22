from django.contrib.gis.db import models


class AppendToAclManager(models.Manager):
    """
    handles the creation of objects which shall be secured.
    """

    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False, add_to_acl=True):
        """ overrides the default bulk_create handling cause bulk_create will not call save() and pre_save/post_save
            signal also not. see docs: https://docs.djangoproject.com/en/3.2/ref/models/querysets/#bulk-create

            Since we implement acls app which implements signals to handle appending of created objects to the acls AND
            we need to use bulk_create to speed up the persisting process in service parser, we need to implement the
            behaviour of auto adding to acls here.
        """
        from acls.models.acls import AccessControlList  # to prevent from circular import
        _objs = super().bulk_create(objs=objs, batch_size=batch_size, ignore_conflicts=ignore_conflicts)
        if add_to_acl:
            AccessControlList.objects.append_objects_to_acls(_objs)
        return _objs


class AclManager(models.Manager):
    """Custom manager class to handle default behaviours like appending object to acls"""
    def append_object_to_acls(self, obj):
        """append the given object to all default acls where the owner is the same

            Args:
                obj: the given object instance which shall be secured by an acls.
        """
        default_acls = super().get_queryset().filter(default_acl=True, owned_by_org=obj.owned_by_org)
        for acl in default_acls:
            field = acl.get_accessible_field_by_related_model(obj._meta.model)
            add_func = acl.get_add_function_by_field(field)
            add_func(obj)

    def append_objects_to_acls(self, objects: list):
        """Same as `append_object_to_acls`, but with more efficient bulk_add usage.

            Args:
                objects: the given objects instances which shall be secured by an acls.
        """
        owners = []
        model_list = []
        for obj in objects:
            if not owners or owners[0] != obj.owned_by_org_id:
                owners.append(obj.owned_by_org_id)
            if not model_list or model_list[0] != obj._meta.model:
                model_list.append(obj._meta.model)

        if len(owners) > 1:
            # todo: we could handle this in future
            raise Exception('Multiple owners are not supported. Split the objects list by different owners.')
        if len(model_list) > 1:
            # todo: we could handle this in future
            raise Exception('Multiple models are not supported. Splite the objects list by different models.')

        default_acls = super().get_queryset().filter(default_acl=True, owned_by_org_id=owners[0])
        for acl in default_acls:
            field = acl.get_accessible_field_by_related_model(model_list[0])
            add_func = acl.get_add_function_by_field(field)
            add_func(*objects)
