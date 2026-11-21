"""Host policy for every server-side fetch of a URL somebody else wrote (#1474, SEC-16).

A service URL is user input: it is typed at registration, and every upstream capabilities
document and metadata reference rewrites it. Before this module nothing but the timeouts
bounded *where* such a URL made the backend connect, so whoever may register a service could
aim the backend at an internal endpoint - the cloud metadata service at 169.254.169.254, the
docker socket API, the database - and read the answer back as a metadata document, a preview
map, or the detail of an error response.

The policy is deliberately not a blanket ban; hosting a service inside the own network is a
normal Mr.Map deployment. It answers one question per address, in this order:

``MRMAP_FETCH_DENY_NETWORKS``
    an explicit fence of the deployment wins over everything else.
``MRMAP_FETCH_ALLOW_NETWORKS``
    an explicit grant wins over the default ranges. It is the one and only way any refused
    range is ever reached, so there is exactly one way to open the policy and it is an entry
    somebody has to write down. Outside production the loopback and private ranges are
    granted too, by `_development_allowance()`.
the default ranges
    loopback, private, link-local and the IPv4 carrier-grade NAT range, multicast, reserved,
    unspecified, the benchmarking block and the rest of the 0/8 block are refused. Everything
    else is a public address and is allowed.

For a URL carrying an IP literal that verdict is final, and `host_is_allowed` answers it
without touching DNS. For a host name it is only the first half: the transport re-answers the
same question for **every** address the name resolves to, at the moment the socket to that
address is created. That is the only place a DNS rebinding answer is still caught - the
answer of the second lookup may differ from the answer of the first, and a pooled socket may
be older than any check - and it is why the guard is a connection class and not a request
hook.

Checking once the socket exists costs one TCP handshake to an address which is refused before
a single byte of the request is written. It buys the verdict about the address which is
actually connected to instead of the verdict about an address an earlier lookup claimed. For
https through a tunneling proxy both ends are judged: the proxy as the peer, the tunnel target
as the endpoint. A *forwarding* proxy is judged as the peer only - it is the deployment's own
choice, and the endpoint behind it is judged by the request the proxy itself forwards.

A refusal is raised as ``requests.exceptions.ConnectionError``, the error every caller which
already copes with an unreachable endpoint catches: a refused endpoint reads as unreachable,
which is what the operator sees and what the registration reports.
"""
import ipaddress
import logging
import socket
from urllib.parse import urlsplit

from django.conf import settings
from requests import Session
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectionError
from urllib3 import connectionpool

logger = logging.getLogger(__name__)

#: the semantics of this module and the settings which open it again
POLICY_DOC = "docs/source/administration/fetch-host-policy.md"

#: the benchmarking block of RFC 2544, which ``is_private`` does not answer for and which
#: no service is served from
BENCHMARKING = ipaddress.ip_network('198.18.0.0/15')
#: the carrier-grade NAT range of RFC 6598: what a Tailscale network and the IPv4 fabric of a
#: provider answer from, and where an internal-only service of the *infrastructure* lives
CARRIER_GRADE_NAT = ipaddress.ip_network('100.64.0.0/10')


def _development_allowance():
    """The ranges a deployment outside production may fetch from without being granted

    The unit tests of the registry run against loopback listeners, and the services of the
    development compose stack reach each other by name over the private network of the stack.
    Both are refused by the default ranges, which are the ranges of a deployment serving the
    public web - which a development stack is not. So its own ranges are granted while
    ``MRMAP_PRODUCTION`` is off, and only then: production refuses them and an internally
    hosted service needs a ``MRMAP_FETCH_ALLOW_NETWORKS`` entry.
    """
    if getattr(settings, 'MRMAP_PRODUCTION', True):
        return []
    return ['127.0.0.0/8', '::1/128', '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16',
            'fc00::/7']


def _networks(entries):
    """The network objects of the given CIDR strings, with unparseable entries dropped

    A broken entry in a list an operator edits by hand must not break every fetch of the
    deployment. Refusing the addresses that entry would have granted is the price of that,
    and the warning names the entry so the operator finds it.
    """
    networks = []
    for entry in entries:
        entry = entry.strip() if isinstance(entry, str) else entry
        if not entry:
            continue
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            logger.warning('mrmap.fetch: ignoring unparseable network %r', entry)
    return tuple(networks)


