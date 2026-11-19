"""The two role settings of #735 and the system check which keeps them honest.

``ROLE_MANAGED_MODELS`` says which models are resources: they know their owning
organization, and a new instance is granted to the roles of that organization.
``GUARDIAN_PERF_MODELS`` says which models answer their object permissions from
tables of their own. Both are lists, and a list rots the way ``SECURED_MODELS``
rotted - not by breaking, but by being believed while the code behind it is not
there. A model without its through-models answers from guardian's generic pair
*successfully*, only slowly, and with the query counts
``docs/source/administration/permissions.md`` describes no longer true: nothing
failed, so nobody fixed it.

What the check is asked here, one failure at a time:

* the shipped state answers nothing - every role-managed model has its pair of
  through-models, is carried by the performance list, names an owner, and every
  group the role system wrote is managed by a ``Role`` row
  (``accounts.E001`` to ``accounts.E006`` and ``accounts.W001`` are silent),
* a role-managed model which has no ``UserObjectPermission`` /
  ``GroupObjectPermission`` pair, or which the performance list does not carry,
  is ``accounts.E002``,
* a role-managed model which does not answer "which organization owns this
  instance" is ``accounts.E003``,
* a group which carries the name of a role group while no ``Role`` row manages
  it is ``accounts.E005``, and it stops the ``check`` command like any other
  error,
* the lists themselves are checked against the code: an entry naming no model
  (``accounts.E001``, ``accounts.E004``) and a declared through-pair the list
  does not carry (``accounts.W001``),
* the rollout switch of #739, ``PERMISSION_FILTERED_LIST_MODELS``, may only
  name a role-managed model: a list narrowed by the organization-role axis of
  the #734 facade hides the rows of a model the bootstrap never grants to an
  organization (``accounts.E006``),
* a command scoped to some apps (``manage.py check <app_label>``) answers for
  the models of those apps only - while an entry naming no model is still
  reported, because a typo belongs to the setting and has no app to ask.

The last test of the module answers the question #735's checklist asks: what
does adding a role-managed model cost? Declaring a model the code already
equips costs nothing but the entry - no role-group naming scheme, no migration
for the organizations which already exist, because the roles of an organization
come from the catalogue of #731 and not from the list of models. A model which
is *not* equipped is a different matter, and that is what the check refuses.
"""
from io import StringIO
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth.models import Group
from django.core.checks.registry import registry
from django.core.management import call_command
from django.core.management.base import SystemCheckError
from django.db import OperationalError, connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import override_settings

from accounts import settings as app_settings
from accounts.checks import (answers_ownership,
                             check_permission_filtered_list_models,
                             check_role_groups_are_managed,
                             check_role_managed_models)
from accounts.models.groups import Organization
from accounts.models.roles import Role
from registry.models.mapcontext import MapContext
from registry.models.service import (CatalogueService, WebFeatureService,
                                     WebMapService)

#: the ids of ``accounts/checks.py``, named so a test says which failure it
#: expects instead of counting messages
UNRESOLVED_ROLE_MANAGED_ID = "accounts.E001"
THROUGH_TABLES_ID = "accounts.E002"
OWNERSHIP_ID = "accounts.E003"
UNRESOLVED_PERF_ID = "accounts.E004"
ORPHAN_ROLE_GROUP_ID = "accounts.E005"
FILTERED_LIST_ID = "accounts.E006"
UNDECLARED_THROUGH_ID = "accounts.W001"

ORGANIZATION_NAME = "Checked Org"

#: a model which is neither equipped with through-models nor with an owner -
#: the shape a role-managed model may not have
UNEQUIPPED_MODEL = "registry.HarvestingJob"

#: a model which has its through-models but no owner: equipped for guardian,
#: not yet a resource
UNOWNED_MODEL = "registry.MapContext"

#: the model which is equipped for both but is not listed, because no role
#: definition may change it yet: see the comment in ``accounts/settings.py``
EQUIPPED_UNLISTED_MODEL = "registry.CatalogueService"


def texts(issues):
    """The messages of ``accounts/checks.py`` as readable, comparable strings.

    A ``CheckMessage`` is not nice to print, and comparing whole instances
    would pin the wording of a hint nobody needs to read again.

    Args:
        issues: the list a check returned

    Returns:
        list: ``"<id>: <message>"`` for every message, in the order returned
    """
    return [f"{issue.id}: {issue.msg}" for issue in issues]


