"""Host policy for every server-side fetch of a URL somebody else wrote (#1474, SEC-16).

A service URL is user input: it is typed at registration, and every upstream capabilities
document and metadata reference rewrites it. Before this module nothing but the timeouts
bounded *where* such a URL made the backend connect, so whoever may register a service could
aim the backend at an internal endpoint - the cloud metadata service at 169.254.169.254, the
docker socket API, the database - and read the answer back as a metadata document, a preview
map or the detail of an error response.

The policy is deliberately not a blanket ban; hosting a service inside the own network is a
normal Mr.Map deployment. It answers one question per address, in this order:

``MRMAP_FETCH_DENY_NETWORKS``
    an explicit fence of the deployment wins over everything else.
``MRMAP_FETCH_ALLOW_NETWORKS``
    an explicit grant wins over the default ranges. It is the one and only way a refused
    range is ever reached, so there is exactly one way to open the policy and it is an entry
    somebody has to write down. ``0.0.0.0/0`` and ``::/0`` together are the documented way
    to switch the policy off for a deployment which is its own network. Outside production
    the loopback and private ranges are granted as well, see `_development_allowance()`.
the default ranges
    every address of the IANA special-purpose registry which is not routable on the public
    internet: loopback, private, unique-local, link-local, the IPv4 carrier-grade NAT range,
    multicast, reserved, unspecified, the benchmarking block of RFC 2544 and the
    documentation blocks. Everything else is a public address and is allowed. A public
    address keeps its verdict in every spelling; an address of a refused range is refused in
    every spelling which encodes it, see `_embedded`.

For a URL carrying an IP literal that verdict is final and `host_is_allowed` answers it
without touching DNS. For a host name `host_is_allowed` answers True - a name is not an
address, and what it means is decided at the moment of connecting - and the transport answers
the same question for **every** address the name resolves to, at the moment the connection to
it is created. That is the only place a DNS rebinding answer is still caught: the second
lookup may answer differently from the first, and a pooled socket may be older than any
check. It also means a refused address is never connected to at all: the lookup is judged
before the socket is created.

Through a proxy both ends are judged: the proxy as the peer, and - for a tunneling proxy -
the tunnel target as the endpoint. A *forwarding* proxy is judged as the peer only; it is the
deployment's own choice, and the endpoint behind it is judged by that proxy.

A refusal is raised as ``requests.exceptions.ConnectionError``, the error every caller which
already copes with an unreachable endpoint catches: a refused endpoint reads as unreachable,
which is what the operator sees and what the registration reports.

The semantics of this module and its settings are documented in ``POLICY_DOC``.
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

#: where the semantics below are described for the person who configures them
POLICY_DOC = "docs/source/administration/fetch-host-policy.md"

#: the benchmarking block of RFC 2544, which no service is served from and whose absence from
#: ``is_private`` is the one gap the default ranges would otherwise leave open
BENCHMARKING = ipaddress.ip_network('198.18.0.0/15')
#: the carrier-grade NAT range of RFC 6598: what a Tailscale network and the IPv4 fabric of a
#: provider answer from, where an internal-only service of the *infrastructure* lives. It is
#: deliberately not global and therefore not ``is_private``, but it is refused the same way.
CARRIER_GRADE_NAT = ipaddress.ip_network('100.64.0.0/10')
#: the documentation block of RFC 3849, which sits *inside* the Teredo prefix and must not be
#: decoded as one
DOCUMENTATION_V6 = ipaddress.ip_network('2001:db8::/32')
#: the prefixes which carry an IPv4 address inside an IPv6 one, as ``(prefix, offset,
#: inverted)``: every address of one of them is judged as the address it carries too, see
#: `_embedded` and `address_is_allowed`
EMBEDDING_PREFIXES = (
    (ipaddress.ip_network('2002::/16'), 2, False),        # 6to4
    (ipaddress.ip_network('64:ff9b::/96'), 12, False),    # NAT64 well known prefix
    (ipaddress.ip_network('::ffff:0:0/96'), 12, False),   # IPv4 mapped
    (ipaddress.ip_network('::/96'), 12, False),           # IPv4 compatible
    (ipaddress.ip_network('2001::/32'), 4, True),         # Teredo, server half inverted
)


def _development_allowance():
    """The ranges a deployment outside production may fetch from without being granted

    The unit tests of the registry run against loopback listeners and the services of the
    development compose stack reach each other by name over the private network of the stack.
    Both are refused by the default ranges, which are the ranges of a deployment serving the
    public web - which a development stack is not. So its own ranges are granted while
    ``MRMAP_PRODUCTION`` is off, and only then: a production deployment refuses them, and an
    internally hosted service needs a ``MRMAP_FETCH_ALLOW_NETWORKS`` entry there.
    """
    if getattr(settings, 'MRMAP_PRODUCTION', True):
        return []
    return ['127.0.0.0/8', '::1/128', '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16',
            'fc00::/7']


def _networks(entries):
    """The network objects of the given CIDR entries, as a list, with unparseable entries dropped

    The deployment supplies the lists through its environment, which is one string with the
    entries separated by commas; a settings file or a test may as well hand over a list or a
    tuple, so all three spellings mean the same thing.

    A broken entry in a list an operator edits by hand must not break every fetch of the
    deployment. Refusing the addresses that entry would have granted is the price of that,
    and the warning names the entry so the operator finds it.
    """
    if isinstance(entries, str):
        entries = entries.replace(';', ',').split(',')
    networks = []
    for entry in entries or ():
        entry = entry.strip() if isinstance(entry, str) else str(entry)
        if not entry:
            continue
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            logger.warning('mrmap.fetch: ignoring unparseable network %r', entry)
    return networks


def _configured(kind):
    """The parsed networks of one configured list, read from the current configuration

    The allow list always includes `_development_allowance()`; the deny list is exactly what
    the deployment wrote. Read per judged address rather than once at import time: a
    deployment supplies the lists through its environment and a test overrides them with
    ``@override_settings``, neither of which takes effect while something holds an older
    answer. Parsing a handful of CIDRs costs far less than the lookup of the host it judges.
    """
    if kind == 'allow':
        return (_networks(_development_allowance())
                + _networks(getattr(settings, 'MRMAP_FETCH_ALLOW_NETWORKS', None)))
    return _networks(getattr(settings, 'MRMAP_FETCH_DENY_NETWORKS', None))


def _is_public(address):
    """Whether the address is a global address of a range the policy fetches from by default

    ``is_global`` is the answer of the IANA special-purpose registry to exactly this question,
    so it covers loopback, private, unique-local, link-local, the 0/8 block, the carrier-grade
    NAT range, the benchmarking block, the documentation blocks, reserved and unspecified in
    one call and in both families. Multicast is the one range it does *not* cover - a group
    address is routable - and no OGC service is addressed to a group, so it is refused as
    well. The benchmarking block and the carrier-grade NAT range are named as constants above
    because they are the two entries an operator is most likely to ask about: neither is
    ``is_private``, both are refused.
    """
    return (address.is_global and not address.is_multicast
            and address not in BENCHMARKING)


def _embedded(address):
    """The IPv4 address an IPv6 address carries, None for an address which carries none

    ``::ffff:127.0.0.1``, a 6to4 address of ``2002::/16``, a NAT64 address of
    ``64:ff9b::/96`` and the server half of a Teredo address of ``2001::/32`` are how an
    internal address is spelled so that a filter looking at the *text* of a URL does not
    recognise it. The first three carry the address in a readable form at a fixed offset, the
    fourth stores it bitwise inverted. The documentation block is excluded: it lies inside the
    Teredo prefix and names no address at all. Only an address which is refused on its own
    reaches the decoder (see `address_is_allowed`), so a public address never changes its
    verdict through a transition form.

    The *client* half of a Teredo address is obfuscated with a key and is not recovered; what
    is reachable through the relay is the server half.
    """
    if address.version == 4 or address in DOCUMENTATION_V6:
        return None
    for prefix, offset, inverted in EMBEDDING_PREFIXES:
        if address in prefix:
            packed = address.packed[offset:offset + 4]
            if inverted:
                packed = bytes(byte ^ 0xFF for byte in packed)
            return ipaddress.IPv4Address(packed)
    return None


def _forms(address):
    """The address and, for an embedding form, the address it carries

    Both are judged by every rule of the policy, so an entry of either list is understood in
    both spellings and no spelling of an internal address answers as a different question than
    the address itself. An embedding form can therefore never *widen* what is allowed: a
    refused form refuses the whole address.
    """
    embedded = _embedded(address)
    if embedded is None:
        return (address,)
    return (address, embedded)


def address_is_allowed(address):
    """Whether the policy lets a fetch be aimed at the given address

    Args:
        address (ipaddress.IPv4Address | ipaddress.IPv6Address): the address to judge

    Returns:
        bool: True for an allowed address, False for a refused one
    """
    forms = _forms(address)
    deny = _configured('deny')
    if any(form in network for form in forms for network in deny):
        return False
    allow = _configured('allow')
    if any(form in network for form in forms for network in allow):
        return True
    return all(_is_public(form) for form in forms)


def host_is_allowed(host):
    """Whether the policy lets a fetch be aimed at the given host name or IP literal

    A host *name* is answered with True: what the policy judges are the addresses of a name,
    and those are judged by the transport once the lookup is answered (see `check_targets`).
    Only a literal can be judged without a lookup, and that is what makes this usable as a
    serializer validator: a name is never refused here, so no screen becomes slower or
    noisier than the endpoint it validates, and a rebinding answer is still caught.
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


