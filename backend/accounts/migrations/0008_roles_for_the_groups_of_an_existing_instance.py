# The roles of an instance which existed before #732: every organization gets
# the roles a new one gets, and the groups it already has are **reused** rather
# than replaced.
#
# Why reuse and never replace: django-guardian's object permission rows point at
# a ``Group`` by key. A migration which created a fresh group and left the old
# one standing would leave every grant of a running instance hanging on a group
# no role explains - and a migration which deleted the old group would delete
# those grants with it. Decision Q5 of #727 retires the legacy grants only after
# they have been reconciled, which is #741's work; #732 hands it the rows to
# reconcile. So nothing in this file deletes a group, and the reverse of every
# step deletes only the rows this file wrote.
#
# What a deployment looks like before this migration, and what it maps onto:
#
# +---------------------------------+------------------------------------------+
# | the group the bootstrap created | the role it becomes                      |
# +---------------------------------+------------------------------------------+
# | ``<Org> Administrators``        | ``organization_admin``, active           |
# | ``<Org> Members``               | the definition marked default, active    |
# | ``<Org> <model> Admins``        | the definition which may change <model>, |
# |                                 | **inactive**, retired by #741            |
# +---------------------------------+------------------------------------------+
#
# The remaining definitions of ORGANIZATION scope - the ones which never had a
# group of their own, such as ``resource_editor`` and ``harvester`` - get a new
# group, so that an upgraded instance answers the same set of roles as a fresh
# install. Those new role groups hold no grants: what a role means is its
# definition, and applying a definition onto groups is the facade of #734, not a
# decision of this file.
#
# Users who are already in a group which becomes a role get a
# ``RoleMembership`` with ``granted_by = NULL``: the membership is real, the
# decision behind it is recorded nowhere, and the question "why does she hold
# this?" of #741 then answers "migrated, no decision known" instead of nothing.
# The members of a group which is retired are adopted the same way, because
# their effective rights continue until #741 removes the group.
#
# The superuser of the instance is not a member of anything here: it stays the
# audited break-glass of decision Q6 of #727 and is not folded into
# ``platform_admin``, which is only the closest a role may come to it.
#
# Reading the legacy groups by name is the one place in the permission code that
# touches those names, and it reads them as the key of a row to migrate, never
# to decide a right - the names were the only identity a role had. Even there the
# model of a per-model group is not guessed from the name: the candidate names
# are built from the ``ContentType`` rows of the database, so a group is matched
# only against a model which exists. A group whose model was removed from the
# code, and with it from ``django_content_type``, is not picked up here; #741's
# audit accounts for it.
#
# Every step is idempotent, so a run which was interrupted half-way re-runs
# without doubling a role or a membership - "restartable" of decision Q5.

from django.db import migrations

#: the suffix of the administrators group of an organization, as
#: ``accounts/signals.py`` built it until this issue
LEGACY_ADMINISTRATORS = "Administrators"

#: the suffix of the members group of an organization
LEGACY_MEMBERS = "Members"

#: the suffix of the per-model administering group; between the organization
#: name and it stands the Django-lowercased name of the model
LEGACY_MODEL_ADMINS = "Admins"

#: the prefix of the group name of a role without an organization, mirroring
#: ``PLATFORM_GROUP_PREFIX`` of ``accounts/models/roles.py``. A migration may not
#: import the models of an app, so the naming is repeated here; the test of this
#: migration asserts that both spellings agree
PLATFORM_GROUP_PREFIX = "platform"

#: the slug of the definition which administers one organization, as the
#: catalogue of #731 names it
ORGANIZATION_ADMIN_SLUG = "organization_admin"

ORGANIZATION_SCOPE = "ORGANIZATION"
PLATFORM_SCOPE = "PLATFORM"

#: the max_length of ``auth.Group.name``; read as a literal because a migration
#: names the state it runs on instead of importing the live model
GROUP_NAME_LIMIT = 150


def role_group_name(prefix, slug, marker=""):
    """The name of a role group, as ``accounts.models.roles`` names it.

    Args:
        prefix (str): the name of the organization, or the platform prefix
        slug (str): the slug of the role definition
        marker (str): the numbering which keeps a truncated name unique

    Returns:
        str: a name of at most the ``auth_group`` limit of characters
    """
    suffix = f": {slug}{marker}"
    return f"{prefix[:GROUP_NAME_LIMIT - len(suffix)]}{suffix}"


