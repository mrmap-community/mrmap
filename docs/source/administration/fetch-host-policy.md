# Fetch host policy

Whoever may register a service decides where the Mr.Map backend connects. The service URL of a
registration, the operation URLs and the ``onlineResource`` link of an upstream capabilities
document, the metadata reference of a harvest and the redirect target of any of them are all
written by someone else and fetched by this backend from inside its own network. Without a host
policy, one typed URL is enough to make the backend read an internal endpoint it should not
reach, and the response of that request is echoed back into stored metadata.

The backend therefore judges **the address it is about to connect to** for every server-side
fetch. This page describes the two variables which configure that, and how to open the policy
again for a deployment whose services live in the own network.

## The two variables

| Variable | Meaning |
| --- | --- |
| ``MRMAP_FETCH_ALLOW_NETWORKS`` | CIDRs which are granted even though the default refuses them. |
| ``MRMAP_FETCH_DENY_NETWORKS`` | CIDRs which are refused even though the default, or a grant, allows them. |

Both are lists of CIDRs separated by ``,`` or ``;``, for example:

```bash
MRMAP_FETCH_ALLOW_NETWORKS="10.20.0.0/16, 2001:0db8:1::/48"
MRMAP_FETCH_DENY_NETWORKS="10.20.30.40/32"
```

``docker-compose.yml`` passes both to ``backend``, ``celery-worker`` and ``celery-beat``, so
setting them in the ``.env`` of the deployment is enough: every process which fetches reads the
same policy.

A deny entry always wins over an allow entry, and an allow entry always wins over the default
ranges. An entry which cannot be parsed as a CIDR is ignored with a warning naming it, rather
than breaking every fetch of the deployment.

## What the default refuses

With both variables empty, a fetch is granted only to a **public** address. Refused is every
address of a range reserved for something else than a public service:

- loopback, including the whole ``127.0.0.0/8`` and ``::1``
- the private ranges ``10.0.0.0/8``, ``172.16.0.0/12``, ``192.168.0.0/16`` and ``fc00::/7``
- link-local (``169.254.0.0/16``, ``fe80::/10``) and interface-local
- the multicast, reserved and unspecified ranges, and the IETF special-use ranges such as
  ``100.64.0.0/10``, the carrier-grade NAT range a container network or a VPN mesh answers from
- the benchmarking block ``198.18.0.0/15`` and the documentation block ``2001:db8::/32``

The refusal also covers an address hidden inside an IPv6 spelling of itself. A public-looking
address can encode a refused one - the IPv4-mapped ``::ffff:127.0.0.1``, the IPv4-compatible
``::127.0.0.1``, the 6to4 ``2002:7f00:1::``, a NAT64 ``64:ff9b::7f00:1``, or a Teredo address
which carries the peer half inverted - and all of them are judged as the address they carry. A
refused address stays refused in every spelling which encodes it.

Nothing is resolved for the sake of the judgment alone: the answer of a name is judged at the
moment the connection is created, before a socket exists, and that stays true for every hop of a
redirect. A name which answers more than one address is granted only when **every** answer is
granted.

## Opening it for internally hosted services

A deployment which registers services from its own network has to name those networks. That is
the intended way to run Mr.Map inside a company network, so this is a configuration decision and
not a bypass:

```bash
# services are served from the service VLAN and from one documented network
MRMAP_FETCH_ALLOW_NETWORKS="10.20.0.0/16, 2001:0db8:1::/48"
```

Grant the narrowest range which covers the services. Where a single host inside a granted range
must stay unreachable while the rest of the range is open, grant the range and deny the host:

```bash
MRMAP_FETCH_ALLOW_NETWORKS="10.20.0.0/16"
MRMAP_FETCH_DENY_NETWORKS="10.20.30.40/32, 169.254.169.254/32"
```

The second line is worth having on its own for any deployment running on a cloud host, because
``169.254.169.254`` answers the instance credentials of that host.

## Proxy deployments

Where a deployment fetches through a proxy, the proxy is the address the backend connects to, so
the proxy has to be reachable under the same policy. A deployment which proxies everything
otherwise gets a refused proxy, unless it names the proxy network:

```bash
MRMAP_FETCH_ALLOW_NETWORKS="10.0.1.7/32"   # the address of the proxy
```

With a *tunneling* proxy, the endpoint behind the tunnel is judged in addition; with a
*forwarding* proxy, only the proxy is judged here, and the endpoint behind it is the
responsibility of that proxy.

## Development and tests

Outside ``MRMAP_PRODUCTION`` the loopback and the private ranges are granted without an entry,
because the development compose stack and the unit tests run exactly there. A production
deployment refuses them, which is why an internally hosted service needs an allow entry even when
it already worked in the development stack.

## What a refusal answers

A refused target is reported as an error of the request it belongs to - an ``OwsExcepion`` naming
the refused URL for a registration, update or harvest, a failed monitoring result for a probe -
and the URL is never fetched. The log line names the policy:

```
mrmap.fetch: <address> refused by the host policy of URL <url>
```

The implementation is ``backend/extras/ssrf.py`` (``GuardedSession``). Every server-side fetch of
an address which came from a user or from an upstream document uses it.