def with_ids(issues, issue_id):
    """The messages of one id.

    Args:
        issues: the list a check returned
        issue_id: the ``id`` to select, as in ``accounts.E003``

    Returns:
        list: the messages carrying that id
    """
    return [issue for issue in issues if issue.id == issue_id]


class ShippedSettingsTestCase(TestCase):
    """What the settings of this checkout answer about themselves."""

    def test_the_shipped_lists_answer_no_issue(self):
        """Both settings and the role groups of a migrated database are clean"""
        issues = [*check_role_managed_models(databases=None),
                  *check_role_groups_are_managed(databases=["default"])]

        self.assertEqual(texts(issues), [],
                         "the settings of this checkout are not equipped, or "
                         "the guardian modules and the lists drifted apart")

    def test_the_role_managed_models_are_the_models_the_bootstrap_connects(self):
        """The list which connects the creation receiver is the shipped one

        Pinned on purpose: the entry of this list is a statement about the
        grants of every resource created from now on, and the reason
        ``registry.CatalogueService`` waits is told by the setting itself.
        """
        self.assertEqual(
            app_settings.ROLE_MANAGED_MODELS,
            ["registry.WebMapService", "registry.WebFeatureService"])
        self.assertEqual(
            app_settings.GUARDIAN_PERF_MODELS[:2],
            ["accounts.Organization", "auth.Group"],
            "the two models the bootstrap grants on are the first entries of "
            "the performance list")

    def test_every_role_managed_model_is_a_performance_model(self):
        """A resource never answers from the generic table"""
        self.assertTrue(
            set(app_settings.ROLE_MANAGED_MODELS)
            <= set(app_settings.GUARDIAN_PERF_MODELS))

    def test_the_equipped_resources_answer_the_ownership_question(self):
        """#733's column is the field the check accepts, on every service kind"""
        for model in (WebMapService, WebFeatureService, CatalogueService):
            self.assertTrue(
                answers_ownership(model),
                f"{model.__name__} stores its owner on the abstract "
                f"OgcService; the check has to see a field it inherits")
        self.assertFalse(answers_ownership(MapContext))

    def test_the_checks_are_registered_with_the_check_framework(self):
        """A check which is only importable answers nothing

        ``AccountsConfig.ready`` imports the module, which is what registers
        the functions - the same moment the signals of this app are connected.
        """
        registered = registry.registered_checks

        self.assertIn(check_role_managed_models, registered)
        self.assertIn(check_role_groups_are_managed, registered)
        self.assertIn(check_permission_filtered_list_models, registered)
        self.assertTrue(registry.tag_exists("accounts"),
                        "the tag which runs the checks of this app alone")


class MissingThroughTablesTestCase(TestCase):
    """A role-managed model which guardian answers from the generic table."""

    def test_a_model_without_its_through_models_is_reported(self):
        """No pair of its own and no entry in the performance list"""
        with patch.object(
                app_settings, "ROLE_MANAGED_MODELS",
                [*app_settings.ROLE_MANAGED_MODELS, UNEQUIPPED_MODEL]):
            issues = check_role_managed_models(databases=None)

        reported = with_ids(issues, THROUGH_TABLES_ID)
        self.assertEqual(len(reported), 1, texts(issues))
        self.assertIn(UNEQUIPPED_MODEL, reported[0].msg)
        self.assertIn("no UserObjectPermission of its own", reported[0].msg)
        self.assertIn("no GroupObjectPermission of its own", reported[0].msg)
        self.assertIn("GUARDIAN_PERF_MODELS does not carry it",
                      reported[0].msg)

    def test_a_model_left_out_of_the_performance_list_is_reported(self):
        """The pair is there, the list does not know about it

        The half of the check which is not about the tables but about the list:
        a model the bootstrap grants on has to be *declared* a performance
        model, else the next reader cannot tell whether the pair was meant to
        cover it.
        """
        with patch.object(
                app_settings, "ROLE_MANAGED_MODELS",
                [*app_settings.ROLE_MANAGED_MODELS, UNOWNED_MODEL]), \
                patch.object(
                    app_settings, "GUARDIAN_PERF_MODELS",
                    [name for name in app_settings.GUARDIAN_PERF_MODELS
                     if name != UNOWNED_MODEL]):
            issues = check_role_managed_models(databases=None)

        reported = with_ids(issues, THROUGH_TABLES_ID)
        self.assertEqual(len(reported), 1, texts(issues))
        self.assertIn("GUARDIAN_PERF_MODELS does not carry it",
                      reported[0].msg)
        self.assertNotIn("no UserObjectPermission", reported[0].msg,
                         "the pair of MapContext exists, only the list is "
                         "incomplete - a different fix")