def _policy():
    """The configured allow- and deny-lists, read from the current configuration

    Read per judged address rather than once at import time: a deployment supplies them
    through its environment and a test overrides them with ``@override_settings``, neither of
    which takes effect while something holds an older answer. Parsing a handful of CIDRs
    costs far less than the DNS lookup of the host it judges, and this is the only place the
    settings are read at all.
    """
    return {
        'allow': _networks(_development_allowance()
                           + list(getattr(settings, 'MRMAP_FETCH_ALLOW_NETWORKS', ()) or ())),
        'deny': _networks(getattr(settings, 'MRMAP_FETCH_DENY_NETWORKS', ()) or ()),
    }


def _refused_range(address):
    """Whether the address belongs to a range no registered service is fetched from

    The stdlib properties cover the IANA special-use registry: ``is_private`` answers for
    loopback, unique-local, site-local, the 0/8 block and the carrier-grade NAT range, and
    link-local, multicast, reserved, unspecified and loopback answer for themselves. Both
    address families are asked, because an endpoint is allowed or refused as one address even
    when it is reachable through the other.
    """
    return (address.is_private or address.is_link_local or address.is_loopback
            or address.is_multicast or address.is_reserved or address.is_unspecified
            or address in BENCHMARKING
            or (address.version == 4 and address in CARRIER_GRADE_NAT))


def _sixtofour(address):
    """The IPv4 address carried by a 6to4 address (RFC 3056), if this is one"""
    if address in ipaddress.ip_network('2002::/16'):
        return ipaddress.IPv4Address(address.packed[2:6])


def _teredo_server(address):
    """The IPv4 address of the Teredo server of a Teredo address (RFC 4380), if there is one

    RFC 4380 stores the server address bitwise inverted, which is what makes it readable
    here. The client address in the same packet is obfuscated with an XOR key and is not
    recovered: the server is the address reachable through the relay.
    """
    if address in ipaddress.ip_network('2001::/32'):
        return ipaddress.IPv4Address(bytes(byte ^ 0xFF for byte in address.packed[4:8]))


def _hidden_forms(address):
    """The address itself plus every other-family form of it which exists

    ``::ffff:127.0.0.1``, a Teredo and a 6to4 address are how an internal address is written
    down so that a filter looking only at the text of a URL does not recognise it. All of
    them are judged as the address they encode.
    """
    forms = [address]
    forms.append(address.ipv4_mapped)
    if address.version == 6:
        forms.append(_sixtofour(address))
        forms.append(_teredo_server(address))
    return [form for form in forms if form is not None]


def address_is_allowed(address):
    """Whether the policy lets a fetch be aimed at the given address

    Args:
        address (ipaddress.IPv4Address | ipaddress.IPv6Address): the address to judge

    Returns:
        bool: True for an allowed address, False for a refused one
    """
    policy = _policy()
    if any(address in network for network in policy['deny']):
        return False
    if any(address in network for network in policy['allow']):
        return True
    return not any(_refused_range(form) for form in _hidden_forms(address))


def host_is_allowed(host):
    """Whether the policy lets a fetch be aimed at the given host name or IP literal

    A host *name* is answered with True: what the policy judges are the addresses of a name,
    and those are judged by the transport once the lookup is answered (see
    `checked_addresses`). Only a literal can be judged without a lookup, and that is what
    makes this usable as a field validator: a name is never refused here, so no screen gets
    slower or noisier than the endpoint it validates, and a rebinding answer is still caught.
    """
    address = _literal(host)
    if address is None:
        return True
    return address_is_allowed(address)


def url_is_fetchable(url):
    """Whether a URL names a host whose literal the policy allows, True for a host name"""
    return host_is_allowed(urlsplit(str(url or '')).hostname)


def _literal(host):
    """The address a host string spells out, None for a name"""
    if not host:
        return None
    try:
        return ipaddress.ip_address(host.strip().strip('[]'))
    except ValueError:
        return None


def _refusal(host, address):
    """Log the refusal of one address of one host and build the error answering it"""
    logger.warning('mrmap.fetch: %s refused by the host policy (%s)', host, address)
    return ConnectionError(
        f'{host}: the address {address} is refused by the fetch host policy of this Mr.Map '
        f'deployment. An endpoint legitimately hosted internally is allowed with '
        f'MRMAP_FETCH_ALLOW_NETWORKS, see {POLICY_DOC}.')


