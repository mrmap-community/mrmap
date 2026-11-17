"""The guard which keeps the two role settings of #735 honest.

``accounts.settings.ROLE_MANAGED_MODELS`` names the models whose instances are
owned and granted to the roles of their owning organization;
``accounts.settings.GUARDIAN_PERF_MODELS`` names the models which answer their
object permissions from tables of their own. Both are lists, and a list is
exactly what rotted before: the single ``SECURED_MODELS`` could gain a model
nobody had equipped, because guardian answers a model without its own tables
from the generic pair *successfully* - only slowly, and with query counts which
are no longer the ones the tests of this repository assert. Nothing failed, so
nothing was fixed.

What is checked, and what it is worth:

* ``accounts.E002`` - a role-managed model which has no dedicated pair of
  through-models, or which the performance list does not carry. Without the
  pair the grants of the role work land in guardian's shared table, and every
  lookup of a model with a uuid primary key takes the cast of its text column
  (``registry/models/guardian.py`` tells that story).
* ``accounts.E003`` - a role-managed model which does not answer the ownership
  question. The bootstrap grants a new instance to the roles of *its*
  organization, so a model without an owner column cannot be role-managed:
  ``accounts.signals.owning_organization`` would answer None and the instance
  would be granted to nobody while the list claims it is managed.
* ``accounts.E005`` - a group which is named like the group of a role while no
  ``Role`` row manages it. The group of a role is what enforces the role, and
  it outlives its ``Role`` row: a deleted role - or the roles of a deleted
  organization - leaves a group behind which still grants everything it was
  granted, with nothing to explain it (#741 asks every grant to be
  explainable down to a decision).

Two more messages keep the lists themselves honest: an entry naming no model
(``accounts.E001`` for the role-managed list, ``accounts.E004`` for the
performance list) and a declared through-pair the performance list does not
carry (``accounts.W001``). The list is the declaration of the set, so a pair of
tables written beside it is a list which no longer answers what is there.

The checks run with every run of the check framework: at the startup of the test
runner, of ``migrate`` and of ``runserver``. The declaration checks need no
connection - their answer is in the code, so they also answer on a deployment
whose tables do not exist yet - while ``E005`` reads the database and stays
silent whenever the command says no connection may be used. Both honour the
``app_configs`` a scoped command passes: ``manage.py check registry`` hears about
the models of the apps it names, and an entry which names no model at all is
reported by every run, because a typo belongs to the setting and has no app.
"""
from django.apps import apps
from django.core.checks import Error, Tags, Warning, register
from django.core.exceptions import FieldDoesNotExist
from django.db import models

from accounts import settings as app_settings

#: the tag of the checks of this module: ``manage.py check -t accounts`` answers
#: these and nothing else
CHECK_TAG = "accounts"

#: the app whose role system ``check_role_groups_are_managed`` answers for: the
#: groups are written by this app's bootstrap, so a command scoped to other apps
#: does not hear about them
ROLE_APP_LABEL = "accounts"

#: the field which answers "which organization owns this instance?", read by
#: ``accounts.signals.owning_organization``
OWNERSHIP_FIELD = "owner"

#: the two sides of a through-model pair, named as guardian names its bases: a
#: message about a missing side says which class the model still needs
SIDES = ("UserObjectPermission", "GroupObjectPermission")


def model_of(name):
    """The model a ``"<app_label>.<ModelName>"`` names, or None.

    A check reports an entry which resolves to nothing rather than raising: a
    check which raises takes every command of the project down with it, and a
    setting is exactly the place a developer or an operator edits.

    Args:
        name: a dotted model name as the settings of this app hold them

    Returns:
        the model class, or None when the name is no model of this project
    """
    parts = name.split('.') if name else []
    if len(parts) != 2 or not all(parts):
        return None
    try:
        return apps.get_model(app_label=parts[0], model_name=parts[1])
    except LookupError:
        return None


def content_object_target(through_model):
    """The model a through-model's ``content_object`` points at, or None.

    Args:
        through_model: a subclass of one of guardian's object permission bases

    Returns:
        the target model of the foreign key, or None for an abstract class and
        for the generic tables of guardian, whose ``content_object`` is a
        ``GenericForeignKey`` and not a key to one model
    """
    if through_model._meta.abstract:
        return None
    try:
        field = through_model._meta.get_field("content_object")
    except FieldDoesNotExist:
        return None
    if not isinstance(field, models.ForeignKey):
        return None
    return field.related_model