class MissingOwnershipTestCase(TestCase):
    """A role-managed model which cannot say who owns an instance of it."""

    def test_a_model_without_an_owner_is_reported(self):
        """A resource which no organization owns is granted to nobody"""
        with patch.object(
                app_settings, "ROLE_MANAGED_MODELS",
                [*app_settings.ROLE_MANAGED_MODELS, UNOWNED_MODEL]):
            issues = check_role_managed_models(databases=None)

        reported = with_ids(issues, OWNERSHIP_ID)
        self.assertEqual(len(reported), 1, texts(issues))
        self.assertIn(UNOWNED_MODEL, reported[0].msg)
        self.assertIn("owner", reported[0].hint)
        # the model of #728's tables is equipped for guardian, so the missing
        # owner is the only thing this entry lacks
        self.assertEqual(with_ids(issues, THROUGH_TABLES_ID), [])

    def test_an_owner_which_is_no_organization_is_no_ownership(self):
        """A column of another shape is a different answer

        ``accounts.signals.owning_organization`` asks for an instance which
        *is* an organization, so a column named ``owner`` which is not a
        foreign key to one must not satisfy the check either.
        """
        with patch("accounts.checks.OWNERSHIP_FIELD", "title"):
            self.assertFalse(
                answers_ownership(MapContext),
                "'title' is asked for by the patched name and is no foreign "
                "key to an organization")


class UnresolvedEntryTestCase(TestCase):
    """An entry which names nothing: reported, never raised."""

    def test_an_entry_naming_no_model_is_reported_and_changes_nothing(self):
        """A typo takes no command down with it"""
        with patch.object(
                app_settings, "ROLE_MANAGED_MODELS",
                ["registry.Nope", "no app label here"]), \
                patch.object(
                    app_settings, "GUARDIAN_PERF_MODELS",
                    [*app_settings.GUARDIAN_PERF_MODELS, "registry.Nope"]):
            issues = check_role_managed_models(databases=None)

        unresolved = with_ids(issues, UNRESOLVED_ROLE_MANAGED_ID)
        self.assertEqual(len(unresolved), 2, texts(issues))
        self.assertEqual(
            sorted(issue.msg for issue in unresolved),
            sorted(
                f"The ROLE_MANAGED_MODELS entry {name!r} names no model of "
                f"this project."
                for name in ("registry.Nope", "no app label here")))
        self.assertEqual(
            [issue.msg for issue in with_ids(issues, UNRESOLVED_PERF_ID)
             if "names no model" in issue.msg],
            ["The GUARDIAN_PERF_MODELS entry 'registry.Nope' names no model "
             "of this project."],
            "both lists report their own typo, and the entries which resolve "
            "are not reported again")


class PerformanceListTestCase(TestCase):
    """The list of models with dedicated tables, against the code."""

    def test_a_listed_model_without_a_pair_of_its_own_is_reported(self):
        """The list claims a table which was never written"""
        with patch.object(
                app_settings, "GUARDIAN_PERF_MODELS",
                [*app_settings.GUARDIAN_PERF_MODELS, UNEQUIPPED_MODEL]):
            issues = check_role_managed_models(databases=None)

        reported = [issue for issue in with_ids(issues, UNRESOLVED_PERF_ID)
                    if UNEQUIPPED_MODEL in issue.msg]
        self.assertEqual(len(reported), 1, texts(issues))
        self.assertIn("no UserObjectPermission of its own", reported[0].msg)

    def test_a_through_pair_outside_the_list_is_reported_as_a_warning(self):
        """A pair written beside the declaration makes the list untrue"""
        with patch.object(
                app_settings, "GUARDIAN_PERF_MODELS",
                [name for name in app_settings.GUARDIAN_PERF_MODELS
                 if name != "registry.MapContextLayer"]):
            issues = check_role_managed_models(databases=None)

        reported = with_ids(issues, UNDECLARED_THROUGH_ID)
        self.assertEqual(len(reported), 1, texts(issues))
        self.assertIn("MapContextLayerUserObjectPermission", reported[0].msg)
        self.assertIn("MapContextLayerGroupObjectPermission", reported[0].msg)
        self.assertEqual(
            [issue for issue in issues if issue.is_serious()], [],
            "an undeclared pair is the list falling behind the code, which "
            "grants nothing wrongly and so must not block a command")


