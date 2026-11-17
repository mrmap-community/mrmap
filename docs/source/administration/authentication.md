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

## Machine / API token lifetime and revocation

Every credential knox issues today comes from the same login endpoint, so a
script authenticating with Basic and keeping the token shares the browser
session's TTL: **10 hours, no refresh, hard stop**. Revocation paths:

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