def managed_group(apps, prefix, slug):
    """The group a new role takes over: an unmanaged one, or a new one.

    A group of exactly this name which no role manages yet is reused - that is
    what a reverse of this migration leaves behind, and stealing a name from a
    group which *is* managed by a role is impossible by the filter.

    Args:
        apps: the app registry of this migration
        prefix (str): the name of the organization, or the platform prefix
        slug (str): the slug of the role definition

    Returns:
        the ``Group`` the role should manage
    """
    Group = apps.get_model("auth", "Group")
    name = role_group_name(prefix, slug)
    unmanaged = Group.objects.filter(name=name, role__isnull=True).first()
    if unmanaged is not None:
        return unmanaged
    counter = 1
    while Group.objects.filter(name=name).exists():
        counter += 1
        name = role_group_name(prefix, slug, marker=f" ({counter})")
    return Group.objects.create(name=name)


def definitions_by_scope(apps):
    """The catalogue of this database, split by scope.

    Args:
        apps: the app registry of this migration

    Returns:
        tuple: (the definitions of ORGANIZATION scope ordered by slug, the one
        marked default or None, the definitions of PLATFORM scope by slug)
    """
    RoleDefinition = apps.get_model("accounts", "RoleDefinition")
    organization_definitions = list(
        RoleDefinition.objects.filter(scope=ORGANIZATION_SCOPE).order_by(
            "slug"))
    platform_definitions = list(
        RoleDefinition.objects.filter(scope=PLATFORM_SCOPE).order_by("slug"))
    defaults = [
        definition for definition in organization_definitions
        if definition.is_default]
    # a catalogue an operator marked up twice still answers one default, by slug
    return (organization_definitions,
            defaults[0] if defaults else None,
            platform_definitions)


def definition_which_manages(apps, content_type):
    """The ORGANIZATION-scope definition which may change instances of a model.

    This is "which role took over the per-model ``Admins`` group?" answered from
    the catalogue rather than from a name: the definition whose permission set
    holds ``change_<model>`` of that model.

    Args:
        apps: the app registry of this migration
        content_type: the ``ContentType`` of the model of a legacy group

    Returns:
        the definition, or None when no role manages that model - the group is
        then left untouched for #741's audit instead of attached to a definition
        which does not describe it
    """
    RoleDefinition = apps.get_model("accounts", "RoleDefinition")
    return RoleDefinition.objects.filter(
        scope=ORGANIZATION_SCOPE,
        permissions__codename=f"change_{content_type.model}",
        permissions__content_type=content_type,
    ).order_by("slug").distinct().first()


def role_for_group(apps, definition, group, organization, is_active):
    """The role of one group, created when the group has no role yet.

    Idempotent by the group: the group is what identifies the role here, because
    the pair (definition, organization) may hold several retired rows while
    #741 has not deleted them.

    Args:
        apps: the app registry of this migration
        definition: the ``RoleDefinition`` the role applies
        group: the ``Group`` the role manages, reused as it stands
        organization: the organization, None for a platform role
        is_active (bool): whether the role is live or waiting for #741

    Returns:
        the role of that group
    """
    Role = apps.get_model("accounts", "Role")
    role = Role.objects.filter(group=group).first()
    if role is not None:
        return role
    return Role.objects.create(
        role_definition=definition,
        organization=organization,
        group=group,
        is_active=is_active)


def adopt_memberships(apps, role, group):
    """Write a membership for every user who is already in a role's group.

    Args:
        apps: the app registry of this migration
        role: the role whose group is read
        group: the ``Group`` whose members are adopted
    """
    RoleMembership = apps.get_model("accounts", "RoleMembership")
    User = apps.get_model("accounts", "User")
    for user in User.objects.filter(groups=group).distinct():
        RoleMembership.objects.get_or_create(
            role=role, user=user, defaults={"granted_by": None})


def legacy_model_group_names(organization, content_types):
    """The names the per-model groups of an organization could carry.

    Args:
        organization: the organization whose groups are looked for
        content_types: every ``ContentType`` of the database

    Returns:
        dict: group name -> the content type that name would name
    """
    return {
        f"{organization.name} {content_type.model} {LEGACY_MODEL_ADMINS}":
            content_type
        for content_type in content_types}


def organization_admin_definition(apps):
    """The definition which administers one organization, by machine name.

    A slug, never a group name: the slug is the name the shipped catalogue and
    the later issues refer to a role by, and it does not depend on the name of
    any organization.

    Args:
        apps: the app registry of this migration

    Returns:
        the definition, or None when the operator removed it from the catalogue
    """
    RoleDefinition = apps.get_model("accounts", "RoleDefinition")
    return RoleDefinition.objects.filter(
        slug=ORGANIZATION_ADMIN_SLUG, scope=ORGANIZATION_SCOPE).first()


