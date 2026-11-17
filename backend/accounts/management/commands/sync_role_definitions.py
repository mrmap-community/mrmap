"""Keep the shipped role catalogue in the database (#731).

MrMap ships a builtin catalogue of role definitions: a versioned, readable
answer to "what may an editor do". The catalogue arrives twice:

* migration ``0005_...`` seeds it into every database, fresh or upgraded, and
* this command reconciles it afterwards.

The command is idempotent: run once or run hourly, an unchanged catalogue
changes nothing. Where a row **differs** from the shipped definition - an
operator adjusted the permission set of ``resource_editor`` deliberately -
the command reports the difference field by field and **keeps the database's
value**. Overwriting an operator's customization silently is exactly what
decision Q4 = A of #727 forbids. An operator who wants the shipped state back
edits the row to match the catalogue (the label and description are editable
for exactly this reconciliation loop).

The catalogue below is the live one; the migration holds the frozen copy it
seeds. A test pins that a freshly migrated database and this command agree,
so the two cannot drift unnoticed.
"""

from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand

from accounts.models.roles import RoleDefinition, RoleScope

#: the read permission on catalogue services, named once for its own sake:
#: the reading roles share it through REGISTRY_READ below, and the harvester
#: and the service account cannot start their work without it
CATALOGUE_READ = "registry.view_catalogueservice"

#: what "reads the registry" means: the four read permissions the reading
#: roles all carry, so the roles differ in what they may change, not in what
#: they may read - stated once, as the codenames are the vocabulary of the
#: catalogue
REGISTRY_READ = (
    "registry.view_webmapservice",
    "registry.view_webfeatureservice",
    CATALOGUE_READ,
    "registry.view_mapcontext",
)

#: the read permission on the organization row, which the three roles that
#: name an organization in their screen share
ORGANIZATION_READ = "accounts.view_organization"