def dedicated_obj_perm_models():
    """The models with dedicated object permission tables, as they are declared.

    Read from the app registry rather than from guardian's own resolver: that
    resolver asks a ``ContentType``, which is a row, and this check has to
    answer during a ``migrate`` on a database without rows. A through-model
    names its model with a real foreign key on ``content_object``; the generic
    tables name their object by content type and a text column instead, which
    is the very thing a through-model is written to avoid.

    Returns:
        dict: ``{model: {side: through-model}}`` mapping every model with a
        table of its own to the through-model of each side of ``SIDES``. A
        side which is missing answers None, because half a pair is one of the
        failures this check is written for.
    """
    # late import: what this check inspects are the classes guardian's bases
    # give rise to; importing here keeps the module importable from
    # ``AccountsConfig.ready`` without a load-order promise
    from guardian.models import (GroupObjectPermissionBase,
                                 UserObjectPermissionBase)

    dedicated = {}
    for through_model in apps.get_models():
        if issubclass(through_model, UserObjectPermissionBase):
            side = SIDES[0]
        elif issubclass(through_model, GroupObjectPermissionBase):
            side = SIDES[1]
        else:
            continue

        target = content_object_target(through_model)
        if target is None:
            # one of the generic tables of guardian: no foreign key, no model
            continue

        pair = dedicated.setdefault(target, {side: None for side in SIDES})
        pair[side] = through_model
    return dedicated


def missing_sides(pair):
    """The halves of a through-model pair which are not there.

    Args:
        pair: the entry of ``dedicated_obj_perm_models`` for one model, or None

    Returns:
        list: the names of the missing sides, in the order of ``SIDES``; empty
        when the pair is complete
    """
    return [side for side in SIDES if pair is None or pair.get(side) is None]


def answers_ownership(model):
    """Whether an instance of ``model`` names the organization which owns it.

    The question is the one ``accounts.signals.owning_organization`` asks with
    ``getattr(instance, 'owner', None)``, so the field is asked for by that
    name, as a foreign key to ``Organization``, and on the model or on one of
    its abstract parents - which is how the OGC services declare it
    (``registry.models.service.OgcService.owner``).

    Args:
        model: the model class to ask

    Returns:
        bool: whether the model stores an owning organization
    """
    # late import: ``accounts.checks`` is imported by the app config of this
    # app, at which point the models of the project may still be loading
    from accounts.models.groups import Organization

    try:
        field = model._meta.get_field(OWNERSHIP_FIELD)
    except FieldDoesNotExist:
        return False
    return (isinstance(field, models.ForeignKey)
            and field.related_model is Organization)


def no_side_words(missing):
    """The missing sides of a pair as words of one clause.

    Args:
        missing: the answer of ``missing_sides``

    Returns:
        str: like "no UserObjectPermission and no GroupObjectPermission"
    """
    return " and ".join(f"no {side} of its own" for side in missing)


def inspected_labels(app_configs):
    """The app labels a scoped command asked about, None for all of them.

    ``manage.py check <app_label>`` and ``makemigrations <app_label>`` pass the
    apps they were told to inspect, and a check answers for those alone - the
    convention every check of Django's own apps follows. Answering for all
    models of the project as well would make a scoped run disagree with the
    other checks that same run reports.

    Args:
        app_configs: the ``AppConfig`` instances of the check framework, None
            when the command was not scoped

    Returns:
        set or None: the labels to report about, None for every app
    """
    if app_configs is None:
        return None
    return {config.label for config in app_configs}


def reports_about(labels, model):
    """Whether a message about ``model`` belongs to a run over ``labels``.

    Args:
        labels: the answer of ``inspected_labels``
        model: the model the message is about, or None for an entry which names
            no model - a typo is the setting's own fault and has no app to ask,
            so every run reports it

    Returns:
        bool: whether this run reports the message
    """
    return (labels is None or model is None
            or model._meta.app_label in labels)


def unresolved_entry_issue(name, setting, hint, issue_id):
    """The message for a list entry which names no model of this project.

    Args:
        name: the entry as the setting holds it
        setting (str): the name of the setting which holds the entry
        hint (str): what to do about it, told by the list it belongs to
        issue_id (str): the id to report - each list answers for its own

    Returns:
        Error: the message
    """
    return Error(
        f"The {setting} entry {name!r} names no model of this project.",
        hint=f"Name the model as '<app_label>.<ModelName>'. {hint}",
        id=issue_id)


def resolved_entries(names, setting, hint, issue_id):
    """The models a setting names, with a message for every entry naming none.

    A check reports an entry which resolves to nothing rather than raising: a
    check which raises takes every command of the project down with it, and a
    setting is exactly what a developer or an operator edits.

    Args:
        names: the entries of the setting
        setting (str): the name of the setting, for the message
        hint (str): what to do about an entry which names no model
        issue_id (str): the id to report for such an entry

    Returns:
        tuple: ``(models, issues)`` with ``models`` mapping every resolved
        model to the entry naming it, and ``issues`` the messages of the rest
    """
    models = {}
    issues = []
    for name in names:
        model = model_of(name)
        if model is None:
            issues.append(unresolved_entry_issue(
                name, setting, hint, issue_id))
            continue
        models[model] = name
    return models, issues


