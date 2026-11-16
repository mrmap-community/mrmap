# The builtin role catalogue of #731, seeded into every database: fresh
# installs get it here, instances which upgrade from before #731 get it here,
# and ``manage.py sync_role_definitions`` reconciles it afterwards. This is
# the frozen copy - the catalogue the command ships with today lives in
# ``accounts/management/commands/sync_role_definitions.py`` and a later change
# to it arrives as a new migration, not as an edit here. The test
# ``test_the_catalogue_matches_the_migration_after_the_migrations`` pins that
# the two agree for this state of the code, so a catalogue edited in only one
# place fails.
#
# Reading a ``Permission`` row here takes creating them first: the command
# ``migrate`` fires the ``post_migrate`` handlers which build the permission
# rows only after the whole plan ran, so during any RunPython - on a fresh
# database, of which the test database is one - even the defaults of a model
# may still be missing. The seeding therefore calls Django's own
# ``create_permissions`` for the two apps first. Not a hand-written stand-in:
# that function keys rows by (content type, codename), computes the names
# exactly as the model Meta declares them and skips what exists, so this
# migration and the later ``post_migrate`` handler write one and the same
# rows. The five new ``registry`` permissions arrive with it because the live
# ``Meta.permissions`` of ``WebMapService`` and ``HarvestingJob`` declare them
# (that model comment says why ``WebMapService`` carries the service-wide
# capabilities).
#
# Reverse deletes the seeded role rows and the five new custom permissions.
# It leaves the default permissions: they belong to their model's migration,
# and a later forward re-creates the customs idempotently.

from django.apps import apps as global_apps
from django.contrib.auth.management import create_permissions
from django.db import migrations

#: the frozen catalogue. Slugs are the names later issues (#732, #736) refer
#: to; they are stable for as long as the rows exist.
BUILTIN_ROLES = [
    {
        "slug": "viewer",
        "label": "Viewer",
        "description": (
            "Reads the registry: services, records and map contexts."),
        "scope": "ORGANIZATION",
        "is_default": True,
        "is_assignable": True,
        "permissions": [
            "registry.view_webmapservice",
            "registry.view_webfeatureservice",
            "registry.view_catalogueservice",
            "registry.view_mapcontext",
        ],
    },
    {
        "slug": "resource_editor",
        "label": "Resource editor",
        "description": (
            "Registers and changes services of the organization; publishing "
            "and deleting are the publisher's and the administrator's."),
        "scope": "ORGANIZATION",
        "is_default": False,
        "is_assignable": True,
        "permissions": [
            "registry.view_webmapservice",
            "registry.view_webfeatureservice",
            "registry.view_catalogueservice",
            "registry.view_mapcontext",
            "registry.add_webmapservice",
            "registry.change_webmapservice",
            "registry.add_webfeatureservice",
            "registry.change_webfeatureservice",
        ],
    },
    {
        "slug": "resource_publisher",
        "label": "Resource publisher",
        "description": (
            "Publishes resources and shares them. Publishing is always an "
            "explicit act (decision Q2 of #727)."),
        "scope": "ORGANIZATION",
        "is_default": False,
        "is_assignable": True,
        "permissions": [
            "registry.view_webmapservice",
            "registry.view_webfeatureservice",
            "registry.view_catalogueservice",
            "registry.view_mapcontext",
            "registry.publish_resource",
            "registry.share_resource",
        ],
    },
    {
        "slug": "organization_admin",
        "label": "Organization administrator",
        "description": (
            "Administers one organization: its members, its access rules and "
            "its publishing requests."),
        "scope": "ORGANIZATION",
        "is_default": False,
        "is_assignable": True,
        "permissions": [
            "registry.view_webmapservice",
            "registry.view_webfeatureservice",
            "registry.view_catalogueservice",
            "registry.view_mapcontext",
            "accounts.view_organization",
            "accounts.change_organization",
            "accounts.can_publish_for_organization",
            "registry.manage_membership",
            "registry.manage_access_rules",
        ],
    },
    {
        "slug": "harvester",
        "label": "Harvester",
        "description": (
            "Runs and follows harvesting jobs over a catalogue service."),
        "scope": "ORGANIZATION",
        "is_default": False,
        "is_assignable": True,
        "permissions": [
            "registry.view_catalogueservice",
            "registry.view_webmapservice",
            "registry.view_webfeatureservice",
            "registry.view_harvestingjob",
            "registry.add_harvestingjob",
            "registry.change_harvestingjob",
            "registry.harvest",
        ],
    },
    {
        "slug": "platform_admin",
        "label": "Platform administrator",
        "description": (
            "Administers the whole instance: accounts, organizations and the "
            "role definitions. Not offered in the member picker; it is not a "
            "replacement for the break-glass superuser (decision Q6 of #727)."),
        "scope": "PLATFORM",
        "is_default": False,
        "is_assignable": False,
        "permissions": [
            "accounts.view_user",
            "accounts.add_user",
            "accounts.change_user",
            "accounts.view_organization",
            "accounts.add_organization",
            "accounts.change_organization",
            "accounts.view_roledefinition",
            "accounts.grant_platform_role",
            "registry.manage_access_rules",
            "registry.manage_membership",
        ],
    },
    {
        "slug": "support",
        "label": "Support",
        "description": (
            "Reads accounts, organizations and the registry across all "
            "organizations to help users; changes nothing."),
        "scope": "PLATFORM",
        "is_default": False,
        "is_assignable": True,
        "permissions": [
            "accounts.view_user",
            "accounts.view_organization",
            "accounts.view_roledefinition",
            "registry.view_webmapservice",
            "registry.view_webfeatureservice",
            "registry.view_catalogueservice",
            "registry.view_mapcontext",
        ],
    },
    {
        "slug": "service_account",
        "label": "Service account",
        "description": (
            "The machine account of automated registration and harvesting "
            "over the API; no human signs in with it."),
        "scope": "PLATFORM",
        "is_default": False,
        "is_assignable": True,
        "permissions": [
            "registry.view_catalogueservice",
            "registry.view_harvestingjob",
            "registry.add_harvestingjob",
            "registry.change_harvestingjob",
            "registry.harvest",
            "registry.add_webmapservice",
            "registry.change_webmapservice",
            "registry.add_webfeatureservice",
            "registry.change_webfeatureservice",
        ],
    },
]

