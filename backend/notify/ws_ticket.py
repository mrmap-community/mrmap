"""Short-lived one-time tickets for the WebSocket handshake (#1472).

The handshake of ``/ws/default/`` carries the identity of its caller. For a
browser that is the same-origin ``sessionid`` cookie (#835); a client which only
holds a knox token must not pay for a socket with the token itself, because a
credential in the query string of a URL lands verbatim in the proxy access logs,
the browser history and any referer the page leaks it to. Such a client instead
exchanges its token over an authenticated HTTP call
(``POST /api/notify/websocket-ticket``, ``notify/views.py``) for a random ticket
which

* names nothing - it is opaque and carries no user id, because the minting
  stored the id behind it in the cache;
* is single-use - the redeeming read consumes it, so a ticket caught in a log
  line is already dead when the next handshake offers it;
* dies on its own after ``TICKET_TTL_SECONDS`` even if never used.

The store is the default cache, the same choice the login throttle of
``accounts/throttling.py`` makes: Redis in every deployment of this stack
(``MrMap/settings.py``), so the web worker which mints and the ASGI server which
redeems share it.
"""
import secrets

from django.contrib.auth import get_user_model
from django.core.cache import cache

TICKET_TTL_SECONDS = 10
TICKET_CACHE_PREFIX = "notify:ws-ticket:"


def mint_ticket(user_id):
    """Store ``user_id`` behind a fresh random ticket and return the ticket."""
    ticket = secrets.token_urlsafe(32)
    cache.set(f"{TICKET_CACHE_PREFIX}{ticket}", user_id, TICKET_TTL_SECONDS)
    return ticket


def consume_ticket(ticket):
    """Return the user ``ticket`` was minted for, else ``None``.

    The read deletes the entry, so the ticket authenticates at most one
    handshake: every later offer of the same value finds nothing. The user row
    is read after the consume, so a ticket minted for a since-deleted user
    answers nothing.
    """
    if not ticket:
        return None
    key = f"{TICKET_CACHE_PREFIX}{ticket}"
    user_id = cache.get(key)
    if user_id is None:
        return None
    cache.delete(key)
    return get_user_model().objects.filter(pk=user_id).first()