def uncovered_model_issue(name, missing, declared):
    """The message for a role-managed model guardian cannot answer quickly.

    Args:
        name: the entry as the setting holds it
        missing: the answer of ``missing_sides`` for its pair
        declared (bool): whether ``GUARDIAN_PERF_MODELS`` carries it

    Returns:
        Error or None: the message, or None when the model is covered
    """
    problems = []
    if missing:
        problems.append(no_side_words(missing))
    if not declared:
        problems.append("GUARDIAN_PERF_MODELS does not carry it")
    if not problems:
        return None
    return Error(
        f"The role-managed model {name!r} does not answer its object "
        f"permissions from tables of its own: {', '.join(problems)}.",
        hint="Guardian would store the grants of the role work in its "
             "generic table, and every lookup of a model with a uuid "
             "primary key would take the cast of that text column - "
             "the regression the through-models of "
             "registry/models/guardian.py exist for. Declare the "
             "missing through-models with their migration and add the "
             "model to GUARDIAN_PERF_MODELS.",
        id="accounts.E002")


def undeclared_pair_warning(model, pair):
    """The message for a through-pair written beside the performance list.

    Args:
        model: the model the pair of tables belongs to
        pair: the entry of ``dedicated_obj_perm_models`` for that model

    Returns:
        Warning: the message naming both sides which are there
    """
    through = sorted(
        through_model.__name__
        for through_model in (pair[side] for side in SIDES)
        if through_model is not None)
    return Warning(
        f"The object permission tables {', '.join(through)} of "
        f"{model._meta.label} are not declared in GUARDIAN_PERF_MODELS.",
        hint="The setting is the declaration of the models which answer "
             "from tables of their own; a pair written beside it is a "
             "declaration which no longer says what is there. Add the "
             "model to the list, with the reason it has its tables.",
        id="accounts.W001")


def role_managed_issues(labels, role_managed, perf_models, dedicated):
    """The messages about the models the permission bootstrap grants on.

    Args:
        labels: the answer of ``inspected_labels``
        role_managed: the resolved ``ROLE_MANAGED_MODELS``
        perf_models: the resolved ``GUARDIAN_PERF_MODELS``
        dedicated: the answer of ``dedicated_obj_perm_models``

    Returns:
        list: ``accounts.E002`` for a listed model whose object permissions are
        not covered, ``accounts.E003`` for one which knows no owner
    """
    issues = []
    for model, name in role_managed.items():
        if not reports_about(labels, model):
            continue
        uncovered = uncovered_model_issue(
            name, missing_sides(dedicated.get(model)), model in perf_models)
        if uncovered is not None:
            issues.append(uncovered)
        if not answers_ownership(model):
            issues.append(Error(
                f"The role-managed model {name!r} does not know an owner.",
                hint=f"A role-managed resource is granted to the roles of the "
                     f"organization which owns it, which "
                     f"accounts.signals.owning_organization reads from an "
                     f"'{OWNERSHIP_FIELD}' foreign key to "
                     f"accounts.Organization. Declare that field with its "
                     f"migration, or take the model out of the list (#735).",
                id="accounts.E003"))
    return issues


def perf_model_issues(labels, perf_models, dedicated):
    """The messages about the performance list claiming tables it lacks.

    Args:
        labels: the answer of ``inspected_labels``
        perf_models: the resolved ``GUARDIAN_PERF_MODELS``
        dedicated: the answer of ``dedicated_obj_perm_models``

    Returns:
        list: ``accounts.E004`` for every listed model without its pair
    """
    issues = []
    for model, name in perf_models.items():
        missing = missing_sides(dedicated.get(model))
        if missing and reports_about(labels, model):
            issues.append(Error(
                f"{name!r} is listed in GUARDIAN_PERF_MODELS but declares "
                f"{no_side_words(missing)}.",
                hint="Declare the through-models in "
                     "accounts/models/guardian.py or "
                     "registry/models/guardian.py, or drop the entry: the "
                     "list says a lookup of this model never touches the "
                     "generic table, and it does.",
                id="accounts.E004"))
    return issues


