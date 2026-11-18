"""Domain steps of the registry shares and the publishing acceptance (#740).

Two vocabularies, one line apart: a *share* writes guardian object grants
onto the group of a role (``…/wms/{id}/share``), an *acceptance* is the
``PublishRequest`` decision that makes one organization's publisher role
publish for another. Both are DB state, so the scenarios pair the generic
request steps with the setup and assertions here - ``manual_updates.py``
is the template for that pattern.

The When steps send through ``context.client`` themselves because their
payload names organization and role by primary key: a scenario says which
role and which actions, and no fixture row can carry the ids of rows a
``Given`` step created. ``context.response`` is left exactly as the generic
send steps leave it, so the generic status and json assertions keep
working.

Holding a role is NOT a step of this module: ``roles.py`` of #736 already
answers ``the user "{username}" holds the role "{slug}" of the organization
"{org}"`` and its assertions - reuse over invention.
"""
import json

from behave import given, then, when
from django.contrib.auth import get_user_model

from accounts.models.guardian import OrganizationGroupObjectPermission
from accounts.models.groups import Organization, PublishRequest
from accounts.models.roles import Role
from registry.models.guardian import (WebFeatureServiceGroupObjectPermission,
                                      WebMapServiceGroupObjectPermission)
from registry.models.service import WebFeatureService, WebMapService

JSONAPI = "application/vnd.api+json"

#: the fixture services whose fields an added service copies; the ids are the
#: first rows of ``test_wms.json`` and ``test_wfs.json``
WMS_TEMPLATE = "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"
WFS_TEMPLATE = "9cc4889d-0cd4-4c3b-8975-58de6d30db41"

#: kind word in a scenario step -> (model, guardian table, url segment)
SERVICE_KINDS = {
    "web map service": (WebMapService, WebMapServiceGroupObjectPermission,
                        "wms"),
    "web feature service": (WebFeatureService,
                            WebFeatureServiceGroupObjectPermission, "wfs"),
}


def _service(kind, title):
    model = SERVICE_KINDS[kind][0]
    return model.objects.get(title=title)


def _share_url(kind, service):
    # the registry router registers with trailing_slash=False; every green
    # feature addresses its actions without one (cf. …/preview)
    return f"/api/registry/{SERVICE_KINDS[kind][2]}/{service.pk}/share"


def _send(context, method, url, payload=None):
    """Send one JSON:API request the way the generic send steps do.

    The Accept header of the harness (#734 "the suite is green") is set
    here too: without it a refusal answers the browsable API renderer and
    the json assertions have nothing to read.
    """
    kwargs = {"HTTP_ACCEPT": JSONAPI}
    if payload is not None:
        context.response = context.client.post(
            url, data=json.dumps(payload), content_type=JSONAPI, **kwargs)
    elif method == "get":
        context.response = context.client.get(url, **kwargs)
    elif method == "delete":
        context.response = context.client.delete(url, **kwargs)


@given('the organization "{name}" exists')
def an_organization(context, name):
    Organization.objects.get_or_create(name=name)


@given('the organization "{org_name}" owns a {kind} "{title}"')
def owned_service(context, org_name, kind, title):
    """A registered service with a known owner.

    Created once per feature and reused: a fixture is not restored between
    scenarios, so the step that adds a row must be idempotent the way
    ``manual_updates.py`` deletes what it configures.
    """
    organization, _ = Organization.objects.get_or_create(name=org_name)
    model = SERVICE_KINDS[kind][0]
    template = model.objects.get(
        pk=WMS_TEMPLATE if kind == "web map service" else WFS_TEMPLATE)
    service, created = model.objects.get_or_create(
        title=title,
        defaults={
            "service_url": "https://www.example.com/share/steps",
            "version": template.version,
            "origin": template.origin,
            "metadata_contact": template.metadata_contact,
            "service_contact": template.service_contact,
            "owner": organization,
        })
    if not created and service.owner_id != organization.pk:
        service.owner = organization
        service.save()


@when('I share the {kind} "{title}" with the role "{slug}" of the '
      'organization "{org_name}" for the actions "{actions}"')
def share_service(context, kind, title, slug, org_name, actions):
    organization = Organization.objects.get(name=org_name)
    service = _service(kind, title)
    _send(context, "post", _share_url(kind, service), {
        "data": {
            "type": service.__class__.__name__,
            "attributes": {
                "organization": organization.pk,
                "role": slug,
                "actions": [part.strip() for part in actions.split(",")],
            },
        },
    })


@when('I list the shares of the {kind} "{title}"')
def list_shares(context, kind, title):
    _send(context, "get", _share_url(kind, _service(kind, title)))


@when('I fetch the {kind} "{title}"')
def fetch_service(context, kind, title):
    """The detail endpoint of the service itself.

    What the share promises to the granted role: its member reaches the
    resource through the read endpoint. The blindness of a caller without
    any grant is asserted on the share listing, not here - the detail
    endpoint's read gate is still the rollout of #739 and answers the
    object today.
    """
    service = _service(kind, title)
    segment = SERVICE_KINDS[kind][2]
    _send(context, "get", f"/api/registry/{segment}/{service.pk}")