def check_targets(host, port, tunnel=None):
    """Refuse the first target address of a connection which the policy does not allow

    Every address the name resolves to is judged and not only the first: an endpoint which
    answers with one public and one internal address is exactly the rebinding setup this
    guards.

    Args:
        host (str): the host the request names
        port (int): the port the request names
        tunnel (tuple): ``(host, port)`` a tunneling proxy is asked to reach, when it tunnels

    Raises:
        requests.exceptions.ConnectionError: on the first refused target
    """
    targets = _addresses_of(host, port)
    if tunnel:
        targets = targets + _addresses_of(tunnel[0], tunnel[1])
    for address in dict.fromkeys(targets):
        if address is None:
            raise ConnectionError(f'{host}: the host does not resolve to any address.')
        if not address_is_allowed(ipaddress.ip_address(address)):
            raise _refusal(host, address)


class HostPolicyMixin:
    """The host policy of one connection, applied before its socket is created

    A mixin over the urllib3 connection classes rather than a hook on ``Session.send``: a
    response hook runs after the request was written, and an adapter only ever sees the name
    of the prepared request. Both would judge the *intent* of a fetch instead of the
    connection it actually opens, which is the whole point: a name is not an address.
    """

    def _new_conn(self):
        check_targets(self.host, self.port, **self._tunnel_target())
        return super()._new_conn()

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
#: never those of a plain ``requests.Session`` in the same process are judged
GUARDED_POOL_CLASSES = {'http': GuardedHTTPConnectionPool, 'https': GuardedHTTPSConnectionPool}


class GuardedHTTPAdapter(HTTPAdapter):
    """An adapter whose pools create their connections through the host policy

    The pool classes are swapped on the pool manager instead of handed over as a connection
    keyword argument, because urllib3 builds its pool cache key from exactly the keywords it
    knows: an unknown one is a TypeError on the first request instead of a guarded
    connection. The proxy managers get the same swap, which is what judges the proxy itself.
    """

    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)
        self.poolmanager.pool_classes_by_scheme = GUARDED_POOL_CLASSES

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
