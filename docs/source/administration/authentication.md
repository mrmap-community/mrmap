# Authentication and session lifetime

MrMap distinguishes **browser sessions** from **machine/API tokens**. This page
documents the lifetime of each, how a session ends, and the contract by which
the API tells a dead credential apart from a refused action. Related:
[permissions.md](permissions.md) (what an authenticated caller may do), issue
#835 (planned migration of browser auth to Django sessions + CSRF).

## Browser session lifetime

The browser authenticates with a token that `POST /api/auth/login` (HTTP Basic
credentials) issues through django-rest-knox. Its lifetime is an explicit
deployment decision in `backend/MrMap/settings.py`:

| Setting | Value | Meaning |
| --- | --- | --- |
| `REST_KNOX["TOKEN_TTL"]` | `timedelta(hours=10)` | One working day, enforced **server-side** on every request against the token row's `expiry` — not a client-side notion. |
| `REST_KNOX["AUTO_REFRESH"]` | `False` | No rolling extension. Activity does not stretch the session; it ends predictably. |
| `REST_KNOX["TOKEN_LIMIT_PER_USER"]` | `5` | At most five **not-yet-expired** tokens per user (#1450). While the cap is reached, `POST /api/auth/login` refuses further logins with `403` and issues no token; a logout or an expiry frees a slot. This bounds what one seen credential can farm — it is not a device-management promise, and there is no per-device view. |

The login response hands the client the exact expiry moment (`expiry`), and the
client trusts no other value. Because server row and client copy are the same
moment, a session cannot silently outlive its enforcement.

**What the user notices** (frontend behaviour, translated in the UI's language):

* The session ends at the configured time even while work is open. The user
  lands on the login page and the reason is shown — "Your session has expired"
  / "Ihre Sitzung ist abgelaufen" — as is "Your login was rejected from another
  source" when the credential was revoked server-side mid-flight.
* Re-login always works with the normal credentials; nothing else resets.

Expiry is a hard end, not a soft warning; a refresh/renewal flow is deliberately
not part of this stack (knox has no refresh-token concept). When #835 lands,
Django's `SESSION_*` settings take over this section and the `REST_KNOX` block
retires.

## Login rate limit

`POST /api/auth/login` is the only endpoint an anonymous caller may reach, so
its attempts are rate-limited (`ScopedRateThrottle`, scopes declared in
`REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]`, pinned by
`tests/django/accounts/test_login_throttle.py`). The counter window lives in
the deployment's `default` cache — redis — so all application workers share
one answer.

| Scope | Rate | Counts | Keyed by |
| --- | --- | --- | --- |
| `login_anon` | `10/min` | **refused** attempts: no credential, or wrong credentials | client IP |
| `login` | `30/min` | requests that presented a **valid** credential | user |

Consequences an administrator should read off this table:

* A client that exceeded the anonymous window is answered **429** until the
  window passes; the response names the wait. Refused guesses share one
  window per address and are never attributed to the guessed-at account.
* A valid credential is *not* locked out by a full `login_anon` window —
  a guesser cannot deny the honest caller behind the same address — and the
  per-user window is far above any interactive login pattern.
* Behind a shared address (NAT, one office) the 10/min is shared too. It is
  sized for typos and humans, not for scripted clients logging in through
  the browser endpoint; scripts share the browser's TTL and cap anyway
  (next section).

`BasicAuthentication` remains in `DEFAULT_AUTHENTICATION_CLASSES` (#1450
evaluation): it is the credential exchange of the login endpoint itself —
knox's `LoginView` carries no authenticator of its own — so dropping it is an
API-wide credential change needing a full acceptance run and an explicit
admin decision, tracked as #1450's follow-up. Removing it is **not** a knob
an operator should flip locally by editing settings.

## Machine / API token lifetime and revocation

Every credential knox issues today comes from the same login endpoint, so a
script authenticating with Basic and keeping the token shares the browser
session's TTL: **10 hours, no refresh, hard stop** — and it shares the
`TOKEN_LIMIT_PER_USER` cap and the login throttle above. Revocation paths:

* `POST /api/auth/logout` (with the token in `Authorization: Token …`) deletes
  exactly the presented token row — other devices of the same user keep their
  tokens (pinned by `tests/django/accounts/test_logout_revokes_token.py`).
* A server administrator can delete a token row (or the user) directly; the
  next request with it is refused like a never-issued one.

There is **no long-lived API-token facility** and no separate scope model; a
dedicated machine-token policy (longer or unbounded lifetime, per-purpose
scopes, admin-issued) is a deliberate open decision tracked with #835 and not
something to infer from the browser-session TTL.

## The auth-vs-denied contract

DRF keeps its 401 only when the *first* configured authenticator advertises a
`WWW-Authenticate` scheme. MrMap's list starts with `SessionAuthentication`,
which has none, so **the status code alone does not identify authentication
loss** — an expired, revoked or unknown credential and a permission refusal
both answer **403**. The deliberate contract is in the JSON:API error `code`
(pinned by `tests/django/accounts/test_session_lifetime.py`):

| Situation | Status | Error `code` | Client consequence |
| --- | --- | --- | --- |
| No credential, endpoint requires one | 403 | `not_authenticated` | Not logged in (public pages stay, protected ones lead to login). |
| Expired / revoked / unknown token presented | 403 | `authentication_failed` | Session is dead: clear the credential, land on `/login` with the reason. |
| Valid credential, action refused | 403 | `permission_denied` | **Session stays.** Notify, revalidate the caller's roles/identity; open screens drop the lost rights on the next revalidation. |
| Too many login attempts from this client | 429 | — (the login endpoint answers DRF's plain `{"detail": …}`, not the JSON:API envelope) | Rate limit, not an auth verdict (#1450): the credential question was never answered. Wait the stated time; a valid credential re-logging in is unaffected. |
| Credential rejected with a `401` (possible in other stacks, e.g. after #835 or with Basic against `WWW-Authenticate`) | 401 | `authentication_failed` / `not_authenticated` | Same as the expired-token row. |

The frontend (`frontend/src/providers/authProvider.ts`) implements exactly this:
401 always clears credentials; a 403 clears them **only** when the error code
says the credential itself is (no longer) accepted — a `permission_denied` never
logs a valid session out.

## Revocation while working

* **Logout** revokes server-side and clears local state even when the backend
  is unreachable (#832).
* **Self-revocation** of one's own administration role on the Members screen
  immediately revalidates the permission snapshot and the cached access answers
  (#727/#737): menus and buttons follow without a manual reload.
* **Revocation by someone else** becomes visible at the caller's next
  revalidation: the next refused write (a `permission_denied`) invalidates the
  cached permission snapshot and react-admin's access answers, so open lists
  reflect the loss within one refetch. The backend is authoritative either
  way — a stale client cache can never grant access the server refuses.
* The identity endpoint `GET /api/accounts/who-am-i/` stays readable without a
  credential (anonymous read-only baseline, #833); presenting a dead token to
  it is refused with `authentication_failed`, which is what lets the client
  tell "not logged in" apart from "my token died".
