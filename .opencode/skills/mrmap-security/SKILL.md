---
name: MrMap Security
description: "Security-sensitive MrMap work — guardian object permissions, the security proxy (WMS/WFS), authentication (session/Basic/Knox tokens, WebSocket auth), authorization in viewsets, service credentials and secrets, external HTTP/SSRF and XML exposure, or any change that could widen access."
---

# MrMap Security

Task skill for anything that touches who may do what, and how untrusted input enters the system.
The nearest `AGENTS.md` wins; the non-negotiables are in `AGENTS.md` ("Never do") and
`backend/AGENTS.md` ("API behavior"). `docs/architecture.md` ("Security Proxy") describes the
domain; open epic #727 (declarative roles) means **permission-model concepts must not be invented
locally**.

## Activation

Load when the task touches `backend/accounts/`, `backend/extras/permissions.py`,
`backend/registry/proxy/`, `registry/managers/security.py`, permission checks in viewsets or
serializers, Knox/session auth, `notify/auth.py`, stored service credentials, proxy request
logging, or any outbound HTTP/XML surface.

## Mandatory project rules (sources named)

- Authorization is guardian object permissions per object, enforced per viewset with an explicit
  `permission_classes` (settings define no global default). Reuse
  `extras.permissions.DjangoObjectPermissionsOrAnonReadOnly` or the existing pattern; keep
  permission checks and queryset visibility rules intact in every refactor
  (`backend/AGENTS.md`).
- Object-permission answers flow through the shared checker: the viewset builds
  `ObjectPermissionChecker` once per request (`extras/viewsets.ObjectPermissionCheckerViewSetMixin`)
  and serializers reuse it (`extras/serializers.ObjectPermissionCheckerSerializer`). Do not build
  per-object checkers — `assertNoSlowObjectPermissions` will fail and the serializer logs a warning
  (`backend/tests/AGENTS.md`).
- Anonymous access is backed by the real DB user `AnonymousUser` (guardian's row, created on
  `post_migrate`; queried by username in `registry/managers/security.py`,
  `registry/proxy/mixins.py`, `registry/filters/security.py`). Keep its group membership
  semantics; tests must re-create it when a `TransactionTestCase` flushed it
  (`backend/tests/AGENTS.md`).
- Proxy (`registry/proxy/`): the service decision comes from
  `service_cls.security.prepare_with_security_info(...).prefetch_whole_service()`; inactive →
  HTTP 423 → `DisabledException`; secured operations without a matching
  `AllowedWebMapServiceOperation`/`AllowedWebFeatureServiceOperation` → `PermissionDenied` →
  `ForbiddenException`; GetCapabilities is served from the stored document. Fail-closed: the WMS
  mask compositing recreates the full mask on any error.
- Forwarded requests **never carry the caller's credentials**: the proxy strips
  `Authorization`, `Cookie`, `Host` and authenticates upstream with the registered service
  credentials only (`registry/proxy/mixins.py` `get_remote_response`). Upstream target is the
  registered operation URL, never a caller-supplied host.
- The "test as user" facility (`X-Test-As-User` header / `_test_as_user` param) is gated on
  `is_staff or is_superuser` and logs both identities — keep the gate and the logging.
- Authentication stack: session + Basic + Knox (`REST_FRAMEWORK` in `MrMap/settings.py`);
  WebSocket auth validates the Knox token in `notify/auth.py`; logout revokes the presented token
  (POST `auth/logout`). Argon2 hashes first; session age 30 min rolling. Do not add new auth
  schemes without an accepted issue.
- Secrets: configuration comes from `.env` / `docker/backend/.mrmap.env`; missing values fail
  early — ask for them, never invent or commit them. When blocked on a credential, use
  `scripts/wip wait` (root `AGENTS.md`).

## Recommended patterns (project code, mirror these)

- New permissioned object: grant creator/view perms with `guardian.shortcuts.assign_perm` in the
  creation signals pattern of `accounts/signals.py`; permissions live in the `registry` app even
  for accounts models — follow that, don't restructure it here.
- Outbound requests: use `OgcClient` (timeout, redirect containment) or a `Session` with an
  explicit timeout and `allow_redirects` handled consciously; TLS verification stays on (the
  `VERIFY_SSL_CERTIFICATES` constant is currently unused by the HTTP layer — don't rely on it).
- Untrusted XML: hardened lxml parser (`resolve_entities=False, no_network=True`) — the pattern in
  `registry/models/harvest.py`, `registry/helper/preview.py`.
- New endpoint answering derived visibility: expose `is_accessible` via the checker serializer
  instead of computing per-row.

## Anti-patterns

- Removing/narrowing a `permission_classes` or queryset filter "temporarily" during a refactor.
- Debug shortcuts that impersonate users outside the staff-gated test-as-user path; tokens or
  passwords in URLs, logs, `BackgroundProcess` fields or fixtures.
- Logging proxy bodies without the existing file-based log models (they gate what is stored).
- Relaxing `csrf_exempt` scope: it exists on the OGC endpoints (KVP/POST from map clients) — keep
  it exactly where it is; new JSON:API endpoints keep CSRF protection.
- Editing CORS/CSRF/trusted-origin settings: `CORS_ALLOW_ALL_ORIGINS` with a startup warning is a
  deployment-time concern documented in `docs/source/development/environment.rst` — changing it is
  a human decision (`scripts/decisions`), not a side effect of a feature PR.

## Framework references (recommendations, not project rules)

- django-guardian: https://django-guardian.readthedocs.io/
- django-rest-knox: https://github.com/EZTextLabs/django-rest-knox
- OWASP SSRF/XML-external-entity preventions: https://owasp.org/www-community/attacks/Server-Side_Request_Forgery

## MCP dependencies

None for the work itself. The project's `postgres` MCP is already restricted (read-only
`mcp_readonly` role, 127.0.0.1-only forwarder, no write tools) — that restriction is defence in
depth, not permission: use it for schema introspection, never to dump user, group or credential
data; reason over fixtures (`accounts/fixtures/test_users.json`, `@fixtures:` sets) and the code
paths above. `sonarqube` (remote, needs the per-host user token file
`~/.config/opencode/sonar-token`) reports security
findings on open PRs — read them, never work around them (root `AGENTS.md`, SonarCloud).

## Verification (commands in `backend/AGENTS.md`, `backend/tests/behave/AGENTS.md`)

1. `../.venv/bin/flake8 <files>` from `backend/`.
2. Permission-visible changes: run the behave permission/object-permission scenarios
   (`features/json:api/registry/security/`, `steps/object_permissions.py`) and the proxy unit
   tests under `tests/django/registry/mrmap-proxy/` (path form, not dotted label).
3. Denials assert their reason code — extend the scenario, not just the status assertion.
4. CI adds CodeQL `security-extended`; treat a new CodeQL finding on auth/proxy code as blocking
   and fix at the reported line.

## Security constraints (this skill's own)

- Never print secret values found in `.env` while debugging; name the variable, not its value.
- A security fix never widens anything else on the side; report anything adjacent you noticed
  instead of silently changing it (root `AGENTS.md`, "Do not silently change behavior").

## Explicit exceptions

- `NOSONAR` with a reason comment is the accepted suppression for normative OGC/ISO/INSPIRE
  identifiers that look like insecure URLs/IPs (root `AGENTS.md`,
  `docs/source/development/code-quality.rst`) — never for an actual reachable URL or credential.
- The proxy endpoints answer OGC XML exceptions, not JSON:API errors, by design — a scenario
  expecting `{"errors": ...}` from them is the scenario being wrong
  (`backend/tests/behave/AGENTS.md`).
