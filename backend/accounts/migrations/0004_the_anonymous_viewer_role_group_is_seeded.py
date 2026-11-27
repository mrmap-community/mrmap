"""The anonymous viewer role group of #739.

A ``view_<model>`` object grant onto the group of the ``anonymous_viewer``
role is what makes a resource public (decision Q2 of #727: public is an
explicit grant, never a side effect). This migration seeds three things the
grant needs to exist on every migrated database:

* the ``anonymous_viewer`` definition of the shipped catalogue, which
  #731's ``sync_role_definitions`` also knows (the frozen copy below is
  checked against the live catalogue by
  ``tests/django/accounts/test_anonymous_viewer_role.py``, the same way
  ``test_role_definitions.py`` pins 0005);
* the PLATFORM-scope ``Role`` of that definition and its group, named like
  the platform roles seeded by 0008;
* guardian's anonymous user row and its membership in that group. Guardian
  3.x only *reads* the row (``guardian.utils.get_anonymous_user`` raises when
  it is absent), so nothing else in this project ever writes it before the
  first anonymous permission check - which is the ``User.DoesNotExist`` the
  note in ``tests/AGENTS.md`` describes. Writing it here, and guarding it on
  ``post_migrate`` in ``accounts/apps.py``, makes the row exist before any
  request rather than lazily, and a member of the group from the first
  anonymous grant on.

The migration grants nothing over any resource: every newly registered and
every existing resource stays non-public until somebody publishes it (#740).
"""

from django.apps import apps as global_apps
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.management import create_permissions
from django.db import migrations

#: the frozen spec of the definition; keep in step with the live catalogue in
#: ``accounts/management/commands/sync_role_definitions.py``
SLUG = "anonymous_viewer"
LABEL = "Anonymous viewer"
DESCRIPTION = (
    "The visitors without an account. A view grant of a resource onto this "
    "role's group is what makes the resource public (#739); nothing joins "
    "it - the guardian anonymous user is its only member and publishing "
    "stays an explicit act (decision Q2 of #727).")
PERMISSIONS = [
    "registry.view_webmapservice",
    "registry.view_webfeatureservice",
    "registry.view_catalogueservice",
    "registry.view_mapcontext",
]

#: the prefix of the group name of a role without an organization, mirroring
#: ``PLATFORM_GROUP_PREFIX`` of ``accounts/models/roles.py``; a migration may
#: not import the models of an app, so the naming is repeated here and the
#: test of this migration asserts that both spellings agree
PLATFORM_GROUP_PREFIX = "platform"

#: the username guardian maps anonymous requests to, mirroring
#: ``GUARDIAN_ANONYMOUS_USER_NAME`` (guardian's own default). A deployment
#: which renamed it holds an unrelated user of that name only until
#: ``ensure_anonymous_viewer`` of ``accounts/apps.py`` runs the next migrate
ANONYMOUS_USERNAME = "AnonymousUser"

#: the max_length of ``auth.Group.name``, as the literal of migration 0008
GROUP_NAME_LIMIT = 150


def create_permission_rows(apps, schema_editor):
    """Have Django build the ``Permission`` rows the seed reads.

    The same call 0005 makes: on a fresh database the rows do not exist
    before ``post_migrate``, and on an upgraded one this is a no-op over
    what is already there.
    """
    using = schema_editor.connection.alias
    create_permissions(
        global_apps.get_app_config("registry"),
        using=using,
        apps=global_apps,
        verbosity=0)


def seed_anonymous_viewer(apps, schema_editor):
    create_permission_rows(apps, schema_editor)

    RoleDefinition = apps.get_model("accounts", "RoleDefinition")
    Permission = apps.get_model("auth", "Permission")
    Role = apps.get_model("accounts", "Role")
    Group = apps.get_model("auth", "Group")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))

    definition, _ = RoleDefinition.objects.get_or_create(
        slug=SLUG,
        defaults={
            "label": LABEL,
            "description": DESCRIPTION,
            "scope": "PLATFORM",
            "is_builtin": True,
            "is_default": False,
            "is_assignable": False,
        },
    )
    definition.permissions.set([
        Permission.objects.get(
            content_type__app_label=app_label, codename=codename)
        for dotted in PERMISSIONS
        for app_label, _, codename in [dotted.partition(".")]
    ])

    # a group of exactly this name which no role manages yet is reused -
    # that is what the reverse of this migration leaves behind, in the shape
    # ``managed_group`` of 0008 established for the platform roles
    # check-then-create, as ``RoleQuerySet.create_for_organization`` does:
    # a group written before a create which would not run stays behind as an
    # orphan which ``accounts.E005`` would report
    role = Role.objects.filter(role_definition=definition,
                               organization__isnull=True).first()
    if role is None:
        # a group of exactly this name which no role manages yet is reused -
        # that is what the reverse of this migration leaves behind, in the
        # shape ``managed_group`` of 0008 established for the platform roles
        name = f"{PLATFORM_GROUP_PREFIX}: {SLUG}"[:GROUP_NAME_LIMIT]
        group = Group.objects.filter(
            name=name, role__isnull=True).first()
        if group is None:
            group = Group.objects.create(name=name)
        role = Role.objects.create(
            role_definition=definition, organization=None, group=group)
    else:
        group = role.group

    # the anonymous user of guardian: no usable password, never a login
    anonymous, _ = User.objects.get_or_create(
        username=ANONYMOUS_USERNAME,
        defaults={"password": make_password(None)})
    anonymous.groups.add(group)


def unseed_anonymous_viewer(apps, schema_editor):
    RoleDefinition = apps.get_model("accounts", "RoleDefinition")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))

    definition = RoleDefinition.objects.filter(slug=SLUG).first()
    if definition is None:
        return
    anonymous = list(User.objects.filter(username=ANONYMOUS_USERNAME))
    for role in definition.roles.filter(organization__isnull=True):
        if anonymous:
            role.group.user_set.remove(*anonymous)
        # the shape of ``Role.delete_with_group``: the Role PROTECTs its
        # group, so the Role goes first and the group - with every guardian
        # grant it carries, by their CASCADE - follows
        group = role.group
        role.delete()
        group.delete()
    # the anonymous user row stays: it may predate this migration (guardian
    # created it lazily before #739) and a user row is never deleted as the
    # reverse of a membership
    definition.delete()


# Carried over from the previous chain (accounts/0009_the_anonymous_viewer_role_group_is_seeded) when the migration history
# was regenerated from the models: the same python, only its dependencies moved.
class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_roles_for_the_groups_of_an_existing_instance"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(
            seed_anonymous_viewer, unseed_anonymous_viewer),
    ]
