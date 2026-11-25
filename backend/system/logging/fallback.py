"""The log sink of this process, and how loud its absence is.

``MrMap/settings.py`` decides once, at import, whether the syslog handler of
the application attaches: it looks the receiver up (``MRMAP_SYSLOG_HOST`` /
``MRMAP_SYSLOG_PORT``, by default the ``victoria-logs`` service of the compose
stack) and skips the handler when the lookup fails. That is the fallback the
lightweight mode of #1614 relies on - the core starts and logs to its console
without the observability tier - and it is also the shape of a real failure: a
deployment which *means* to ship its structured logs but starts its backend
before the store takes the same silent path and loses every syslog record of
the process for its whole lifetime.

So the absence answers with a warning and not with a bare line on stdout
(#1622). ``print`` is kept, because that is what the deployment documentation
quotes and what an operator of a container without a configured warning filter
sees; the warning is what a test runner, a warnings filter and the check
framework see. Both name the receiver it could not reach, because "no sink" is
only actionable together with "for which address".
"""
import socket
from warnings import warn

#: the receiver of the compose stack, as documented in the installation guide
DEFAULT_SYSLOG_HOST = "victoria-logs"
DEFAULT_SYSLOG_PORT = 5514


def syslog_reachable(host, port):
    """True when an RFC 5424 receiver can be addressed at ``host``:``port``.

    A DNS lookup only, never a packet: the UDP handler itself reports nothing
    when it sends into a void, which is why the decision has to be made here,
    once, before the first record.
    """
    try:
        socket.getaddrinfo(host, port, proto=socket.IPPROTO_UDP)
    except socket.gaierror:
        return False
    return True


def warn_without_syslog(host, port):
    """State, loudly and once, that this process has no structured log sink.

    The first two sentences are the documented line of the installation guide
    and of :ref:`compose-profiles` - kept verbatim, and repeated by the
    ``print``, so an operator greps the same sentence whichever of the two
    outputs their tooling shows them. The rest names the receiver, because "no
    sink" is only actionable together with "for which address".
    """
    print("syslog server is not reachable. skipping syslog handler setup.")
    warn(
        message=(
            "syslog server is not reachable. skipping syslog handler setup. "
            f"No receiver at {host}:{port}, so the structured logs of this "
            "process reach its console only and the per request dumps of the "
            "rfc5424 formatter are not written. This is the expected fallback "
            "without the observability tier of docker-compose.lightweight.yml "
            "(#1614); on a deployment which wants central logs it means the "
            "store is down or the backend started before it "
            "(MRMAP_SYSLOG_HOST / MRMAP_SYSLOG_PORT, "
            "docs/source/development/compose-profiles.rst)."),
        category=RuntimeWarning,
        stacklevel=2,
    )