def map_existing_organizations(apps, schema_editor):
    """Give every organization which exists the roles a new one would get.

    Args:
        apps: the app registry of this migration
        schema_editor: the editor, never asked: this step writes through the
            models of the migration state and needs no connection of its own
    """
    Organization = apps.get_model("accounts", "Organization")
    Group = apps.get_model("auth", "Group")
    Role = apps.get_model("accounts", "Role")
    ContentType = apps.get_model("contenttypes", "ContentType")

    organization_definitions, default_definition, _ = definitions_by_scope(apps)
    admin_definition = organization_admin_definition(apps)
    content_types = list(ContentType.objects.all())
    # an Organization *is* a Group (multi table inheritance), so its own row sits
    # in the very table the legacy groups are looked up in and must never be
    # taken for one of them
    organization_pks = set(Organization.objects.values_list("pk", flat=True))

    for organization in Organization.objects.all():
        # the group which becomes the administrator of the organization
        administrators = Group.objects.filter(
            name=f"{organization.name} {LEGACY_ADMINISTRATORS}",
        ).exclude(pk__in=organization_pks).first()
        if administrators is not None and admin_definition is not None:
            role = role_for_group(
                apps, admin_definition, administrators, organization, True)
            adopt_memberships(apps, role, administrators)

        # the group which becomes the default role of the organization
        members = Group.objects.filter(
            name=f"{organization.name} {LEGACY_MEMBERS}",
        ).exclude(pk__in=organization_pks).first()
        if members is not None and default_definition is not None:
            role = role_for_group(
                apps, default_definition, members, organization, True)
            adopt_memberships(apps, role, members)

        # the per-model groups: retired, not renamed. Their group keeps granting
        # what its guardian rows carry until #741 has reconciled them, and takes
        # no new member in the meantime
        names = legacy_model_group_names(organization, content_types)
        for group in Group.objects.filter(
                name__in=list(names)).exclude(pk__in=organization_pks):
            definition = definition_which_manages(apps, names[group.name])
            if definition is None:
                continue
            role = role_for_group(
                apps, definition, group, organization, False)
            adopt_memberships(apps, role, group)

        # every definition of ORGANIZATION scope ends up with a role; the ones
        # which never had a group of their own get a new, empty one, because the
        # member picker of #736 must not offer fewer roles on an upgraded
        # instance than on a fresh one
        for definition in organization_definitions:
            if Role.objects.filter(
                    role_definition=definition,
                    organization=organization).exists():
                continue
            group = managed_group(apps, organization.name, definition.slug)
            role_for_group(apps, definition, group, organization, True)


def seed_platform_roles(apps, schema_editor):
    """Create the role instances of the definitions which reach all organizations.

    A platform role has no organization: that is the other half of "organization
    is null iff the scope is PLATFORM" of #732. They are created without a
    member - nothing here hands the platform to anybody, the superuser of the
    instance least of all (decision Q6 of #727).

    Args:
        apps: the app registry of this migration
        schema_editor: the editor, never asked
    """
    RoleDefinition = apps.get_model("accounts", "RoleDefinition")
    Role = apps.get_model("accounts", "Role")

    for definition in RoleDefinition.objects.filter(
            scope=PLATFORM_SCOPE).order_by("slug"):
        if Role.objects.filter(
                role_definition=definition,
                organization__isnull=True).exists():
            continue
        Role.objects.create(
            role_definition=definition,
            organization=None,
            group=managed_group(apps, PLATFORM_GROUP_PREFIX, definition.slug))


def remove_roles(apps, schema_editor):
    """Undo the rows this migration wrote; the groups of an instance stay.

    The role rows go, and their memberships with them through the cascade. Every
    group stays with its guardian rows and its members - including the groups
    this migration created itself: one of them may hold a grant written onto it
    after the migration ran, and deleting a group is the deliberate work of #741,
    never the side effect of a rollback.

    Args:
        apps: the app registry of this migration
        schema_editor: the editor, never asked
    """
    Role = apps.get_model("accounts", "Role")
    Role.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_roles_and_their_memberships'),
        ('auth', '0012_alter_user_first_name_max_length'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.RunPython(
            map_existing_organizations,
            remove_roles,
        ),
        migrations.RunPython(
            seed_platform_roles,
            remove_roles,
        ),
    ]
