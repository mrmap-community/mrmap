---
name: MrMap DRF JSON:API
description: "Working on MrMap API endpoints — DRF viewsets, serializers, django-filter FilterSets, pagination, nested routes, drf-spectacular OpenAPI schema, JSON:API request/response shapes, or any change the frontend consumes over /api."
---

# MrMap DRF / JSON:API

Task skill for the HTTP API layer in `backend/`. The nearest `AGENTS.md` wins; the API contract
rules are mandatory in `backend/AGENTS.md` ("API behavior") and `AGENTS.md` ("Never do"). This
skill adds where the existing abstractions are and how to use them.

## Activation

Load when the task touches: `registry/views/`, `registry/serializers/`, `registry/filters/`,
`extras/viewsets.py`, `extras/serializers.py`, `extras/schema.py`, `extras/routers.py`, URL
confs under `backend/`, or an OpenAPI-schema effect (the frontend parses `/api/schema` at runtime).

## Mandatory project rules (sources named)

- Preserve JSON:API 1.1 contracts: resource types, relationships, filter names, pagination, error
  shapes (`backend/AGENTS.md`). A denial answers
  `{"errors":[{"detail","status","code"}]}` — codes like `not_authenticated`, `permission_denied`,
  `invalid` carry the reason (`backend/tests/behave/AGENTS.md`).
- Never change an API contract or behaviour outside the requested scope; if the request implies
  one, explain the implication before proceeding (root `AGENTS.md`).
- Every viewset declares `permission_classes` explicitly; `DEFAULT_PERMISSION_CLASSES` is only
  the fail-closed floor a view naming none falls back to — anonymous reads, no anonymous writes
  (#1444).
  Reuse `extras.permissions.DjangoObjectPermissionsOrAnonReadOnly` or an existing pattern
  (see skill `mrmap-security`).
- Class-based views only; app-specific views in the owning app, generic ones in `extras/`;
  `MrMap/` holds routing only; declare accepted verbs with `http_method_names` and preserve each
  endpoint's existing method policy including OPTIONS/`Allow` (`backend/AGENTS.md`).
- A `sort`/`filter[...]` the frontend sends is a contract: declare it in the filterset or
  `ordering_fields` and pin it with a behave scenario **before** the screen asks for it (#1080,
  `frontend/AGENTS.md`).
- Where a list serializer exists, the detail serializer inherits from it; declare a field once on
  the base (`backend/AGENTS.md`).

## Recommended patterns (project code, mirror these)

- Canonical viewset stack: `SerializerClassesMixin, ObjectPermissionCheckerViewSetMixin,
  PreloadNotIncludesMixin, HistoryInformationViewSetMixin` + DRF/json:api mixins
  (`extras/viewsets.py`, used throughout `registry/views/service.py`).
- Async creation returns 202 + a BackgroundProcess resource via `extras.viewsets.AsyncCreateMixin`
  — never block a request on long work (see skill `mrmap-celery`).
- Nested resources: `extras/routers.NestedDefaultRouter` + `NestedModelViewSet`
  (`parents_query_lookups`), read-only by default.
- Serializer modules per aggregate in `registry/serializers/`; shared history fields via
  `HistoryInformationSerializer`, alert fields via `ServiceAlertSerializerMixin`, permissions-aware
  output via `ObjectPermissionCheckerSerializer` (`is_accessible`).
- Schema: keep `drf-spectacular` declarations honest — `@extend_schema` / `@extend_schema_view`
  with the operation-id conventions of `extras/schema.py` (`CustomOperationId`); the frontend
  derives fields, validation and operations from the schema and must not need workarounds
  (`frontend/src/jsonapi/AGENTS.md`).
- Sparse fieldsets: answer list needs from the list serializer and let `include`/sparse fieldsets
  control cost (`backend/AGENTS.md`, `docs/architecture.md`).

## Anti-patterns

- Forking a shared serializer/viewset/filter into a feature folder — extend or wrap (`AGENTS.md` "Never do").
- Re-declaring a serializer field a model property, annotation or mixin already answers
  (`backend/AGENTS.md`).
- Hardcoding frontend-side field lists or validation to work around a schema gap — report the
  schema limitation instead (`frontend/src/jsonapi/AGENTS.md`).
- Silent contract drift: renaming JSON:API types/attributes (camelCase via
  `JSON_API_FORMAT_FIELD_NAMES`), changing pagination or error envelopes.
- Function-based views, or handlers defined in URLconfs instead of `.as_view()` wiring.

## Framework references (recommendations, not project rules)

- JSON:API 1.1: https://jsonapi.org/format/1.1/ — DRF: https://www.django-rest-framework.org/
- drf-jsonapi: https://django-rest-framework-json-api.readthedocs.io/
- drf-spectacular: https://drf-spectacular.readthedocs.io/ — django-filter: https://django-filter.readthedocs.io/

## MCP dependencies

None required. Inspect the live schema through the stack (`/api/schema`) or the behave scenarios.
**Optional** (repo `opencode.json`, see `docs/development/mcp-servers.md`): `django-docs` (pinned
to the running Django) for DRF-adjacent framework questions — note the pin covers Django itself,
not DRF or drf-spectacular — and the read-only `postgres` server for checking what a serializer
actually reads. Degrade to the stack and the code when they are not configured.

## Verification (commands in `backend/AGENTS.md`)

1. `../.venv/bin/flake8 <files>` from `backend/`.
2. Targeted Django tests for the aggregate, then targeted behave of the endpoint
   (`--simple --noinput --keepdb`, quote the `json:api/` path) — tiers in
   `backend/tests/behave/AGENTS.md`.
3. Contract-visible changes: also check frontend usage before merging
   (`backend/AGENTS.md`) and run the relevant `frontend` specs.

## Security constraints

- Preserve permission checks and queryset visibility rules; new endpoints start read-scoped with
  guardian object permissions and assert denial reasons in behave.
- Never expose stored service credentials, tokens or proxy request bodies through serializers or
  logs (see skill `mrmap-security`).

## Explicit exceptions

- A contract change is allowed only when explicitly requested/accepted on the issue; then update
  behave scenarios, schema consumers and the frontend in the same change.
- Non-JSON:API endpoints exist by design (`auth/login|logout`, `/api/schema`, `/csw`, proxy) and
  answer plain JSON or XML — do not "normalize" them (their scenarios set their own `Accept`).