def _addresses_of(host, port):
    """Every address of a host or literal, as the connect layer sees it

    A host which resolves to nothing yields ``(None,)`` and not ``()``: what cannot be judged
    is not let through by accident, and an unresolvable host is unreachable for the caller
    either way.
    """
    literal = _literal(host)
    if literal is not None:
        return (str(literal),)
    try:
        infos = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError, OverflowError):
        return (None,)
    return tuple(dict.fromkeys(info[4][0] for info in infos))


def checked_addresses(host, port, peer=None, tunnel=None):
    """Refuse the first target address of a connection which the policy does not allow

    Every address the name resolves to is judged and not only the first: an endpoint which
    answers with one public and one internal address is exactly the rebinding setup this
    guards.

    Args:
        host (str): the host the request names
        port (int): the port the request names
        peer (str): the address the socket is actually connected to, when it is connected
        tunnel (tuple): ``(host, port)`` a proxied connection tunnels to, when it tunnels

    Raises:
        requests.exceptions.ConnectionError: on the first refused target
    """
    targets = []
    if peer:
        targets.append(peer)
    if tunnel:
        targets.extend(_addresses_of(tunnel[0], tunnel[1]))
    targets.extend(_addresses_of(host, port))
    for address in dict.fromkeys(targets):
        if address is None:
            raise ConnectionError(f'{host}: the host does not resolve to any address.')
        if not address_is_allowed(ipaddress.ip_address(address)):
            raise _refusal(host, address)


class HostPolicyMixin:
    """The host policy of one connection, applied where its socket is created

    A mixin over the urllib3 connection classes rather than a hook on ``Session.send``: a
    response hook runs after the request was written, and an adapter only ever sees the name
    of the prepared request. Both would judge the *intent* of a fetch instead of the
    connection it actually opened, which is the whole point: a name is not an address.
    """

    def _new_conn(self):
        sock = super()._new_conn()
        try:
            checked_addresses(self.host, self.port, peer=sock.getpeername()[0],
                              **self._tunnel_target())
        except BaseException:
            # the refused socket must not stay open and the caller must see the refusal
            sock.close()
            raise
        return sock

    def _tunnel_target(self):
        """The endpoint of a tunneling proxy, as ``set_tunnel`` stored it"""
        if self._tunnel_host:
            return {'tunnel': (self._tunnel_host, self._tunnel_port)}
        return {}


class GuardedHTTPConnection(HostPolicyMixin, connectionpool.HTTPConnection):
    pass


class GuardedHTTPSConnection(HostPolicyMixin, connectionpool.HTTPSConnection):
    pass


class GuardedHTTPConnectionPool(connectionpool.HTTPConnectionPool):
    ConnectionCls = GuardedHTTPConnection


class GuardedHTTPSConnectionPool(connectionpool.HTTPSConnectionPool):
    ConnectionCls = GuardedHTTPSConnection


#: the pools of a guarded manager, so that only the connections of a `GuardedSession` and
#: never those of a plain `requests.Session` in the same process are judged
GUARDED_POOL_CLASSES = {'http': GuardedHTTPConnectionPool, 'https': GuardedHTTPSConnectionPool}


class GuardedHTTPAdapter(HTTPAdapter):
    """An adapter whose pools create their sockets through the host policy

    The pool classes are swapped on the pool manager instead of handed over as a connection
    keyword argument, because urllib3 builds its pool cache key from exactly the keywords it
    knows: an unknown one is a TypeError on the first request instead of a guarded
    connection.
    """

    def init_poolmanager(self, *args, **kwargs):
        manager = super().init_poolmanager(*args, **kwargs)
        manager.pool_classes_by_scheme = GUARDED_POOL_CLASSES
        return manager

    def proxy_manager_for(self, *args, **kwargs):
        manager = super().proxy_manager_for(*args, **kwargs)
        manager.pool_classes_by_scheme = GUARDED_POOL_CLASSES
        return manager


class GuardedSession(Session):
    """A session whose http and https connections pass the host policy

    A class and not a helper mounting adapters onto a plain session, because the sessions of
    the registry are often subclasses of the plain one: the bounded preview session of
    `registry.helper.preview` limits timeouts, body size and redirects in its own ``send()``
    and inherits the policy from here. A mounting helper would have been dropped by exactly
    that subclass.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        adapter = GuardedHTTPAdapter()
        self.mount('http://', adapter)
        self.mount('https://', adapter)
