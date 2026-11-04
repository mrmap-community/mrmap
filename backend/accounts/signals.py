"""The permission bootstrap: which creation grants what to whom.

Both receivers of this module connect themselves to ``post_save`` and both
return early when ``raw`` is true. That guard is not an optimisation. A
``loaddata`` does emit ``post_save`` for every row it writes: the deserializer
does not call ``Model.save()``, it calls ``save_base`` with ``raw=True``, and
``save_base`` forwards that to the signal. A receiver therefore sees
``created=True`` **and** ``raw=True`` for a fixture row, and one acting on
``created`` alone creates the groups and the grants of a deployment a second
time for every organization its dump carries - and the second ``loaddata`` of
the same dump then collides on the unique name of ``auth_group`` (#864).

So the rule for every receiver this app connects - #731, #732 and #734 add
more: one which creates or grants anything takes ``raw`` in its signature and
returns before its first write when it is true.
``tests/django/accounts/test_fixture_raw_guards.py`` fails for a connected
receiver of this app which does not take the parameter, so the rule cannot be
forgotten by a receiver written later; an exemption has to be named there, with
the reason it cannot run during a ``loaddata``.

What is exempt and why:

* ``accounts.apps.create_default_user_and_org`` creates a user and an
  organization, but on ``post_migrate``, which no fixture emits,
* ``PublishRequest.save`` grants publishing rights through
  ``Organization.add_publisher``, and a deserializer does not call
  ``Model.save()`` - it calls ``save_base`` - so a loaded publish request
  grants nothing either.
"""
from logging import Logger

from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.db.models.signals import post_save
from django.db.transaction import atomic
from django.dispatch import receiver
from guardian.shortcuts import assign_perm

from accounts.models.groups import Organization
from accounts.utils import get_secured_models

logger: Logger = settings.ROOT_LOGGER


@receiver(post_save, sender=Organization)
def handle_organization_creation(instance, created, raw=False, **kwargs):
    """
    Create the groups which administer a newly created organization.

    Args:
        instance: the created organization
        created: whether the organization was created and not changed
        raw: whether the organization was loaded by a fixture
    """
    # a fixture loads an organization as it is: the groups of an organization of
    # a deployment are part of its dump, running this receiver during loaddata
    # would create them a second time for every organization of the fixture
    if not created or raw:
        return

    with atomic():
        organization = instance  # only for better reading

        # create organization administrator and member group
        orga_admins = Group.objects.create(
            name=f"{organization.name} Administrators")
        assign_perm(perm='registry.view_organization',
                    user_or_group=orga_admins, obj=organization)
        assign_perm(perm='registry.change_organization',
                    user_or_group=orga_admins, obj=organization)

        orga_members = Group.objects.create(
            name=f"{organization.name} Members")
        assign_perm(perm='registry.view_organization',
                    user_or_group=orga_members, obj=organization)
        assign_perm(perm='registry.can_publish_for_organization',
                    user_or_group=orga_members, obj=organization)

        # create groups for any configured secured model
        for secured_model in get_secured_models():
            # FIXME: name max_length is 150 chars. Maybe this could be not enough
            secured_model_admins = Group.objects.create(
                name=f"{organization.name} {secured_model._meta.model_name} Admins")

            assign_perm(perm='registry.view_group',
                        user_or_group=orga_admins,
                        obj=secured_model_admins)
            assign_perm(perm='registry.change_group',
                        user_or_group=orga_admins,
                        obj=secured_model_admins)


def owning_organization(instance):
    """
    The organization a newly created resource shall be granted to.

    Nothing knows that today: no resource model stores an owner, ownership is
    the subject of the role work (#727). Whatever learns it later answers it
    here; an instance which does not know its owner is a normal case and not an
    error.

    Args:
        instance: the newly created resource

    Returns:
        Organization or None: the organization to grant the resource to
    """
    owner = getattr(instance, 'owner', None)
    if isinstance(owner, Organization):
        return owner
    return None


def handle_secured_model_creation(instance, created, raw=False, **kwargs):
    """
    Grant the administering group of the owning organization a new resource.

    A resource which has no known owner is granted to nobody and says so once
    in the log. A receiver which raised here would break the registration it is
    supposed to protect, because an exception of a post_save receiver reaches
    the caller of save().
    """
    # a fixture loads services as they are, there is nothing to grant for them
    if not created or raw:
        return

    model_name = instance._meta.model_name
    organization = owning_organization(instance)
    if organization is None:
        logger.warning(
            f"Can't grant object permissions on the new {model_name} "
            f"{instance.pk}: no owner is known for it.")
        return

    admins_group_name = f'{organization.name} {model_name} Admins'
    instance_admins = Group.objects.filter(name=admins_group_name).first()
    if instance_admins is None:
        logger.warning(
            f"Can't grant object permissions on the new {model_name} "
            f"{instance.pk}: {organization} has no group '{admins_group_name}'.")
        return

    with atomic():
        global_add_perm = Permission.objects.get(
            codename=f'add_{model_name}', content_type__app_label=instance._meta.app_label, content_type__model=model_name)
        instance_admins.permissions.add(global_add_perm)
        assign_perm(perm=f'{instance._meta.app_label}.view_{model_name}',
                    user_or_group=instance_admins,
                    obj=instance)
        assign_perm(perm=f'{instance._meta.app_label}.change_{model_name}',
                    user_or_group=instance_admins,
                    obj=instance)
        assign_perm(perm=f'{instance._meta.app_label}.delete_{model_name}',
                    user_or_group=instance_admins,
                    obj=instance)


for model in get_secured_models():
    post_save.connect(receiver=handle_secured_model_creation,
                      sender=model,
                      dispatch_uid=f"handle_secured_model_creation_for_{model}")
