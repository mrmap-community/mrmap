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
from django.db.models.signals import post_save
from django.db.transaction import atomic
from django.dispatch import receiver
from guardian.shortcuts import assign_perm

from accounts.models.groups import Organization
from accounts.models.roles import (ORGANIZATION_ADMIN_ROLE, Role,
                                   RoleDefinition, RoleScope)
from accounts.utils import get_secured_models

logger: Logger = settings.ROOT_LOGGER


@receiver(post_save, sender=Organization)
def handle_organization_creation(instance, created, raw=False, **kwargs):
    """
    Give a newly created organization the roles which administer it.

    The organization is created without a member, so nothing here grants a
    person anything: the receiver creates one ``Role`` per role definition of
    ORGANIZATION scope - a managed group each - and writes onto two of them the
    object grants over the organization which the bootstrap of #729 wrote onto
    ``<Org> Administrators`` and ``<Org> Members``:

    * the role of the definition marked default, the successor of the members
      group, may view the organization and publish for it,
    * ``organization_admin``, the successor of the administrators group, may
      view and change it.

    Two things the old bootstrap did which this one does not:

    * it created one group per entry of ``SECURED_MODELS`` next to the two
      above, so the group count of an organization grew with the list of
      models. A role is per definition now, so adding a role-managed model
        needs no group and no data migration for the organizations which
        already exist (#727).
    * it granted the administrators group ``view_group`` and ``change_group`` on
      those model groups, because administering them *was* administering the
      membership of a name-coupled group. Administering a role is administering
      a membership, which the ``registry.manage_membership`` permission of the
      ``organization_admin`` definition answers - applied where the facade of
      #734 and the API of #736 decide it, so no grant of a group is written
      here for a mechanism which does not read it yet.

    A receiver of ``post_save`` must not raise: an exception reaches the caller
    of ``save()``, so a missing definition is logged rather than acted on, and
    the organization is created anyway.

    Args:
        instance: the created organization
        created: whether the organization was created and not changed
        raw: whether the organization was loaded by a fixture
    """
    # a fixture loads an organization as it is: the roles of an organization of
    # a deployment are part of its dump, running this receiver during loaddata
    # would create them a second time for every organization of the fixture
    if not created or raw:
        return

    with atomic():
        organization = instance  # only for better reading
        Role.objects.create_for_organization(organization)

        # every permission string names the app its permission's ``Permission``
        # row really belongs to: an ``Organization`` is an ``accounts`` model.
        # Guardian resolves an object grant by the codename and the content type
        # of the object (``guardian/shortcuts.py`` ``_normalize_perm`` strips the
        # app_label), so a wrong label here would stay invisible in the grants
        # and only mislead the next reader (#729)
        default_definition = RoleDefinition.objects.filter(
            scope=RoleScope.ORGANIZATION, is_default=True).first()

        # the roles are looked up by definition slug, never by the name of
        # their group: a rename of the organization changes the name and keeps
        # the role (#727's "renaming an organization changes no permission")
        grants = [(ORGANIZATION_ADMIN_ROLE,
                   ('accounts.view_organization',
                    'accounts.change_organization'))]
        if default_definition is not None:
            grants.append((default_definition.slug,
                           ('accounts.view_organization',
                            'accounts.can_publish_for_organization')))

        for slug, permissions in grants:
            role = Role.objects.for_org(organization).with_definition(
                slug).first()
            if role is None:
                logger.warning(
                    f"Can't grant the organization {organization.pk} its "
                    f"{slug} role: the catalogue holds no definition of that "
                    f"slug.")
                continue
            for permission in permissions:
                assign_perm(perm=permission,
                            user_or_group=role.group,
                            obj=organization)


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
    Grant the roles of the owning organization which manage this model.

    The grant target is the role, not a group named after the model: the roles
    of an organization whose *definition* holds ``change_<model>`` are the ones
    which edit instances of that model, which is what #732 replaces the
    interpolated group name with. Renaming an organization therefore cannot
    detach the grant path of anything created afterwards, and a model added to
    the role-managed list needs no group of its own.

    What the receiver no longer does is add the global ``add_<model>``
    permission to the group it grants: the right to register is part of the role
    definition - ``resource_editor`` holds ``registry.add_webmapservice`` - and
    the permissions of a definition reach the group where the facade of #734
    applies them. Writing them onto a group here as a side effect of one
    creation would be the hidden global grant which decision Q5 of #727 retires.

    A resource which has no known owner is granted to nobody, and an organization
    without a role which manages the model is granted to nobody; both say so once
    in the log. A receiver which raised here would break the registration it is
    supposed to protect, because an exception of a post_save receiver reaches
    the caller of save().

    Args:
        instance: the newly created resource
        created: whether the resource was created and not changed
        raw: whether the resource was loaded by a fixture
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

    # by key and definition, never by a name built from the organization: the
    # lookup which made a rename of an organization detach its roles (#732)
    roles = Role.objects.for_org(organization).managing(instance)
    if not roles.exists():
        logger.warning(
            f"Can't grant object permissions on the new {model_name} "
            f"{instance.pk}: {organization} has no active role whose "
            f"definition may change it.")
        return

    with atomic():
        app_label = instance._meta.app_label
        for role in roles:
            for action in ('view', 'change', 'delete'):
                assign_perm(perm=f'{app_label}.{action}_{model_name}',
                            user_or_group=role.group,
                            obj=instance)


for model in get_secured_models():
    post_save.connect(receiver=handle_secured_model_creation,
                      sender=model,
                      dispatch_uid=f"handle_secured_model_creation_for_{model}")