@when('I revoke the share of action "{action}" of the {kind} "{title}"')
def revoke_share(context, action, kind, title):
    """Revoke exactly the answered grant id of one action.

    The id encodes the through-table kind (``group-<pk>``); looking it up
    from the list answer is what pins that DELETE addresses a share by the
    id GET answered, not by a constructed one.
    """
    service = _service(kind, title)
    url = _share_url(kind, service)
    _send(context, "get", url)
    grants = context.response.json()["grants"]
    grant = [g for g in grants if g["action"] == action]
    assert grant, f"the list answered no share of action {action}"
    _send(context, "delete", f"{url}/{grant[0]['id']}")


@when('the publish request from "{from_name}" to "{to_name}" is accepted')
def accept_publish_request(context, from_name, to_name):
    requesting, _ = Organization.objects.get_or_create(name=from_name)
    requested, _ = Organization.objects.get_or_create(name=to_name)
    request = PublishRequest.objects.filter(
        from_organization=requesting, to_organization=requested).first()
    if request is None:
        request = PublishRequest.objects.create(
            from_organization=requesting, to_organization=requested)
    request.accept()


@given('the user "{username}" exists')
def a_user(context, username):
    """A scenario user with the fixture convention: password is the name."""
    user_model = get_user_model()
    user, created = user_model.objects.get_or_create(username=username)
    if created:
        user.set_password(username)
        user.save()


@then('the publish request from "{from_name}" to "{to_name}" is gone')
def publish_request_gone(context, from_name, to_name):
    assert not PublishRequest.objects.filter(
        from_organization__name=from_name,
        to_organization__name=to_name).exists()


# --------------------------------------------------------------- assertions

@then('the grant list answers the actions "{actions}"')
@then('the grant list answers no actions')
def grant_list_actions(context, actions=None):
    """The share listing answers exactly these actions.

    ``no actions`` is its own wording because parse's default type needs at
    least one character - an empty quoted list would match no step at all.
    """
    expected = sorted(part for part in
                      (value.strip() for value in
                       (actions or '').split(",")) if part)
    answered = sorted(grant["action"]
                      for grant in context.response.json()["grants"])
    assert answered == expected, f"answered {answered}, expected {expected}"


@then('the role "{slug}" of the organization "{org_name}" holds '
      '"{codename}" over the {kind} "{title}"')
def role_holds_grant(context, slug, org_name, codename, kind, title):
    """The decided row exists - and names its decider if one was given

    A share names the person; the publisher grants of an acceptance through
    ``save()`` and the creation bootstrap are mechanical rows. Both are
    grants, only the listing in the API separates them.
    """
    organization = Organization.objects.get(name=org_name)
    role = Role.objects.for_org(organization).with_definition(slug).get()
    table = SERVICE_KINDS[kind][1]
    assert table.objects.filter(
        content_object=_service(kind, title), group=role.group,
        permission__codename=codename).exists(), (
            f"{role.group.name} does not hold {codename} over {title}")


@then('the role "{slug}" of the organization "{org_name}" does not hold '
      '"{codename}" over the {kind} "{title}"')
def role_lacks_grant(context, slug, org_name, codename, kind, title):
    organization = Organization.objects.get(name=org_name)
    role = Role.objects.for_org(organization).with_definition(slug).get()
    table = SERVICE_KINDS[kind][1]
    assert not table.objects.filter(
        content_object=_service(kind, title), group=role.group,
        permission__codename=codename).exists()


@then('the organization "{org_name}" answers "{publisher_name}" among its '
      'publishers')
def publishers_answer(context, org_name, publisher_name):
    organization = Organization.objects.get(name=org_name)
    publisher = Organization.objects.get(name=publisher_name)
    assert publisher in organization.publishers


@then('the organization "{org_name}" does not answer "{other_name}" among '
      'its publishers')
def publishers_absent(context, org_name, other_name):
    organization = Organization.objects.get(name=org_name)
    other = Organization.objects.get(name=other_name)
    assert other not in organization.publishers


@then('the organization "{org_name}" holds the publish grant over '
      '"{target_name}" through its "{slug}" role')
def publish_grant_through_role(context, org_name, target_name, slug):
    """The organization-level statement of the acceptance, role-scoped

    The grant sits on the TARGET and is held by the role group - leaving
    the role revokes it, which the old whole-organization grant could not.
    """
    organization = Organization.objects.get(name=org_name)
    role = Role.objects.for_org(organization).with_definition(slug).get()
    target = Organization.objects.get(name=target_name)
    assert OrganizationGroupObjectPermission.objects.filter(
        content_object=target, group=role.group,
        permission__codename="can_publish_for_organization").exists()
