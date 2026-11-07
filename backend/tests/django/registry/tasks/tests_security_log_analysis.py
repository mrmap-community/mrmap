"""The analysis of a response which the security proxy logged.

The request and response logs of the proxy are abstract models with one concrete
model per service type, so the task which analyzes a logged response is told which
model its primary key belongs to: read from the abstract base there is no table at
all, and an abstract model cannot be instantiated (#1153).
"""
import tempfile
from datetime import timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase
from django.utils import timezone
from PIL import Image, ImageDraw
from registry.models.security import (
    WebFeatureServiceAnalyzedResponseLog, WebFeatureServiceHttpRequestLog,
    WebFeatureServiceHttpResponseLog, WebMapServiceAnalyzedResponseLog,
    WebMapServiceHttpRequestLog, WebMapServiceHttpResponseLog)
from registry.models.service import WebFeatureService, WebMapService
from registry.tasks.security import async_analyze_log

WMS_PK = "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"
WFS_PK = "9cc4889d-0cd4-4c3b-8975-58de6d30db41"


def map_image(width=100, height=100, transparent_columns=0):
    """The bytes of a PNG which stands in for the map a service returned.

    ``transparent_columns`` are the columns at the left edge which are fully
    transparent, which is what the analysis counts apart from the whole picture.
    """
    image = Image.new("RGBA", (width, height), (255, 0, 0, 255))
    if transparent_columns:
        ImageDraw.Draw(image).rectangle(
            [0, 0, transparent_columns - 1, height - 1], fill=(0, 0, 0, 0))
    out = BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


class AnalyzeLoggedResponseTest(TestCase):

    fixtures = ["test_users.json", "test_keywords.json", "test_wms.json",
                "test_wfs.json"]

    def setUp(self):
        media_root = tempfile.TemporaryDirectory(prefix="mrmap-log-analysis-")
        self.addCleanup(media_root.cleanup)
        override = self.settings(MEDIA_ROOT=media_root.name)
        override.enable()
        self.addCleanup(override.disable)

    def logged_response(self, response_log_cls, request_log_cls, service,
                        content=None):
        """One logged exchange of the security proxy, with the given response body."""
        request_log = request_log_cls.objects.create(
            timestamp=timezone.now(),
            elapsed=timedelta(seconds=1),
            method="GET",
            url="http://testserver/mrmap-proxy/service",
            headers={},
            service=service,
            user=get_user_model().objects.get(username="User1"),
        )
        response_log = response_log_cls(
            status_code=200,
            reason="OK",
            elapsed=timedelta(seconds=1),
            headers={"content-type": "image/png"},
            url="http://mapserver.example.org/service",
            request=request_log,
        )
        if content is None:
            response_log.save()
        else:
            response_log.content.save(
                name="response.png", content=ContentFile(content))
        return response_log

    def test_the_map_of_a_logged_wms_response_is_analyzed(self):
        response_log = self.logged_response(
            WebMapServiceHttpResponseLog, WebMapServiceHttpRequestLog,
            WebMapService.objects.get(pk=WMS_PK),
            content=map_image(width=100, height=100, transparent_columns=50))

        self.assertTrue(
            async_analyze_log(
                response_log.pk, response_log._meta.label_lower),
            "the logged map was not analyzed")

        analyzed = WebMapServiceAnalyzedResponseLog.objects.get()
        self.assertEqual(response_log, analyzed.response)
        # of the 10000 pixels of the picture, 5000 are transparent
        self.assertEqual(0.005, analyzed.entity_count)
        self.assertEqual(0.01, analyzed.entity_total_count)

    def test_a_logged_response_without_content_is_not_analyzed(self):
        response_log = self.logged_response(
            WebMapServiceHttpResponseLog, WebMapServiceHttpRequestLog,
            WebMapService.objects.get(pk=WMS_PK))

        self.assertFalse(async_analyze_log(
            response_log.pk, response_log._meta.label_lower))
        self.assertEqual(0, WebMapServiceAnalyzedResponseLog.objects.count())

    def test_a_logged_response_which_is_no_map_is_not_analyzed(self):
        # a GetFeatureInfo answers a document, and a remote service which refuses
        # the request answers a report; both are logged but carry no pixels
        response_log = self.logged_response(
            WebMapServiceHttpResponseLog, WebMapServiceHttpRequestLog,
            WebMapService.objects.get(pk=WMS_PK),
            content=b"<ServiceExceptionReport/>")

        self.assertFalse(async_analyze_log(
            response_log.pk, response_log._meta.label_lower))
        self.assertEqual(0, WebMapServiceAnalyzedResponseLog.objects.count())

    def test_the_analysis_of_a_wfs_response_is_handed_its_own_models(self):
        # the analysis of a WFS response is not implemented yet, so nothing is
        # stored -- but the row was read from the model of the WFS and not from a
        # table of another service type (#1153)
        response_log = self.logged_response(
            WebFeatureServiceHttpResponseLog,
            WebFeatureServiceHttpRequestLog,
            WebFeatureService.objects.get(pk=WFS_PK),
            content=b"<wfs:FeatureCollection/>")

        self.assertFalse(async_analyze_log(
            response_log.pk, response_log._meta.label_lower))
        self.assertEqual(
            0, WebFeatureServiceAnalyzedResponseLog.objects.count())
        # the response which was read is the one of the WFS
        self.assertEqual(
            response_log,
            WebFeatureServiceHttpResponseLog.objects.get(request__service__pk=WFS_PK))
