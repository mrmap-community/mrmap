"""Domain steps of the role API of #736.

The scenarios of ``features/json:api/auth/*role*.feature`` and
``*membership*.feature`` say what an organization administrator does: they
create an organization (whose bootstrap of #732 writes the role rows, exactly
like a running instance), aim at one of its endpoints and assert the rows
after the response. The rows a scenario creates are unique to it — a new
organization per scenario — because behave loads fixtures once per feature
and never restores them, so scenarios must not share mutable state.
"""
import json

from behave import given, then
from django.contrib.auth import get_user_model

from accounts.models.groups import Organization
from accounts.models.roles import Role

API = "http://localhost:8000/api/accounts"


def _loginable(username):
    """The account as the login step expects it: password equals username"""
    user, _ = get_user_model().objects.get_or_create(username=username)
    user.set_password(username)
    user.save()
    return user


def _organization(name):
    return Organization.objects.get(name=name)


def _role(org_name, slug):
    # not through ``with_definition``: that answers active roles only, while
    # the steps here have to reach the retired row of the retired scenario
    return Role.objects.for_org(_organization(org_name)).get(
        role_definition__slug=slug)


@given('an organization "{name}" with an administrator "{admin}" and a '
       'member "{member}"')
def create_organization_with_people(context, name, admin, member):
    """A fresh organization, its administrator holding the bootstrap's
    ``organization_admin`` role, its member a plain member of the group."""
    organization = Organization.objects.create(name=name)
    admin_role = Role.objects.for_org(
        organization).with_definition("organization_admin").get()
    admin_role.add_member(_loginable(admin))
    _loginable(member).groups.add(organization)


@given('the role "{slug}" of the organization "{org}" is retired')
def retire_role(context, slug, org):
    # the write of #741: an inactive role grants through its group until the
    # task deletes it, but takes no new membership on the API
    Role.objects.filter(pk=_role(org, slug).pk).update(is_active=False)


@given('I target the memberships of the role "{slug}" of the organization '
       '"{org}"')
def target_role_memberships(context, slug, org):
    context.endpoint = "%s/roles/%s/memberships" % (API, _role(org, slug).pk)


@given('I target the membership of the user "{username}" in the role '
       '"{slug}" of the organization "{org}"')
def target_membership_detail(context, username, slug, org):
    membership = _role(org, slug).memberships.get(user__username=username)
    context.endpoint = "%s/memberships/%s" % (API, membership.pk)


@given('I target the roles of the organization "{org}"')
def target_organization_roles(context, org):
    context.endpoint = "%s/organizations/%s/roles" % (
        API, _organization(org).pk)


@given('I target the members of the organization "{org}"')
def target_organization_members(context, org):
    context.endpoint = "%s/organizations/%s/members" % (
        API, _organization(org).pk)


@given('I set the payload to assign the user "{username}" to the role '
       '"{slug}" of the organization "{org}"')
def payload_assign_user(context, username, slug, org):
    role = _role(org, slug)
    user = get_user_model().objects.get(username=username)
    context.payload = json.dumps({
        "data": {
            "type": "RoleMembership",
            "relationships": {
                "role": {"data": {"type": "Role", "id": str(role.pk)}},
                "user": {"data": {"type": "User", "id": str(user.pk)}}}}})


@given('I set the payload to add the user "{username}"')
def payload_add_member(context, username):
    user = get_user_model().objects.get(username=username)
    # adding a member links two existing rows: the document is the resource
    # identifier whose "id" names the user to add
    context.payload = json.dumps(
        {"data": {"type": "User", "id": str(user.pk)}})


@given('the user "{username}" holds the role "{slug}" of the organization '
       '"{org}"')
def grant_role(context, username, slug, org):
    _role(org, slug).add_member(
        get_user_model().objects.get(username=username))


@then('the user "{username}" holds the role "{slug}" of the organization '
      '"{org}"')
def assert_holds_role(context, username, slug, org):
    # the membership row and the group behind it are one state: holding the
    # role *is* membership of the role's group, which is what the promise of
    # the API is about either way
    assert _role(org, slug).memberships.filter(
        user__username=username).exists(), (
        "%s does not hold %s of %s" % (username, slug, org))


@then('the user "{username}" does not hold the role "{slug}" of the '
      'organization "{org}"')
def assert_does_not_hold_role(context, username, slug, org):
    assert not _role(org, slug).memberships.filter(
        user__username=username).exists(), (
        "%s unexpectedly holds %s of %s" % (username, slug, org))


@then('the user "{username}" is a member of the organization "{org}"')
def assert_is_member(context, username, org):
    assert get_user_model().objects.get(
        username=username).groups.filter(
            pk=_organization(org).pk).exists(), (
        "%s is not a member of %s" % (username, org))


@then('the user "{username}" is not a member of the organization "{org}"')
def assert_is_not_member(context, username, org):
    assert not get_user_model().objects.get(
        username=username).groups.filter(
            pk=_organization(org).pk).exists(), (
        "%s is unexpectedly a member of %s" % (username, org))