#: the builtin catalogue. ``permissions`` are ``app_label.codename`` strings;
#: every one of them must exist as a ``Permission`` row, which #731 verifies
#: by test. The catalogue deliberately holds plain data - an operator's
#: deployment can be audited by reading this list against
#: ``manage.py sync_role_definitions`` output.
BUILTIN_ROLES = [
    {
        "slug": "viewer",
        "label": "Viewer",
        "description": (
            "Reads the registry: services, records and map contexts."),
        "scope": RoleScope.ORGANIZATION,
        "is_default": True,
        "is_assignable": True,
        "permissions": [
            *REGISTRY_READ,
        ],
    },
    {
        "slug": "resource_editor",
        "label": "Resource editor",
        "description": (
            "Registers and changes services of the organization; publishing "
            "and deleting are the publisher's and the administrator's."),
        "scope": RoleScope.ORGANIZATION,
        "is_default": False,
        "is_assignable": True,
        "permissions": [
            *REGISTRY_READ,
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
        "scope": RoleScope.ORGANIZATION,
        "is_default": False,
        "is_assignable": True,
        "permissions": [
            *REGISTRY_READ,
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
        "scope": RoleScope.ORGANIZATION,
        "is_default": False,
        "is_assignable": True,
        "permissions": [
            *REGISTRY_READ,
            ORGANIZATION_READ,
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
        "scope": RoleScope.ORGANIZATION,
        "is_default": False,
        "is_assignable": True,
        "permissions": [
            CATALOGUE_READ,
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
        "scope": RoleScope.PLATFORM,
        "is_default": False,
        "is_assignable": False,
        "permissions": [
            "accounts.view_user",
            "accounts.add_user",
            "accounts.change_user",
            ORGANIZATION_READ,
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
        "scope": RoleScope.PLATFORM,
        "is_default": False,
        "is_assignable": True,
        "permissions": [
            "accounts.view_user",
            ORGANIZATION_READ,
            "accounts.view_roledefinition",
            *REGISTRY_READ,
        ],
    },
    {
        "slug": "service_account",
        "label": "Service account",
        "description": (
            "The machine account of automated registration and harvesting "
            "over the API; no human signs in with it."),
        "scope": RoleScope.PLATFORM,
        "is_default": False,
        "is_assignable": True,
        "permissions": [
            CATALOGUE_READ,
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
    {
        "slug": "anonymous_viewer",
        "label": "Anonymous viewer",
        "description": (
            "The visitors without an account. A view grant of a resource "
            "onto this role's group is what makes the resource public "
            "(#739); nothing joins it - the guardian anonymous user is its "
            "only member and publishing stays an explicit act (decision Q2 "
            "of #727)."),
        "scope": RoleScope.PLATFORM,
        "is_default": False,
        # the member picker of #737 adds people to roles; nobody is the
        # anonymous viewer by decision, so the role is not offered there
        "is_assignable": False,
        "permissions": [
            *REGISTRY_READ,
        ],
    },
]

#: the catalogue fields the command reconciles; ``is_builtin`` is not among
#: them - it marks the shipped rows and nobody's edit of it is a customization
COMPARED_FIELDS = ("label", "description", "scope",
                   "is_default", "is_assignable")


class Command(BaseCommand):
    help = ("Reconcile the shipped builtin role catalogue with the database: "
            "creates missing definitions, reports edited ones instead of "
            "reverting them, and changes nothing when nothing differs "
            "(#731).")

    def handle(self, *args, **options):
        created = []
        in_sync = []
        drifted = []

        for spec in BUILTIN_ROLES:
            role = RoleDefinition.objects.filter(slug=spec["slug"]).first()
            if role is None:
                self._create(spec)
                created.append(spec["slug"])
                continue
            differences = self._differences(role, spec)
            if differences:
                drifted.append(spec["slug"])
                self.stdout.write(
                    self.style.WARNING(
                        f"role '{spec['slug']}' differs from the shipped "
                        f"catalogue and was kept as edited:"))
                for line in differences:
                    self.stdout.write(f"  {line}")
            else:
                in_sync.append(spec["slug"])

        self.stdout.write(
            f"sync_role_definitions: {len(BUILTIN_ROLES)} builtin roles - "
            f"{len(created)} created, {len(in_sync)} in sync, "
            f"{len(drifted)} reported as edited"
            + (f" ({', '.join(drifted)})" if drifted else ""))

    def _create(self, spec):
        """Create one missing catalogue role, permissions included.

        Args:
            spec (dict): the catalogue entry
        """
        role = RoleDefinition.objects.create(
            slug=spec["slug"],
            label=spec["label"],
            description=spec["description"],
            scope=spec["scope"],
            is_builtin=True,
            is_default=spec["is_default"],
            is_assignable=spec["is_assignable"])
        role.permissions.set(self._permissions_of(spec))
        self.stdout.write(
            self.style.SUCCESS(f"created builtin role '{spec['slug']}'"))

    def _permissions_of(self, spec):
        """The Permission rows a catalogue entry names.

        A codename without a row is a bug in the catalogue, not a thing to
        paper over: the query would silently hand back a shorter set and the
        role would mean something else than it says. Letting the lookup raise
        names the codename which is missing.

        Args:
            spec (dict): the catalogue entry

        Returns:
            list: the Permission rows named by ``spec["permissions"]``
        """
        permissions = []
        for dotted in spec["permissions"]:
            app_label, _, codename = dotted.partition(".")
            permissions.append(
                Permission.objects.get(
                    content_type__app_label=app_label, codename=codename))
        return permissions

    def _differences(self, role, spec):
        """What the database row says differently than the catalogue.

        Nothing is written here - this is the drift report the operator gets
        instead of an overwrite.

        Args:
            role (RoleDefinition): the persisted row
            spec (dict): the catalogue entry

        Returns:
            list: one readable line per differing field, empty when the row
                matches the catalogue
        """
        differences = []
        for field in COMPARED_FIELDS:
            if getattr(role, field) != spec[field]:
                differences.append(
                    f"{field}: catalogue says {spec[field]!r}, "
                    f"database says {getattr(role, field)!r}")
        catalogue = set(spec["permissions"])
        stored = {
            f"{permission.content_type.app_label}."
            f"{permission.codename}"
            for permission in role.permissions.all()}
        for missing in sorted(catalogue - stored):
            differences.append(
                f"permissions: {missing} is in the catalogue but not on the "
                f"role")
        for extra in sorted(stored - catalogue):
            differences.append(
                f"permissions: {extra} is on the role but not in the "
                f"catalogue")
        return differences