class PermissionFilteredListTestCase(TestCase):
    """The rollout switch of #739, whose entries an operator edits.

    ``PERMISSION_FILTERED_LIST_MODELS`` decides per model whether a LIST is
    narrowed to what the caller may view. The narrowing works on the axis of
    #734 which asks the owning organization's roles, so it answers only for a
    model the bootstrap grants to an organization: an entry outside
    ``ROLE_MANAGED_MODELS`` would hide rows in SQL rather than show them, and
    nothing but this check says so.
    """

    @override_settings(PERMISSION_FILTERED_LIST_MODELS=[])
    def test_the_shipped_rollout_answers_nothing(self):
        """Empty is today's behaviour kept, and today's behaviour is silent"""
        self.assertEqual(
            check_permission_filtered_list_models(databases=None), [])

    @override_settings(
        PERMISSION_FILTERED_LIST_MODELS=[WebMapService._meta.label])
    def test_a_role_managed_entry_is_silent(self):
        """The model the rollout is written for passes the guard"""
        self.assertEqual(
            check_permission_filtered_list_models(databases=None), [])

    @override_settings(
        PERMISSION_FILTERED_LIST_MODELS=[EQUIPPED_UNLISTED_MODEL])
    def test_a_model_the_bootstrap_does_not_manage_is_reported(self):
        """A model without an owning organization must not be narrowed

        ``registry.CatalogueService`` is equipped for guardian but is no
        resource of the role system - which is why the rollout does not carry
        it either.
        """
        issues = check_permission_filtered_list_models(databases=None)

        reported = with_ids(issues, FILTERED_LIST_ID)
        self.assertEqual(len(reported), 1, texts(issues))
        self.assertIn(EQUIPPED_UNLISTED_MODEL, reported[0].msg)
        self.assertTrue(reported[0].is_serious(),
                        "a rollout which hides rows is not a warning")

    @override_settings(PERMISSION_FILTERED_LIST_MODELS=["registry.Nope"])
    def test_an_entry_naming_no_model_is_reported(self):
        """A typo in a deployment list is an answer, not a crash"""
        issues = check_permission_filtered_list_models(databases=None)

        reported = with_ids(issues, FILTERED_LIST_ID)
        self.assertEqual(len(reported), 1, texts(issues))
        self.assertIn("names no model", reported[0].msg)


class DeclarationNeedsNoConnectionTestCase(TestCase):
    """The checks about the settings answer on a database without tables."""

    def test_a_broken_list_is_reported_without_a_database(self):
        """``migrate`` runs the checks before it wrote a single row

        ``BaseCommand.check`` passes no database for a command which asks for
        all checks, so a check about the declarations may not read one: on a
        fresh deployment it is the only voice which can still stop the start.
        """
        with patch.object(
                app_settings, "ROLE_MANAGED_MODELS",
                [*app_settings.ROLE_MANAGED_MODELS, UNEQUIPPED_MODEL]):
            issues = check_role_managed_models()

        self.assertEqual(
            sorted({issue.id for issue in issues}),
            [THROUGH_TABLES_ID, OWNERSHIP_ID],
            texts(issues))


