from django.db.models.signals import post_save
from django.dispatch import receiver
from guardian.shortcuts import assign_perm
from service.models import Metadata


@receiver(post_save, sender=Metadata)
def assign_perm_to_object(sender, instance, created, **kwargs):
    """assign guardian user and group permissions on created instance"""
    if created:
        assign_perm("change_metadata", instance.created_by, instance)
        assign_perm("view_metadata", instance.created_by, instance)
        assign_perm("delete_metadata", instance.created_by, instance)
