# Permissions

MrMap answers two different questions about access, and the answer to one says nothing about
the other. They are implemented separately, configured separately and read by different parts
of the code. An administrator has to set both, and an implementer has to keep them apart.

| axis | the question it answers | what answers it |
| --- | --- | --- |
| **Registry axis** | which user or group may read, register, change or delete a **registered object** — a service, a map context, an organization, a background process — through the API | django-guardian object permissions, asked by DRF permission classes on each viewset |
| **Proxy axis** | which OGC client may call which **operation** on which **layer or feature type** of a secured service, optionally only inside an area | one configuration row per rule: `AllowedWebMapServiceOperation` / `AllowedWebFeatureServiceOperation`, together with `ProxySetting` for the proxy behaviour |

The proxy axis is **consumption control**. It decides what an OGC client may ask a mapped
service for. It is not related to who may edit that resource in the registry: holding a rule
on the proxy axis grants no write access to the resource, and the permission to edit a
resource grants nothing at all when its service is secured. The single point where the two
touch is a side effect: saving an allowed operation forces `ProxySetting.camouflage` to
`True` for its service, because MrMap must answer the client itself to be able to restrict
it. See [Security Proxy](../design/architecture.md#security-proxy) for the proxy in the domain
overview.

Both axes are about **users, groups and objects**. Neither has roles today, which is what
[epic #727](https://github.com/mrmap-community/mrmap/issues/727) sets out to change; see
[Roles and memberships](#roles-and-memberships).

## The registry axis

Object permissions come from [django-guardian](https://django-guardian.readthedocs.io/)
(`django-guardian==3.5.2`, `backend/.requirements/base.txt`). Guardian stores a permission
row per (user or group, object) pair next to Django's own model permissions, so a grant can
name one service instead of all services of that type.

### Settings

`backend/MrMap/settings.py`:

- `AUTHENTICATION_BACKENDS` — `django.contrib.auth.backends.ModelBackend` plus
  `guardian.backends.ObjectPermissionBackend`. The backend is what makes
  `user.has_perm("registry.change_webmapservice", service)` answer for grants on one object.
- `GUARDIAN_RAISE_403 = True` — where guardian's own view helpers deny something
  (`guardian.utils.get_40x_or_None`, behind guardian's view decorators and mixins), the
  denial is raised as `PermissionDenied` and runs through Django's exception handling
  instead of being answered by guardian as a bare 403 response. It may not be combined with
  `GUARDIAN_RENDER_403`. No MrMap view uses those helpers today — the API's 403 answers come
  from the DRF classes below — so this setting currently changes nothing on a MrMap request.
  It is kept as the deployment's stated preference for 403 handling.
- `DEFAULT_PERMISSION_CLASSES` — `rest_framework.permissions.IsAuthenticatedOrReadOnly`,
  the **floor** of the API since #1444. It is what a view falls back to when it names no
  permission class of its own: reading stays open, a write needs an identity. Nothing about
  it reaches a viewset which already names a class, and it asks an *identity*, not a grant —
  the guardian classes below are still what decides who may write. Before it, DRF's empty
  default answered every permission question with "allowed", so the endpoints naming none —
  the metadata lookups, the historical endpoints, the groups and organizations, the periodic
  schedules and the authentication records of a service — were writable by an anonymous
  client. When adding an endpoint, name the class you need: the floor is a fallback, not a
  decision.

One view names no permission class on purpose: the security proxy
(`OgcServiceProxyView` in `backend/registry/proxy/mixins.py`, and with it both concrete
proxies and the single-resource capabilities endpoints). The XML POST binding of WMS and WFS
carries a `GetMap` or a `GetFeature` — both reads — over HTTP POST, so a rule keyed on the
HTTP verb would refuse the anonymous map client those bindings are specified for. What the
proxy answers is decided on the [proxy axis](#the-proxy-axis), and a refusal there travels as
an OGC exception report rather than as a JSON:API error.

### What a request is asked

Three classes carry the registry axis; all of them are used per viewset, and the floor above
is what a viewset naming none of them falls back to.

- `rest_framework.permissions.DjangoObjectPermissions` — DRF's own class. Used where even
  reading needs an identity: the four proxy-configuration endpoints of
  `backend/registry/views/security.py` (for `AllowedWebMapServiceOperation`,
  `AllowedWebFeatureServiceOperation`, `WebMapServiceProxySetting` and
  `WebFeatureServiceProxySetting`, each carried by the mixin its nested endpoint shares),
  the users endpoint (`backend/accounts/views/users.py`) and the groups and organizations
  endpoints (`backend/accounts/views/groups.py`, #1448). Those two answered an anonymous
  `PATCH` of their members relation until then, which handed out whatever the granted role
  group may do; the members of a group are written by `POST /organizations/{id}/members`
  (#736), which asks the organization the group belongs to, and the relation of the group
  serializer is read-only since then.
- `extras.permissions.DjangoObjectPermissionsOrAnonReadOnly` (`backend/extras/permissions.py`)
  — the same class with `authenticated_users_only = False`. This is the majority of the API,
  including the resource endpoints of `backend/registry/views/service.py`.
- `notify.permissions.CanChangeRelatedResource`
  (`backend/notify/permissions.py`) — the background-process endpoint. A process is only the
  report of work done on another resource, so reading is open and aborting it is decided by
  the `change_` permission of the resource the process names. A process which names no
  resource (a registration learns its service while it runs) falls back to the global
  `notify.change_backgroundprocess`. `notify.permissions.CanRetryRegistrationReference`
  composes this class with the read-only class for the retry of a registration work row
  (#1265).

What the guardian classes actually ask, given DRF 3.18's `perms_map`
(`rest_framework.permissions.DjangoModelPermissions`):

- **Reads** (`GET`, `HEAD`, `OPTIONS`) map to *no* permission at all. They are gated only by
  whether the class allows an anonymous user. A read is therefore never refused because of a
  missing grant — see [What the API answers](#what-the-api-answers-about-permissions) for
  where the view grants do matter.
- **Writes** are asked twice. `has_permission` requires the **global model permission** —
  `add_`, `change_` or `delete_` of the model — and `check_object_permissions` then requires
  the **same codename as an object permission** on the concrete object. A user needs both, so
  a group which only ever got object grants cannot write a collection endpoint. A denial
  answers 403 with the message of the class; it does not answer 404, because the read part of
  `perms_map` is empty and DRF's "no read permission means 404" branch cannot trigger.

### Where the grants live

Guardian keeps every object grant of every model in one pair of generic tables, naming the
object by content type and the **text** of its primary key. A lookup for a model whose
primary key is a UUID compares that text column by casting it to a UUID, and whether the
query plan evaluates the cast only for the rows of the looked-up model is its own decision:
one row of a model with an integer primary key can make the lookup of a service fail with
`invalid input syntax for type uuid`. Models which guardian's
[performance guide](https://django-guardian.readthedocs.io/en/stable/userguide/performance/#direct-foreign-keys)
calls direct-foreign-key models have a table of their own here, and every model MrMap grants
something on has one:

- `backend/registry/models/guardian.py` — `WebMapService`, `WebFeatureService` and
  `CatalogueService`, plus `MapContext`, `MapContextLayer` and
  `WebMapServiceMonitoringSetting`. The last three have their tables before any code grants
  on them, because the fixtures of this repository write grants that name their integer
  primary keys in the shared table.
- `backend/accounts/models/guardian.py` — `Organization` and `Group`, which the permission
  bootstrap below grants on.

That set is declared as data since #735, and a system check reads it back:

- `GUARDIAN_PERF_MODELS` in `backend/accounts/settings.py` — the models which answer from
  tables of their own, i.e. exactly the eight named above. An entry whose pair of
  through-models was never written is `accounts.E004`; a pair written beside the list is
  `accounts.W001`.
- `ROLE_MANAGED_MODELS` in the same file — the models which are *resources*: they store their
  owning organization (the `owner` column of #733), and the bootstrap below grants a new
  instance to the roles of that organization. Today: `registry.WebMapService` and
  `registry.WebFeatureService`. `registry.CatalogueService` has its owner and its tables and
  is deliberately not listed, because no definition of the role catalogue holds
  `change_catalogueservice` — so today no role would be granted a new harvested record. It
  joins the list together with the definition which manages it.

Models nothing grants on answer from the generic tables until the role work needs a table of
their own.

### What the two settings promise

A list is only honest while something reads it back, and the single `SECURED_MODELS` list is
the lesson: a model could join it while nobody noticed that its through-models were missing,
because guardian answers a model without its own tables *successfully* — only slowly, and
with query counts which the assertions of `tests/django/registry/tests_query_performance.py`
no longer describe. Nothing failed, so nothing was fixed. `backend/accounts/checks.py` is the
guard, and it runs with every run of Django's check framework: at the startup of the test
runner, of `migrate` and of `runserver`.

| message | what it reports |
| --- | --- |
| `accounts.E001` | an entry of `ROLE_MANAGED_MODELS` names no model |
| `accounts.E002` | a role-managed model has no dedicated through-models, or `GUARDIAN_PERF_MODELS` does not carry it |
| `accounts.E003` | a role-managed model has no `owner` foreign key to `accounts.Organization`, so its grants would go to nobody |
| `accounts.E004` | an entry of `GUARDIAN_PERF_MODELS` names no model, or names one without the pair the list claims |
| `accounts.E005` | a group carries the name of a role group while no `Role` row manages it: the group still grants everything it was granted, and nothing explains it |
| `accounts.W001` | a pair of through-models exists which `GUARDIAN_PERF_MODELS` does not declare |

`E005` is the only message which reads the database; it stays silent for a command which
allows no connection, because a `migrate` on a fresh deployment has no groups to explain. The
others answer from the model declarations, so they answer before a deployment has tables.
`manage.py check -t accounts` runs these checks and nothing else, a command scoped to an app
(`manage.py check registry`) answers for the models of that app as every check of Django's own
apps does, and `SILENCED_SYSTEM_CHECKS` is the escape hatch for a message an operator has
inspected.

What declaring one more role-managed model costs:

- nothing in the role model. No new role-group naming scheme and no data migration for the
  organizations which already exist: the roles of an organization come from the catalogue of
  #731, not from the list of models. That is the retirement of the per-model groups of the old
  bootstrap (#727), and `tests/django/accounts/test_permission_bootstrap.py` keeps it.
- the equipment of the model, where it is not equipped yet: the `owner` foreign key with its
  migration, the pair of through-models with its migration, and a role definition holding
  `change_<model>` — without that the bootstrap finds no role to grant to. `accounts.E002`
  and `accounts.E003` are what refuse a model declared ahead of its equipment, which is the
  one thing that keeps the list from rotting the way `SECURED_MODELS` did.

### What creation grants today

The bootstrap is `backend/accounts/signals.py`. It is the only code which grants anything on
behalf of a user, and since #732 it answers *who administers what* by role rather than by a
group name built from the organization.

When an `Organization` is created, `handle_organization_creation` creates one `Role` per role
definition of `ORGANIZATION` scope (#731, #732) — a managed group each, named
`"<Organization name>: <slug>"` for reading only — and writes onto two of them the object
grants which the old bootstrap wrote onto `<Org> Administrators` and `<Org> Members`:

- the role of the default definition (`viewer` today) gets `view_organization` and
  `can_publish_for_organization` on the organization;
- the role of `organization_admin` gets `view_organization` and `change_organization` on it.

The group count of an organization therefore follows the catalogue and not the list of
models. The per-model `<Org> <model> Admins` groups of the old bootstrap are gone, and #732
retired the ones an instance already had as inactive roles, which is the work list #741
deletes.

When an instance of a role-managed model is created — a model of `ROLE_MANAGED_MODELS`, today
`registry.WebMapService` and `registry.WebFeatureService` — `handle_role_managed_model_creation`
looks up its owning organization (the `owner` column #733 stores), asks
`RoleQuerySet.managing` which roles of that organization hold `change_<model>` in their
definition, and assigns `view_`, `change_` and `delete_` on the instance to their groups. It
hands no *global* permission to a group: the right to register belongs to the role definition,
which is decision Q5 of #727. A resource which knows no owner, and an organization without a
managing role, are granted to nobody and say so once in the log — a `post_save` receiver must
not raise, or it would break the registration it is there to protect.

A receiver which grants anything takes `raw` in its signature and returns when a fixture is
being loaded — a `loaddata` emits `post_save` too, and creating the groups a second time
per dumped organization collides on the unique group name (#864). `tests/django/accounts/`
guards that rule.

### Publishing rights

An organization can be granted the right to publish for another one. The permission is
declared on the model (`Organization.Meta.permissions` in `backend/accounts/models/groups.py`)
and stored as the object grant `accounts.can_publish_for_organization` on the organization
which is published *for*, held by the other organization's group.

- `Organization.add_publisher` writes the grant, `remove_publisher` takes it away, and
  `Organization.can_publish_for` reads the question back for one organization.
- `PublishRequest` is the request workflow: a request from one organization to another,
  whose acceptance calls `add_publisher`. Both the direction it writes and the fact that
  accepting deletes the request instead of persisting `is_accepted` are pinned by
  `backend/tests/django/accounts/test_publishing_rights.py`; that file names the corrections
  as the work of #740, which rewrites this to role-scoped grants.

Note what the grant does *not* do: nothing in `backend/registry/` consults it when a resource
is registered. It is a stored relation and a request workflow, not yet a gate on registration.

### What the API answers about permissions

Because reads need no grant, the API does not hide objects which the requesting user may not
see: the resource endpoints of `backend/registry/views/service.py` query
`WebMapService.objects.all()` and their peers, and guardian is not in that filter. Where reads
*are* scoped, the code says so explicitly:

- `registry/querys/alerts.py` and `notify/managers.py` narrow services and background
  activity with `get_objects_for_user` before counting or listing them;
- the organizations endpoint narrows with `filter[user_has_perm]`
  (`accounts/filters/groups.py`), which uses `accept_global_perms=False` and so ignores a
  global permission.

The two resources which answer *people* are the documented exception, because a row of them is
a person and not a service: `GET /api/accounts/users` and `GET /api/accounts/groups` answer an
authenticated caller only the accounts and the groups of the organizations it belongs to or
administers, and of those accounts only what a picker needs (`username`,
`stringRepresentation`). `email`, `isStaff`, `isSuperuser`, `lastLogin`, `dateJoined`,
`settings` and the confirmation flags travel with `accounts.view_user`, and the members of a
group with `auth.view_group` — the catalogue of #727 decides both, and it names
`accounts.view_user` for `platform_admin` and `support` and `auth.view_group` for nobody out of
the box. See `backend/accounts/permissions.py` for the rule and
`backend/tests/django/accounts/test_account_read_scope.py` for its answers.

The per-user view of a single object travels in the payload instead:
`extras.serializers.ObjectPermissionCheckerSerializer` answers `allowedActions`, the actions
the requesting user may take on that object as one answer of the permission facade
(`view`, `change`, `delete` and the capabilities the app declares), replacing the retired
`is_accessible` hint (#738). The checker is built
once per request by `extras.viewsets.ObjectPermissionCheckerViewSetMixin`
(`backend/extras/viewsets.py`) and prefetched for exactly the objects the answer shows — the
page of a list action, the one object of a detail action — which the mixin remembers in
`paginate_queryset` and `get_object`. A serializer which finds no checker in its context
builds one per object and logs "slow handling of object permissions detected"; that warning
means an endpoint is missing the mixin, not that permissions are broken.

## Who may view a resource (visibility)

Every read of a WMS or WFS answers `visibility` with one of three words, derived
from the guardian grants of the resource and never stored as a column, so the
list, the detail route and the permission checks cannot disagree about one and
the same resource (#727 called the disagreement the bug):

- **public** — the `view_<model>` grant over the resource is held by the
  *anonymous viewer* role group: a PLATFORM-scope, non-assignable role which
  migration `0009_the_anonymous_viewer_role_group_is_seeded` writes and the
  `post_migrate` guard of `accounts/apps.py` keeps; guardian's anonymous user
  row is its only member and nothing ever joins it. Publishing is the only
  code path that grants onto it — decision Q2 of #727: public is an explicit
  grant, never a side effect. A public resource is public for logged-in users
  too: the facade answers the anonymous group's view grant for every caller
  (`authorized_public_object_grant` in `backend/extras/permissions.py`),
  because a logged-in user who saw *less* than an anonymous one would rebuild
  the split on a new axis.
- **organization-internal** — a role group of the resource's owning
  organization holds the view grant. This is the state every newly registered
  resource starts in: the creation bootstrap grants the managing roles of the
  owner ([What creation grants today](#what-creation-grants-today)) and never
  the anonymous group.
- **restricted** — neither: shared with individually named groups or users
  (#740's sharing surface) or with nobody. A resource which lost its owner
  lost its internal scope with it.

The answer travels in the `visibility` attribute of the WMS and WFS serializers
(`registry/serializers/service.py`, mixin `VisibilitySerializerMixin`); on a
list it is one `CASE` over two `EXISTS` in the page's own SELECT
(`registry/expressions/visibility.py`) — no query per row, none per role.

A `PATCH` may move a resource across the public axis only:

- `"visibility": "public"` needs `registry.publish_resource` over the resource
  — held through the `resource_publisher` role of the owning organization;
- `"visibility": "organization-internal"` takes the grant back and needs that
  same permission, or `manage_access_rules`;
- `"restricted"` is refused (400): it is the shape of the *absence* of grants,
  and shaping it deliberately is #740, not this endpoint.

### The rollout switch

Whether a *list* is narrowed to what the caller may view is a deployment
decision per model:

```
MRMAP_PERMISSION_FILTERED_LIST_MODELS=registry.WebMapService,registry.WebFeatureService
```

- **empty (the default)**: lists answer what they always answered — every
  row — while `visibility` is shown everywhere. Nothing published before the
  switch is affected and no anonymous access widens by itself.
- **a model named**: the list, the detail route and the pagination count of
  that model answer the same `objects_for_user` SQL which decides the detail
  endpoint (#734) — one statement over guardian's tables, not a query per
  role.
- The system check `accounts.E006` refuses naming a model which is not
  role-managed (`ROLE_MANAGED_MODELS`), because without the owner axis the
  SQL filter would drop the organization-internal rows it exists to keep.
- Rollback is the empty value: the annotation stays, the filtering leaves.

## The proxy axis

This axis answers one question: may this OGC client call this operation on this layer? It is
configured per secured service in `backend/registry/models/security.py` and enforced in
`backend/registry/proxy/`.

### A rule: AllowedOperation

`AllowedOperation` is an abstract base; one row is one rule and allows

- a set of groups (`allowed_groups`, a `ManyToManyField` to `django.contrib.auth.models.Group`;
  **empty means everybody, including anonymous**),
- to call a set of operations (`operations`, on `WebMapServiceOperation` or
  `WebFeatureServiceOperation` — both are `ChoiceModel`s listing the OGC operation names),
- on the layers or feature types of one service (`secured_layers` on an
  `AllowedWebMapServiceOperation`, `secured_feature_types` on an
  `AllowedWebFeatureServiceOperation`, with `secured_service` naming the service),
- and optionally only inside an area (`allowed_area`, a `MultiPolygonField` with a
  `geometry_is_empty` validator, so a stored area is never an empty geometry).

`description` is a free-text label for administration. The two concrete classes are
`AllowedWebMapServiceOperation` and `AllowedWebFeatureServiceOperation`.

`allowed_area` is a restriction, not a grant. When every rule of a service carries an area,
the service is *spatially secured* (`is_spatial_secured`) and a request outside the area is
not answered. If two rules match the same operations and groups and one of them has
`allowed_area = None`, the unrestricted one allows every area — the warning in the model's
docstring is the rule, not an edge case. For a WFS `GetFeature`, the applicable areas are
unioned per feature type (`allowed_area_union` in `registry/managers/security.py`) rather
than intersected with the request.

### The proxy behaviour: ProxySetting

`ProxySetting` is the second abstract model in the same file, with one concrete row per
secured service: `WebMapServiceProxySetting` and `WebFeatureServiceProxySetting`.

- `camouflage` — replace the host names and addresses in the service's documents by this
  MrMap's own host name, so a client cannot walk past the proxy to the origin service.
  Without camouflage a restriction is decoration: the capabilities document still points at
  the origin.
- `log_response` — log the responses of the service for the usage analysis
  (`registry/tasks/security.py` counts what was answered).

A `CheckConstraint` forbids `log_response` without `camouflage`, and `ProxySetting.clean`
refuses to switch camouflage off while allowed operations exist for that service. Saving an
`AllowedOperation` sets `camouflage = True` on its service's setting — creating a rule is
what switches the service over to the proxy.

### The client, and where the request enters

Secured services are read through the proxy URLs of `backend/MrMap/urls.py`:

- `/mrmap-proxy/wms/<uuid:pk>` and `/mrmap-proxy/wfs/<uuid:pk>` for the service,
- `/mrmap-proxy/wms/layer/<uuid:layer_pk>` and `/mrmap-proxy/wfs/featuretype/<uuid:featuretype_pk>`
  for the capabilities of a single layer or feature type.

The client's identity is the MrMap user of that HTTP request, authenticated exactly like an
API request (session, basic auth or a knox token — `DEFAULT_AUTHENTICATION_CLASSES`). The
floor of `DEFAULT_PERMISSION_CLASSES` asks nothing of it: the proxy names no permission class,
so a request is refused or answered by the rules below and never by the verb it used.
`AllowedOgcServiceOperationQuerySet.filter_by_request`
(`backend/registry/managers/security.py`) matches the rule against the **groups of that
user**; for an anonymous request it uses the groups of `AnonymousUser`. A client which must
not be able to read a layer therefore needs an account without a matching group — or no
account at all — and not a different URL.

Staff and superusers may ask the proxy as somebody else to debug a rule: `_test_as_user` as
a query or POST parameter, or the `X-TEST-AS-USER` header, handled by
`registry/proxy/mixins.py`. Any other user is refused with 403. The swap is visible instead
of silent: the answer carries `X-Test-As-User` and `X-Original-User` response headers, and
the response log records the original user with the request marked as a test. It is a
debugging instrument, not an access-control feature.

### The decision for one request

`OgcServiceProxyView.get_and_post` in `backend/registry/proxy/mixins.py` — the base of
`WebMapServiceProxy` and `WebFeatureServiceProxy` — decides in this order, and answers a
failure as an OGC exception report rather than as a bare HTTP error:

1. a missing `request` or `version` parameter → 400 (already in `initial`, before the
   service is looked up at all);
2. the service is not found → 404;
3. the service is deactivated → 423, including its capabilities: the metadata of a
   deactivated service stays unreadable;
4. a `GetCapabilities` request → the camouflaged capabilities document;
5. an operation which is not secureable → answered straight from the origin service. Only
   `GetMap` and `GetFeatureInfo` (WMS) and `GetFeature` and `Transaction` (WFS) are
   secureable (`SecureableWMSOperationEnum` and `SecureableWFSOperationEnum` in
   `registry/enums/service.py`, collected as `SECURE_ABLE_OPERATIONS_LOWER` in
   `backend/registry/settings.py`);
6. a service with no rule at all (`is_secured` false) → answered from the origin service;
7. a service with rules and at least one rule matching this user, operation and requested
   entity (`relevant_allowed_operations`) → the secured path, `secure_request()`, which
   clips the map to the allowed area or filters the features;
8. anything else → 403 `PermissionDenied`: the user is not entitled to this operation on the
   entities it asked for.

Note what step 7 needs: **all** requested entities must appear in the matched rule
(`filter_by_requested_entity`). Asking for one permitted layer together with one the client
may not have is a failure for the whole request, not a partial answer.

Both concrete proxies override `get_and_post` to add their own checks before this decision,
and `registry/proxy/resource_capabilities.py` overrides it again for the single-resource
capabilities endpoints. (The docstrings in `mixins.py` still call this class
`GenericOwsServiceOperationFacade`; no class carries that name, so grepping for it finds
comments and nothing else.)

## Roles and memberships

> Updated by #731-#739: the role system the text below describes as missing has
> since shipped — `RoleDefinition`, `Role` and `RoleMembership` in
> `backend/accounts/models/roles.py`, the builtin catalogue of
> `accounts/management/commands/sync_role_definitions.py`, the creation
> bootstrap of `accounts/signals.py` and the facade of `extras/permissions.py`.
> The groups named by string concatenation are gone; a role's group is found
> through its `Role` row (#732). Who may *view* a resource is told by
> [Who may view a resource](#who-may-view-a-resource-visibility). The rest of
> this section is kept as the baseline of what was missing and why.

There are none. No role model, no membership model, no role administration screen, and no
role is applied at creation beyond the groups the bootstrap names above. Who administers
what is currently derived from group **names** built by string concatenation
(`<Organization name> Administrators`, `<Organization name> <model> Admins`), which breaks
as soon as an organization is renamed or a name exceeds the 150-character limit of
`auth_group` — a limit the bootstrap marks with a FIXME.

Two consequences an implementer will run into:

- There is no way to ask *which users may change this service*: the answer is spread over
  guardian rows, group membership, and global model permissions, and the three are asked
  differently in different places (`accept_global_perms` is `False` in some calls and `True`
  in others, which is why the same question has two answers today).
- Grants on new resources silently do not happen, because no resource knows an owner
  ([What creation grants today](#what-creation-grants-today)).

[Issue #727](https://github.com/mrmap-community/mrmap/issues/727) is the epic which introduces
declarative roles, memberships and explainable permissions. #734 is the permission-resolution
facade and role-based grants at creation time, #735 the declared set of role-managed models
and their through-tables, #740 the rewrite of sharing and accepted publish requests into
role-scoped grants. Anything this page describes as missing belongs to that epic; nothing in
it is implemented and waiting.

## History

Earlier versions of this page described a custom role system built on an app which was
removed in #52 — its models, an entity-relationship diagram and a lemma about user sets —
and promised an *Organization administrator* and a *Resource administrator* role which the
code never implemented. The page described an intended design rather than the software, and
an implementer following it would have built an app that has not existed since 2021. The
text above describes the software. The role design that page was reaching for is the work of
#727, and the reason that epic's discussion kept restarting was that the repository had no
shared baseline to point at; this page is that baseline.

## Names this page uses

Every name above, with the file it comes from.

| name | file |
| --- | --- |
| `ObjectPermissionBackend`, `GUARDIAN_RAISE_403` | `backend/MrMap/settings.py` |
| `DEFAULT_PERMISSION_CLASSES` (the floor a view without a declared class falls back to) | `backend/MrMap/settings.py` |
| `DjangoObjectPermissionsOrAnonReadOnly` | `backend/extras/permissions.py` |
| `ObjectPermissionCheckerViewSetMixin` | `backend/extras/viewsets.py` |
| `ObjectPermissionCheckerSerializer` (`allowedActions`) | `backend/extras/serializers.py` |
| `CanChangeRelatedResource`, `CanRetryRegistrationReference` | `backend/notify/permissions.py` |
| one `UserObjectPermissionBase` / `GroupObjectPermissionBase` subclass per model with tables of its own, e.g. `WebMapServiceUserObjectPermission`, `MapContextLayerGroupObjectPermission` | `backend/registry/models/guardian.py` |
| `OrganizationUserObjectPermission`, `OrganizationGroupObjectPermission`, `GroupUserObjectPermission`, `GroupGroupObjectPermission` | `backend/accounts/models/guardian.py` |
| `ROLE_MANAGED_MODELS`, `GUARDIAN_PERF_MODELS` | `backend/accounts/settings.py` |
| the system check of the two settings (`check_role_managed_models`, `check_role_groups_are_managed`, `accounts.E001`–`accounts.E005`, `accounts.W001`) | `backend/accounts/checks.py` |
| permission bootstrap (`handle_organization_creation`, `handle_role_managed_model_creation`) | `backend/accounts/signals.py` |
| `Organization.can_publish_for`, `add_publisher`, `PublishRequest`, `can_publish_for_organization` | `backend/accounts/models/groups.py` |
| `get_objects_for_user` scoping of alerts | `backend/registry/querys/alerts.py` |
| `get_objects_for_user` scoping of background activity | `backend/notify/managers.py` |
| `filter[user_has_perm]` | `backend/accounts/filters/groups.py` |
| `Visibility`, `allowed`, `objects_for_user`, `set_public`, `authorized_public_object_grant` | `backend/extras/permissions.py` |
| the `anonymous_viewer` slug and the platform group prefix | `backend/accounts/models/roles.py` |
| the seed of the anonymous viewer's role group and member | `backend/accounts/migrations/0009_the_anonymous_viewer_role_group_is_seeded.py`, guarded by `accounts/apps.py` and `accounts.utils.ensure_anonymous_viewer` |
| `visibility_expression`, `anonymous_viewer_group_ids` | `backend/registry/expressions/visibility.py` |
| `PermissionVisibilityMixin` | `backend/extras/viewsets.py` |
| `VisibilitySerializerMixin`, `VisibilityField` | `backend/registry/serializers/service.py` |
| `PERMISSION_FILTERED_LIST_MODELS` (`MRMAP_PERMISSION_FILTERED_LIST_MODELS`) and the check `accounts.E006` | `backend/MrMap/settings.py`, `backend/accounts/checks.py` |
| `AllowedOperation`, `AllowedWebMapServiceOperation`, `AllowedWebFeatureServiceOperation`, `ProxySetting`, `WebMapServiceProxySetting`, `WebFeatureServiceProxySetting` | `backend/registry/models/security.py` |
| `filter_by_request`, `is_spatial_secured`, `allowed_area_union` | `backend/registry/managers/security.py` |
| `OgcServiceProxyView` (`get_and_post`, `_test_as_user`) | `backend/registry/proxy/mixins.py` |
| `WebMapServiceProxy`, `WebFeatureServiceProxy` | `backend/registry/proxy/wms_proxy.py`, `backend/registry/proxy/wfs_proxy.py` |
| `SecureableWMSOperationEnum`, `SecureableWFSOperationEnum` | `backend/registry/enums/service.py` |
| `SECURE_ABLE_OPERATIONS_LOWER` | `backend/registry/settings.py` |
| proxy URLs | `backend/MrMap/urls.py` |