class UnmigratedRoleGroupCheckTestCase(SimpleTestCase):
    """Database checks must let migrate create the tables they inspect."""

    def test_a_fresh_database_needs_no_role_tables(self):
        with patch.object(connection.introspection, "table_names",
                          return_value=[]):
            self.assertEqual(
                check_role_groups_are_managed(databases=["default"]), [])

    def test_a_partly_migrated_database_can_finish_migrating(self):
        tables = {"auth_group", "accounts_organization", "accounts_role",
                  "accounts_roledefinition"}
        for missing in sorted(tables):
            with self.subTest(missing=missing), patch.object(
                    connection.introspection, "table_names",
                    return_value=sorted(tables - {missing})):
                self.assertEqual(
                    check_role_groups_are_managed(databases=["default"]), [])

    def test_a_connection_failure_is_not_hidden(self):
        with patch.object(connection.introspection, "table_names",
                          side_effect=OperationalError("database unavailable")):
            with self.assertRaises(OperationalError):
                check_role_groups_are_managed(databases=["default"])


class OrphanRoleGroupTestCase(TestCase):
    """A group the role system named, which no ``Role`` row manages."""

    def setUp(self):
        self.organization = Organization.objects.create(name=ORGANIZATION_NAME)

    def test_the_groups_of_a_new_organization_are_explained(self):
        """Every group the bootstrap wrote is the group of a role"""
        self.assertTrue(Role.objects.for_org(self.organization).exists())
        self.assertEqual(
            check_role_groups_are_managed(databases=["default"]), [])

    def test_a_retired_role_group_is_still_explained(self):
        """A role of #741's work list is a role, and its group is its group"""
        role = Role.objects.for_org(self.organization).first()
        Role.objects.filter(pk=role.pk).update(is_active=False)

        self.assertEqual(
            check_role_groups_are_managed(databases=["default"]), [],
            "a retired role grants through its group until #741 deletes it, "
            "which is the state the retirement was written for")

    def test_a_role_group_whose_role_row_is_gone_is_reported(self):
        """The group outlives the row which explained it

        ``Role.group`` protects the group against deletion, not the other way
        round: whatever deletes the ``Role`` - by hand, or the cascade of a
        deleted organization - leaves the group and every grant it carries.
        """
        role = Role.objects.for_org(self.organization).first()
        group_name = role.group.name
        role.delete()

        reported = check_role_groups_are_managed(databases=["default"])

        self.assertEqual(len(reported), 1, texts(reported))
        self.assertEqual(reported[0].id, ORPHAN_ROLE_GROUP_ID)
        self.assertIn(group_name, reported[0].msg)

    def test_the_error_stops_the_check_command(self):
        """The check is not advice: an unexplained enforcing group is an error

        The state above is what a deployment inherits when a role is deleted
        outside the role API, so the command which starts the project refuses
        to start until the group has its role back or is gone.
        """
        role = Role.objects.for_org(self.organization).first()
        group_name = role.group.name
        role.delete()

        with self.assertRaises(SystemCheckError) as raised:
            call_command("check", databases=["default"],
                         stderr=StringIO())

        self.assertIn(ORPHAN_ROLE_GROUP_ID, str(raised.exception))
        self.assertIn(group_name, str(raised.exception))

    def test_a_group_which_is_no_role_group_is_not_reported(self):
        """Recognition asks the catalogue, so a colon is not a role group

        The names are the ones the fixtures of this repository carry: the
        legacy per-organization groups of the old bootstrap, which #732 wrote
        over as roles on a migrated instance but which a ``loaddata`` loads as
        plain groups, and a hand-made group whose name holds a colon.

        The last row is the case the exclusion of organizations is written
        for: an organization *is* a group - it shares ``auth_group``, name and
        uniqueness included - so a group row whose name happens to be the name
        of a role group is an organization somebody registered, not a role
        whose row is gone. Its name is built from a slug of the catalogue and
        a prefix no organization of this test owns, because ``auth_group.name``
        holds the role groups of ``Checked Org`` as well.
        """
        slug = (Role.objects.for_org(self.organization)
                .first().role_definition.slug)
        Group.objects.create(name="Group1")
        Group.objects.create(name="Default-Permissions")
        Group.objects.create(name=f"{ORGANIZATION_NAME} webmapservice Admins")
        Group.objects.create(name=f"{ORGANIZATION_NAME}: unrelated-slug")
        Organization.objects.create(name=f"Nested {ORGANIZATION_NAME}: {slug}")

        self.assertEqual(
            check_role_groups_are_managed(databases=["default"]), [])

    def test_the_number_of_a_colliding_role_group_name_is_recognised(self):
        """``free_role_group_name`` numbers a colliding name; the check reads it

        Two organizations whose names agree in their first characters truncate
        to the same name, so the second one's group gets a numbered name. That
        name is a role group name as much as the plain one is, so a group which
        carries it and no ``Role`` row is reported with it.
        """
        role = Role.objects.for_org(self.organization).first()
        orphan = Group.objects.create(name=f"{role.group.name} (2)")

        reported = check_role_groups_are_managed(databases=["default"])

        self.assertEqual(len(reported), 1, texts(reported))
        self.assertEqual(reported[0].id, ORPHAN_ROLE_GROUP_ID)
        self.assertIn(orphan.name, reported[0].msg)