def undeclared_pair_issues(labels, perf_models, dedicated):
    """The messages about a through-pair written beside the performance list.

    Args:
        labels: the answer of ``inspected_labels``
        perf_models: the resolved ``GUARDIAN_PERF_MODELS``
        dedicated: the answer of ``dedicated_obj_perm_models``

    Returns:
        list: one ``accounts.W001`` per pair the list does not carry, ordered by
        the model it belongs to so the answer of a run does not depend on the
        order the app registry happens to report its models in
    """
    undeclared = {
        model: pair for model, pair in dedicated.items()
        if model not in perf_models}
    return [
        undeclared_pair_warning(model, pair)
        for model, pair in sorted(undeclared.items(),
                                  key=lambda item: item[0]._meta.label)
        if reports_about(labels, model)]


@register(CHECK_TAG, Tags.models)
def check_role_managed_models(app_configs=None, **kwargs):
    """Every role-managed model is equipped, and both lists answer what is there.

    Compares the two settings of ``accounts.settings`` with what the models
    declare. No connection is used: the whole answer is in the code, so the
    check also answers during a ``migrate`` which has not created a table yet.

    Args:
        app_configs: the apps to inspect, None for all of them. A scoped
            ``manage.py check <app_label>`` hears about the models of its apps
            and nothing else, as every check of Django's own apps answers; the
            pair of a model is still looked for across all apps, so a scoped
            run cannot mistake a model for one without tables.
        **kwargs: the keyword arguments of the check framework, unused

    Returns:
        list: the ``CheckMessage`` instances of the problems found
    """
    labels = inspected_labels(app_configs)
    dedicated = dedicated_obj_perm_models()

    perf_models, issues = resolved_entries(
        app_settings.GUARDIAN_PERF_MODELS, "GUARDIAN_PERF_MODELS",
        "The list declares which models answer from tables of their own, and "
        "an entry which is no model declares nothing.",
        "accounts.E004")
    role_managed, unresolved = resolved_entries(
        app_settings.ROLE_MANAGED_MODELS, "ROLE_MANAGED_MODELS",
        "The permission bootstrap connects the receiver which grants a new "
        "resource to what this list resolves.",
        "accounts.E001")
    issues.extend(unresolved)

    issues.extend(role_managed_issues(labels, role_managed, perf_models,
                                      dedicated))
    issues.extend(perf_model_issues(labels, perf_models, dedicated))
    issues.extend(undeclared_pair_issues(labels, perf_models, dedicated))
    return issues


@register(CHECK_TAG, Tags.database)
def check_role_groups_are_managed(app_configs=None, **kwargs):
    """Every group a role was written for is still explained by a ``Role`` row.

    The name of a role group carries no meaning and nothing looks a role up by
    it (#732), which is why ``accounts.models.roles.is_role_group_name`` is
    asked only about the slugs the catalogue knows: a hand-made group whose
    name happens to contain a colon is not a role group and is not reported.

    Args:
        app_configs: the apps to inspect. The check answers for the role system
            of this app, so a scoped command which does not name ``accounts``
            hears nothing about its groups.
        **kwargs: the keyword arguments of the check framework. The check
            answers without a message when ``databases`` names no connection
            to read: a deployment which was not migrated yet holds no groups,
            and ``migrate`` is the command writing them.

    Returns:
        list: one ``accounts.E005`` per group which no role manages
    """
    if not kwargs.get("databases"):
        return []
    labels = inspected_labels(app_configs)
    if labels is not None and ROLE_APP_LABEL not in labels:
        return []

    from django.contrib.auth.models import Group

    from accounts.models.roles import (ROLE_GROUP_SEPARATOR, RoleDefinition,
                                       is_role_group_name)

    # an organization IS a group, and the group of a retired role is still the
    # group of a role: both are explained, so neither is a candidate
    candidates = (Group.objects
                  .exclude(role__isnull=False)
                  .exclude(organization__isnull=False)
                  .filter(name__contains=ROLE_GROUP_SEPARATOR)
                  .order_by("name"))
    slugs = sorted(RoleDefinition.objects.values_list("slug", flat=True))

    issues = []
    for group in candidates:
        slug = next(
            (known for known in slugs
             if is_role_group_name(group.name, known)),
            None)
        if slug is None:
            continue
        issues.append(Error(
            f"The group {group.name!r} carries the name of the "
            f"{slug!r} role, but no Role row manages it.",
            hint="The group is what enforces a role, and it outlives the Role "
                 "row which was written for it: whatever deleted that row - a "
                 "deleted role, or a deleted organization taking its roles "
                 "with it - leaves a group behind which still grants "
                 "everything it was granted. Give the group its Role or "
                 "delete the group; silence accounts.E005 only for a "
                 "deployment which has inspected every one of its groups.",
            obj=group,
            id="accounts.E005"))
    return issues
