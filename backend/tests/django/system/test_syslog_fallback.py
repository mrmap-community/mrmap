"""The fallback of the log sink of #1614/#1622, and how loud it is.

``MrMap/settings.py`` answers a missing syslog receiver with the console-only
fallback the lightweight mode depends on. Two things must stay true about it:
the decision is a DNS lookup and nothing else (a UDP probe would block the
import of every process, and a send into a void reports nothing), and the
absence is *said* - the documented line plus a warning, so a deployment which
means to ship structured logs but lost its sink cannot pass for a lightweight
one.
"""
import socket
import warnings
from unittest.mock import patch

from django.test import SimpleTestCase

from system.logging.fallback import (
    DEFAULT_SYSLOG_HOST, DEFAULT_SYSLOG_PORT, syslog_reachable,
    warn_without_syslog)

# the sentence the installation guide and compose-profiles.rst quote, and which
# an operator greps a container log for
DOCUMENTED_LINE = "syslog server is not reachable. skipping syslog handler setup."


def fake_getaddrinfo(resolvable):
    """A ``socket.getaddrinfo`` which resolves only what ``resolvable`` lists."""
    def resolve(host, port, proto=0):
        if host in resolvable:
            return [(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP,
                     "", ("10.0.0.9", port))]
        raise socket.gaierror("Name or service not known")
    return resolve


class SyslogReachableTests(SimpleTestCase):
    def test_a_receiver_which_resolves_is_reachable(self):
        with patch("system.logging.fallback.socket.getaddrinfo",
                   fake_getaddrinfo({DEFAULT_SYSLOG_HOST})):
            self.assertTrue(syslog_reachable(DEFAULT_SYSLOG_HOST,
                                             DEFAULT_SYSLOG_PORT))

    def test_a_receiver_which_does_not_resolve_is_unreachable(self):
        with patch("system.logging.fallback.socket.getaddrinfo",
                   fake_getaddrinfo(set())):
            self.assertFalse(syslog_reachable("no-such-log-store", 5514))

    def test_the_lookup_is_udp_and_names_the_port_it_was_asked_for(self):
        seen = []

        def resolve(host, port, proto=0):
            seen.append((host, port, proto))
            return [(2, 2, socket.SOCK_DGRAM, "", ("10.0.0.9", port))]

        with patch("system.logging.fallback.socket.getaddrinfo", resolve):
            syslog_reachable("store", 5515)
        self.assertEqual(seen, [("store", 5515, socket.IPPROTO_UDP)])

    def test_defaults_are_the_compose_service_of_the_installation_guide(self):
        self.assertEqual(DEFAULT_SYSLOG_HOST, "victoria-logs")
        self.assertEqual(DEFAULT_SYSLOG_PORT, 5514)


class WarnWithoutSyslogTests(SimpleTestCase):
    def test_the_documented_line_is_printed_and_the_warning_is_raised(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with patch("builtins.print") as printed:
                warn_without_syslog("victoria-logs", 5514)
        printed.assert_called_once_with(DOCUMENTED_LINE)
        self.assertEqual(len(caught), 1)
        self.assertIs(caught[0].category, RuntimeWarning)
        self.assertIn(DOCUMENTED_LINE, str(caught[0].message))

    def test_the_warning_names_the_receiver_it_could_not_reach(self):
        """Without the address the message is not actionable: the lightweight
        mode and a broken deployment look identical until it is named."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with patch("builtins.print"):
                warn_without_syslog("logstore.internal", 6514)
        text = str(caught[0].message)
        self.assertIn("logstore.internal:6514", text)
        self.assertIn("MRMAP_SYSLOG_HOST", text)
        self.assertIn("compose-profiles", text)

    def test_a_deployment_which_wants_logs_is_told_so_explicitly(self):
        """The acceptance line of #1622: the fallback may not read as if
        warnings had been dropped silently."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with patch("builtins.print"):
                warn_without_syslog(DEFAULT_SYSLOG_HOST, DEFAULT_SYSLOG_PORT)
        text = str(caught[0].message)
        self.assertIn("expected fallback", text)
        self.assertIn("wants central logs", text)