class ConnectionNeededOnlyForGroupsTestCase(TestCase):
    """The database check says nothing when no connection may be read."""

    def test_the_group_check_stays_silent_without_a_database(self):
        """The same state, asked without ``databases``, answers nothing"""
        organization = Organization.objects.create(name=ORGANIZATION_NAME)
        role = Role.objects.for_org(organization).first()
        role.delete()

        self.assertEqual(
            check_role_groups_are_managed(databases=None), [],
            "a check which read a connection during ``migrate`` would take "
            "the command which creates the tables down with it")


class ScopedRunTestCase(TestCase):
    """A command scoped to some apps answers about those apps and no others."""

    def test_a_model_outside_the_inspected_apps_is_not_reported(self):
        """``manage.py check accounts`` does not answer for a registry model

        Every other check of the run answers for the apps the command names,
        and an answer which reaches over all models of the project would make
        this check disagree with them.
        """
        with patch.object(
                app_settings, "ROLE_MANAGED_MODELS",
                [*app_settings.ROLE_MANAGED_MODELS, UNEQUIPPED_MODEL]):
            issues = check_role_managed_models(
                [apps.get_app_config("accounts")])

        self.assertEqual(texts(issues), [],
                         "the unequipped model belongs to an app this command "
                         "did not name")

    def test_an_entry_naming_no_model_is_reported_by_a_scoped_run_too(self):
        """A typo is the setting's own fault and has no app to ask"""
        with patch.object(app_settings, "ROLE_MANAGED_MODELS",
                          ["registry.Nope"]):
            issues = check_role_managed_models(
                [apps.get_app_config("accounts")])

        self.assertEqual([issue.id for issue in issues],
                         [UNRESOLVED_ROLE_MANAGED_ID], texts(issues))

    def test_the_group_check_answers_for_no_other_app(self):
        """The role system is this app's, so its groups are this app's answer"""
        organization = Organization.objects.create(name=ORGANIZATION_NAME)
        Role.objects.for_org(organization).first().delete()

        scoped = check_role_groups_are_managed(
            [apps.get_app_config("registry")], databases=["default"])
        self.assertEqual(texts(scoped), [],
                         "a command about the registry does not audit the "
                         "groups of the role system")

        named = check_role_groups_are_managed(
            [apps.get_app_config("accounts")], databases=["default"])
        self.assertEqual(len(named), 1, texts(named))


class AddingARoleManagedModelTestCase(TestCase):
    """What declaring one more role-managed model costs (#735's checklist)."""

    def test_a_model_the_code_equips_needs_nothing_but_the_entry(self):
        """No new naming scheme, no migration for the organizations which exist

        ``registry.CatalogueService`` was equipped by #733 (its owner) and by
        the through-models of ``registry/models/guardian.py``. Declaring it
        therefore answers nothing, and it creates no group: the roles of an
        organization are its catalogue (#731), not the list of models, which is
        what frees a new role-managed model from the per-organization group
        migration the retired ``SECURED_MODELS`` needed.

        It is not listed today for a different reason, and the comment of the
        setting tells it: no definition of the catalogue may change a harvested
        record, so today no role would be granted one.
        """
        with patch.object(
                app_settings, "ROLE_MANAGED_MODELS",
                [*app_settings.ROLE_MANAGED_MODELS, EQUIPPED_UNLISTED_MODEL]):
            issues = [*check_role_managed_models(databases=None),
                      *check_role_groups_are_managed(databases=["default"])]

        self.assertEqual(texts(issues), [],
                         "a model which is equipped for ownership and for "
                         "guardian needs no further preparation, and the "
                         "check must not ask for any")
