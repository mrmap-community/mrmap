"""The knob which turns the legacy slow-request detector off (#1777).

``system.logging.middleware.LogSlowRequestsMiddleware`` was the one piece of the
legacy technical observability without a switch: it is simply listed in
``MIDDLEWARE``. That left the matched benchmark of #1777 no honest way to read a
"diagnostics off" web tier - the alternative was a second settings module which
``from MrMap.settings import *`` and dropped the entry, i.e. an application
forked away from the one the other arm measures (the finding #1844's Sonar scan
raised on exactly that file). So the removal is a named knob like its task-side
siblings of #1389/#1391/#1401, and the chain a deployment boots is decided by
``_middleware_from_env``.

``SimpleTestCase`` throughout: the decision is a function of two arguments, so
pinning it needs neither a database nor a re-import of the settings module.
"""

from django.conf import settings
from django.test import SimpleTestCase

from MrMap.settings import (
    _flag_from_env,
    _middleware_from_env,
    SLOW_REQUEST_LOGGING_MIDDLEWARE,
)

KNOB = "MRMAP_OBSERVABILITY_SLOW_REQUEST_LOGGING"
DETECTOR = SLOW_REQUEST_LOGGING_MIDDLEWARE


class MiddlewareFromEnvTests(SimpleTestCase):
    """``_middleware_from_env`` keeps the shipped chain and drops the detector."""

    CHAIN = ["a.middleware.A", DETECTOR, "b.middleware.B"]

    def test_on_keeps_the_chain_unchanged(self):
        """The default boots what the list says, in order, detector included."""
        self.assertEqual(_middleware_from_env(self.CHAIN, True), self.CHAIN)

    def test_off_removes_the_detector_and_keeps_the_order_of_the_rest(self):
        self.assertEqual(_middleware_from_env(self.CHAIN, False),
                         ["a.middleware.A", "b.middleware.B"])

    def test_off_is_idempotent_and_leaves_an_absent_detector_absent(self):
        """Turning off a chain which never had it must not invent one."""
        without = [entry for entry in self.CHAIN if entry != DETECTOR]
        self.assertEqual(_middleware_from_env(without, False), without)

    def test_the_chain_of_the_deployment_is_a_copy(self):
        """Django may mutate what it loads, the settings list may not drift.

        Without the copy the ``on`` branch hands out ``_MIDDLEWARE_CHAIN``
        itself, so anything which later touches ``settings.MIDDLEWARE`` would
        edit the shipped chain the next call reads.
        """
        returned = _middleware_from_env(self.CHAIN, True)
        returned.append("c.middleware.C")
        self.assertEqual(self.CHAIN, ["a.middleware.A", DETECTOR, "b.middleware.B"])
        self.assertEqual(_middleware_from_env(self.CHAIN, True), self.CHAIN)


class SlowRequestLoggingFlagTests(SimpleTestCase):
    """The knob is spelled like every other flag of that stack."""

    def test_absent_value_keeps_the_shipped_detector(self):
        """No value is no decision: a deployment ships with its diagnostics."""
        self.assertTrue(_flag_from_env({}, KNOB, True))

    def test_a_blank_value_is_not_a_decision(self):
        """``NAME=`` in an ``.env`` must not silently drop the detector.

        Blank is what an unset variable looks like once a compose pass-through
        or a CI export has touched it; reading it as off would cost a deployment
        its slow-request dump because nobody wrote a value.
        """
        for blank in ("", "   ", "\t"):
            with self.subTest(value=repr(blank)):
                self.assertTrue(_flag_from_env({KNOB: blank}, KNOB, True))

    def test_the_spelling_of_the_stack_is_honoured_both_ways(self):
        self.assertFalse(_flag_from_env({KNOB: "False"}, KNOB, True))
        self.assertTrue(_flag_from_env({KNOB: "True"}, KNOB, False))

    def test_only_the_one_spelling_reads_as_on(self):
        """Everything but ``"True"`` is off, which is why the bench arm spells it.

        ``bool(value)`` would read ``"0"`` and ``"off"`` as on, so the string
        comparison is the whole of the parsing (#1141). The consequence for this
        knob is that a mistyped value costs the deployment its slow-request dump
        rather than half-enabling a detector, and it is why the arm definition of
        the benchmark writes the exact ``"False"`` its own guard insists on.
        """
        for unrecognised in ("0", "1", "off", "on", "yes", "no", "true", "TRUE"):
            with self.subTest(value=unrecognised):
                self.assertFalse(_flag_from_env({KNOB: unrecognised}, KNOB, True))


class ShippedChainTests(SimpleTestCase):
    """What this runner boots is the shipped chain, detector included.

    The name of the middleware is written in two places - the literal list and
    the constant the filter compares against - and a typo in either would drop
    the detector from every deployment while still reading as configured.
    """

    def test_the_detector_of_the_shipped_chain_is_listed(self):
        chain = list(settings.MIDDLEWARE)
        self.assertIn(DETECTOR, chain,
                      "%s is off this runner although the knob defaults to on" % KNOB)
        self.assertEqual(chain.count(DETECTOR), 1)

    def test_the_detector_is_last_as_it_shipped(self):
        """The position carries the policy, so the filter may not reorder it.

        The dump measures the time the whole request takes, which is what
        everything below it contributes; moving it above the others would make
        the threshold mean something else, and a rebuild which only drops an
        entry has no business changing an order.
        """
        self.assertEqual(list(settings.MIDDLEWARE)[-1], DETECTOR)

    def test_the_other_entries_of_the_shipped_chain_survive_the_knob(self):
        """Removing the detector may not take a neighbour with it.

        Compared against the module's own list rather than a second copy of the
        expected chain, so this fails on a filter which is too wide and not on
        every unrelated edit of the block.
        """
        from MrMap import settings as mrmap_settings

        self.assertEqual(
            _middleware_from_env(mrmap_settings._MIDDLEWARE_CHAIN, False),
            [entry for entry in mrmap_settings._MIDDLEWARE_CHAIN
             if entry != DETECTOR])
        self.assertEqual(len(list(settings.MIDDLEWARE)),
                         len(mrmap_settings._MIDDLEWARE_CHAIN))

    def test_the_knob_is_documented_for_the_stack_it_governs(self):
        """An operator can only set what the reference passes through.

        Compose interpolates ``.env`` only into the entries it declares, so a
        knob which is not named there cannot be set by the operator who follows
        the environment reference. The compose file is one level above the bind
        mount of this suite: absent inside the QA image, present on a checkout,
        where the check is real.
        """
        import pathlib

        compose = (pathlib.Path(__file__).resolve().parents[3]
                   / "docker-compose.yml")
        if not compose.is_file():
            self.skipTest(f"no {compose} on this runner")
        text = compose.read_text(encoding="utf-8")
        self.assertIn(KNOB, text,
                      "%s is never declared, so the documented knob cannot be "
                      "set from .env" % KNOB)
