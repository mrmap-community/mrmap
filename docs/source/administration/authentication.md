# Authentication and session lifetime

MrMap distinguishes **browser sessions** from **machine/API tokens**. This page
documents each credential, its lifetime, how it ends, and the contract by which
the API tells a dead credential apart from a refused action. Related:
[permissions.md](permissions.md) (what an authenticated caller may do) and
issue #835 (accepted decision Q8=B: the browser authenticates with a Django
session + CSRF, machine clients keep the token endpoint).

## The two credentials

| | Browser session | Machine / API token |
| --- | --- | --- |
| Opened by | `POST /api/auth/session` (HTTP Basic credentials in the login request only) | `POST /api/auth/login` (HTTP Basic) answers a knox token |
| Carried by | the `sessionid` cookie, attached by the browser itself | `Authorization: Token …` header, kept by the caller |
| Held by the SPA | never — it is an `HttpOnly` cookie JavaScript cannot read | the caller's own storage |
| Lifetime | `SESSION_COOKIE_AGE` (30 min), sliding — see below | `REST_KNOX["TOKEN_TTL"]` (10 h), hard stop |
| Ended by | `DELETE /api/auth/session` (flushes the session server-side) | `POST /api/auth/logout` (deletes exactly the presented token row, #832) |

The credential a browser script can read is a credential a script can copy, so
the SPA holds none (#835). What survives in `localStorage` is an identity
marker (`mrmap.session`: user id and name only) — losing it costs a reload, not
a session.

**Basic is a login-time credential only.** Since #1450 HTTP Basic is declared
on the two login endpoints themselves (the `authentication_classes` of
`backend/accounts/views/auth.py`) and dropped from DRF's global
`DEFAULT_AUTHENTICATION_CLASSES`: with Basic in the global stack, *every*
endpoint silently accepted the account password beside the credential it
documents. A machine client that wants to address the API keeps the token of
`POST /api/auth/login` (#835) and never hands out the password per request.

**Login attempts are budgeted.** The two credential-carrying POSTs answer
**429** once a client address spends `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
["login"]` attempts (30/min) in one minute — counted *before* the credential is
read, so refused attempts count too, in the deployment's cache and per client
address (the edge's `X-Real-IP` behind nginx, `backend/accounts/throttling.py`).
The password-free verbs — the session probe, the logout — cost nothing. The
budget is sized from what the application itself does from one address; a
deployment whose machine clients share one NAT address and log in more often
raises the setting. (#1450)

## Browser session lifetime

`POST /api/auth/session` turns the request's Basic credentials into a Django
session (`login()`); the answer is `{"authenticated": true}` — no token, no
expiry value, nothing to keep. The relevant settings in
`backend/MrMap/settings.py`:

| Setting | Value | Meaning |
| --- | --- | --- |
| `SESSION_COOKIE_AGE` | `1800` s | The session ages out after 30 minutes of *inactivity*. |
| `SESSION_SAVE_EVERY_REQUEST` | `True` | Every request slides that window; an actively used session does not expire mid-work, an abandoned one ends on its own. |
| `SESSION_COOKIE_HTTPONLY` | `True` | The session cookie is unreadable to JavaScript by design. |
| `SESSION_COOKIE_SAMESITE` | `"Lax"` | nginx serves the SPA and proxies `/api` and `/ws` from the same origin (`docker/nginx/mrmap.conf`), so every request needing the credential is same-site anyway. |
| `CSRF_COOKIE_HTTPONLY` | `False` | The SPA must read the CSRF cookie to repeat it in the `X-CSRFToken` header (see the CSRF paragraph). |
| `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` | `DJANGO_COOKIE_SECURE`, defaulting to `MRMAP_PRODUCTION` | TLS-only cookies. On an http-only deployment set `DJANGO_COOKIE_SECURE=False`, or the browser refuses to store the session and no login sticks; a https deployment that is not flagged production can opt in. |

**CSRF.** DRF's `SessionAuthentication` (first in
`DEFAULT_AUTHENTICATION_CLASSES`) demands the `X-CSRFToken` header beside the
cookie for every state-changing request the session authenticates. The SPA
reads the `csrftoken` cookie and repeats it (axios via `xsrfCookieName`/
`xsrfHeaderName`, the provider's own `fetch` calls explicitly). `GET /api/auth/session`
ensures the cookie exists — Django only sends it where somebody asks — which is
why the SPA's boot probe is also its CSRF bootstrap. A `POST` that
authenticates by Basic *without* a session (the normal first login) is not
session-authenticated and needs no token; re-logging into a live session does,
which is the login-CSRF guard Django's own login view provides.

**What the user notices** (frontend behaviour, translated in the UI's language):

* Whether the cookie still authenticates is answered by the backend, not by a
  client-side clock: the SPA's boot probe is `GET /api/auth/session` ("does
  this browser have a live session?"), answered `{"authenticated": true|false}`
  and deliberately answerable anonymously — knowing *whether* a cookie
  authenticates grants nothing. A refused probe lands the user on the login
  page with the reason — "Your session has expired" / "Ihre Sitzung ist
  abgelaufen".
* A logout (`DELETE`) flushes the session server-side, so a cookie copied out
  of the browser before the logout answers nothing afterwards. The local
  session ends even when the backend is unreachable (#832).

The WebSocket carries the same credential: the handshake is same-origin, and
`channels`' `AuthMiddlewareStack` resolves the user from the session cookie.
No token travels in the query string any more — there is none to put there.
(The backend still accepts the legacy `?token=` parameter for old clients; it
is deprecated in `backend/notify/auth.py` and should disappear with the last
pre-#835 client.)

## Machine / API token lifetime and revocation

`POST /api/auth/login` (Basic) and `POST /api/auth/logout` remain for scripts
and CLI clients. The policy is an explicit deployment decision in
`backend/MrMap/settings.py`:

| Setting | Value | Meaning |
| --- | --- | --- |
| `REST_KNOX["TOKEN_TTL"]` | `timedelta(hours=10)` | One working day, enforced **server-side** on every request against the token row's `expiry` — not a client-side notion. |
| `REST_KNOX["AUTO_REFRESH"]` | `False` | No rolling extension. Activity does not stretch the token; it ends predictably. |

Revocation paths:

* `POST /api/auth/logout` (with the token in `Authorization: Token …`) deletes
  exactly the presented token row — other devices of the same user keep their
  tokens (pinned by `tests/django/accounts/test_logout_revokes_token.py`).
* A server administrator can delete a token row (or the user) directly; the
  next request with it is refused like a never-issued one.

There is **no long-lived API-token facility** and no separate scope model; a
dedicated machine-token policy (longer or unbounded lifetime, per-purpose
scopes, admin-issued) is a deliberate open decision tracked with #835 and not
something to infer from the browser-session or token TTL.

## The auth-vs-denied contract

DRF keeps its 401 only when the *first* configured authenticator advertises a
`WWW-Authenticate` scheme. MrMap's list starts with `SessionAuthentication`,
which has none, so **the status code alone does not identify authentication
loss** — an expired session, a revoked token and a permission refusal all
answer **403**. The deliberate contract is in the JSON:API error `code`
(pinned by `tests/django/accounts/test_session_lifetime.py` and
`tests/django/accounts/test_browser_session.py`):

| Situation | Status | Error `code` | Client consequence |
| --- | --- | --- | --- |
| No credential, endpoint requires one | 403 | `not_authenticated` | Not logged in (public pages stay, protected ones lead to login). |
| Expired session cookie / revoked token presented | 403 | `authentication_failed` | Credential is dead: end the session, land on `/login` with the reason. |
| Valid credential, action refused | 403 | `permission_denied` | **Session stays.** Notify, revalidate the caller's roles/identity; open screens drop the lost rights on the next revalidation. |
| CSRF check failed on a session-authenticated write | 403 | `permission_denied` | The session is alive but the request repeated no CSRF cookie. The SPA always sends it; a client without one must read the cookie first (`GET /api/auth/session`). |
| Credential rejected with a `401` (possible in other stacks, e.g. Basic against `WWW-Authenticate`) | 401 | `authentication_failed` / `not_authenticated` | Same as the dead-credential row. |
| Login budget spent by the client address (`POST /api/auth/session`, `POST /api/auth/login`) | 429 | plain JSON `detail` with a `Retry-After` header, like these views' other refusals | Wait the window out; while the budget is spent no credential of this address is even read. The password-free verbs — probe, logout — never cost anything (#1450). |

The frontend (`frontend/src/providers/authProvider.ts`) implements exactly
this: 401 always ends the session; a 403 ends it **only** when the error code
says the credential itself is (no longer) accepted — a `permission_denied`
never logs a live session out. Because a session cookie carries no
client-readable expiry, a 403 without a readable code never guesses the session
dead; the next backend answer decides.

## Revocation while working

* **Logout** closes the session server-side and clears local state even when
  the backend is unreachable (#832).
* **Self-revocation** of one's own administration role on the Members screen
  immediately revalidates the permission snapshot and the cached access answers
  (#727/#737): menus and buttons follow without a manual reload.
* **Revocation by someone else** becomes visible at the caller's next
  revalidation: the next refused write (a `permission_denied`) invalidates the
  cached permission snapshot and react-admin's access answers, so open lists
  reflect the loss within one refetch. The backend is authoritative either
  way — a stale client cache can never grant access the server refuses.
* The identity endpoint `GET /api/accounts/who-am-i/` stays readable without a
  credential (anonymous read-only baseline, #833); presenting a dead session
  or token to it is refused with `authentication_failed`, which is what lets
  the client tell "not logged in" apart from "my session died".

## Rolling out and back (#835)

* Deploying the new frontend logs every browser in once: a page load finds the
  knox token the previous frontend left in `localStorage`, revokes exactly that
  token at `POST /api/auth/logout` (#832) and drops it. Machine clients are
  untouched — their tokens never lived in browser storage.
* Rollback to a pre-#835 frontend stays possible: the knox endpoints are still
  mounted and browser users simply log in again (which issues a fresh token).
  Browsers that already ran the new frontend had their old token revoked;
  scripts are unaffected.
* A session opened by the new frontend is closed by `DELETE /api/auth/session`;
  rolling back does not flush sessions, but they age out with
  `SESSION_COOKIE_AGE` and harm nothing — a pre-#835 frontend ignores them.