#: the new custom permissions of the catalogue, with the model their
#: ``ContentType`` resolves on - the models of the ``Meta.permissions``
#: declarations - listed here so the reverse knows exactly which rows the
#: catalogue migration introduced; the forward creates them through Django's
#: own machinery, not from this list
CUSTOM_PERMISSIONS = [
    ("registry", "webmapservice", "publish_resource",
     "Can publish a registry resource"),
    ("registry", "webmapservice", "share_resource",
     "Can share a registry resource"),
    ("registry", "webmapservice", "manage_access_rules",
     "Can manage access rules"),
    ("registry", "webmapservice", "manage_membership",
     "Can manage organization memberships"),
    ("registry", "harvestingjob", "harvest",
     "Can run a harvesting job"),
]

SEED_SLUGS = [role["slug"] for role in BUILTIN_ROLES]


def create_permission_rows(apps, schema_editor):
    """Have Django build the ``Permission`` rows the catalogue reads.

    ``create_permissions`` is the very function ``post_migrate`` calls: it
    takes the models as the code declares them, keys rows by
    (content type, codename), computes every name from the model Meta and
    skips rows already in place. Calling it here is what lets this migration
    seed on a fresh database - and on an upgraded one it is a no-op over the
    existing rows, adding just the new custom codenames the live Meta names.

    The live app registry is passed as ``apps``, the same way the signal does
    it; the historical ``apps`` of this migration would render models from the
    migration state, which is not what the final ``post_migrate`` will write.
    """
    using = schema_editor.connection.alias
    for app_label in ("registry", "accounts"):
        create_permissions(
            global_apps.get_app_config(app_label),
            using=using,
            apps=global_apps,
            verbosity=0)


def unseed_custom_permissions(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    for app_label, _model_name, codename, _name in CUSTOM_PERMISSIONS:
        Permission.objects.filter(
            content_type__app_label=app_label,
            codename=codename).delete()


def seed_role_catalogue(apps, schema_editor):
    RoleDefinition = apps.get_model("accounts", "RoleDefinition")
    Permission = apps.get_model("auth", "Permission")
    for spec in BUILTIN_ROLES:
        # get_or_create, not create: a re-run after a partial seed, or a
        # deployment which already ran ``sync_role_definitions`` on a
        # pre-#731 checkout of a development branch, holds these rows
        role, created = RoleDefinition.objects.get_or_create(
            slug=spec["slug"],
            defaults={
                "label": spec["label"],
                "description": spec["description"],
                "scope": spec["scope"],
                "is_builtin": True,
                "is_default": spec["is_default"],
                "is_assignable": spec["is_assignable"],
            },
        )
        if created:
            # every entry is looked up by its exact (app_label, codename)
            # pair: a codename alone could match a permission of the other
            # app, and a missing row is a bug in this catalogue - ``get``
            # names it instead of silently shortening the role
            permissions = []
            for dotted in spec["permissions"]:
                app_label, _, codename = dotted.partition(".")
                permissions.append(Permission.objects.get(
                    content_type__app_label=app_label, codename=codename))
            role.permissions.set(permissions)


def unseed_role_catalogue(apps, schema_editor):
    RoleDefinition = apps.get_model("accounts", "RoleDefinition")
    RoleDefinition.objects.filter(slug__in=SEED_SLUGS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_role_definitions'),
        ('auth', '0012_alter_user_first_name_max_length'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.RunPython(
            create_permission_rows,
            unseed_custom_permissions,
        ),
        migrations.RunPython(
            seed_role_catalogue,
            unseed_role_catalogue,
        ),
    ]
