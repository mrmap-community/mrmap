"""A probe decodes the body it checks once, not once per searched string (#1620).

``requests.Response.text`` is not cached by the library: every read of the
property decodes the whole content again. A capabilities probe reads it once
per searched string of its ``does contain`` check, once per string of its
``does not contain`` check and once more for the error excerpt of a refusing
service, which put a fresh full copy of a capped multi-megabyte response behind
each of those reads in the worker which runs the probe. The checks read the
decoded body through the probe, which decodes it once per response.

A ``SimpleTestCase``: the checks write onto the result object they are handed
and touch no database, so the probe and its result are unsaved instances.
"""
from types import SimpleNamespace

from django.test import SimpleTestCase

from registry.models.monitoring import GetCapabilitiesProbe
from requests import Response


class CountingResponse(Response):
    """A response whose decoded body counts the decodes behind it."""

    def __init__(self, body, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._body = body
        self._decoded = 0
        self.encoding = "utf-8"

    @property
    def content(self):
        return self._body

    @property
    def text(self):
        self._decoded += 1
        return self._body.decode("utf-8", errors="replace")


class ProbeDecodeOnceTest(SimpleTestCase):

    def _probe(self, **fields):
        probe = GetCapabilitiesProbe(
            check_response_is_valid_xml=False,
            check_response_does_contain="Title>,Abstract>,Keyword>",
            check_response_does_not_contain="ExceptionReport>,ServiceException>")
        for name, value in fields.items():
            setattr(probe, name, value)
        probe.result = SimpleNamespace(
            check_response_does_contain_success=None,
            check_response_does_contain_message="",
            check_response_does_not_contain_success=None,
            check_response_does_not_contain_message="")
        return probe

    def test_the_checked_body_is_decoded_once_for_all_searched_strings(self):
        """Five searched strings, one decode (#1620).

        Before the fix each of the five strings paid its own decode of the
        whole body; the checks of one response now share the first.
        """
        body = b"<Capabilities><Title>t</Title><Abstract>a</Abstract>" \
               b"<Keyword>k</Keyword></Capabilities>"
        response = CountingResponse(body)

        probe = self._probe()
        probe.check_does_contain(response=response)
        probe.check_does_not_contain(response=response)

        self.assertEqual(1, response._decoded,
                         'the contains checks of one response decode its '
                         'body once between them')
        self.assertIs(
            probe.result.check_response_does_contain_success, True)
        self.assertIs(
            probe.result.check_response_does_not_contain_success, True)

    def test_the_answer_of_the_checks_is_the_answer_of_the_decoded_body(self):
        """The shared decode changes what is paid, never what is decided."""
        response = CountingResponse(b"<ServiceExceptionReport>oops</...>")

        probe = self._probe()
        probe.check_does_contain(response=response)
        probe.check_does_not_contain(response=response)

        self.assertIs(probe.result.check_response_does_contain_success, False)
        self.assertIn("Title>", probe.result.check_response_does_contain_message)
        self.assertIs(
            probe.result.check_response_does_not_contain_success, False)
        self.assertIn(
            "ExceptionReport>",
            probe.result.check_response_does_not_contain_message)

    def test_the_error_excerpt_of_a_refusing_service_reuses_the_decode(self):
        """The excerpt of a failing status is read from the same body (#1620)."""
        response = CountingResponse(b"<ServiceExceptionReport>oops</...>")
        probe = self._probe()

        first = probe._response_text(response)
        second = probe._response_text(response)

        self.assertEqual(1, response._decoded,
                         'the excerpt of a refusing service is an excerpt of '
                         'the decode the checks already made')
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("<ServiceExceptionReport>"))

    def test_a_response_which_refuses_the_cache_still_answers_its_text(self):
        """A double which cannot hold the cache decodes per read, as before."""
        class Slotted:
            __slots__ = ("text",)

            def __init__(self, text):
                self.text = text

        probe = self._probe()

        self.assertEqual("body", probe._response_text(Slotted("body")))
