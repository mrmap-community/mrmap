import difflib
import hashlib
from datetime import timedelta
from io import BytesIO

from django.contrib.gis.db import models
from django.utils.translation import gettext_lazy as _
from django_celery_results.models import TaskResult
from lxml import objectify
from lxml.etree import ParseError
from PIL import Image, UnidentifiedImageError
from registry.models.service import Layer, WebMapService
from registry.settings import MONITORING_REQUEST_TIMEOUT
from requests import Request
from requests.exceptions import ConnectTimeout, ReadTimeout, RequestException


class MonitoringResult(models.Model):
    task_result: TaskResult = models.OneToOneField(
        to=TaskResult,
        on_delete=models.CASCADE,
        related_name="%(class)s_monitoring_results",
        related_query_name="%(class)s_monitoring_result",
        editable=False,
        verbose_name=_("Task Result"),
        help_text=_("The result of the celery task"))
    status_code: int = models.IntegerField(
        editable=False,
        default=0,
        verbose_name=_("HTTP status code"),
        help_text=_("The http status code of the response"))
    error_msg: str = models.TextField(
        null=True,
        blank=True,
        editable=False,
        verbose_name=_("error message"),
        help_text=_("The error message of the http response or other error description"))
    monitored_uri: str = models.URLField(
        max_length=4096,
        editable=False,
        verbose_name=_("monitored uri"),
        help_text=_("This is the url which was monitored"))
    request_duration: timedelta = models.DurationField(
        null=True,
        blank=True,
        editable=False,
        verbose_name=_("request duration"),
        help_text=_("elapsed time of the request"))

    response = None

    class Meta:
        abstract = True
        ordering = ['-task_result__date_done', ]
        get_latest_by = ('task_result__date_done')

    def check_url(self, service: WebMapService, url):
        try:
            self.monitored_uri = url
            self.response = service.client.send_request(
                request=Request(method="GET", url=url), timeout=MONITORING_REQUEST_TIMEOUT)
            self.status_code = self.response.status_code
            if self.status_code != 200:
                self.error_msg = self.response.text
        except ConnectTimeout:
            self.status_code = 900
            self.error_msg = "The request timed out in {MONITORING_REQUEST_TIMEOUT} seconds while trying to connect to the remote server."
        except ReadTimeout:
            self.status_code = 901
            self.error_msg = f"The server did not send any data in the allotted amount of time ({MONITORING_REQUEST_TIMEOUT} seconds)."
        except RequestException as exception:
            self.status_code = self.response.status_code if self.response.status_code else 902
            self.error_msg = str(exception)
        finally:
            self.request_duration = self.response.elapsed if self.response else None

    def check_service_exception(self):
        try:
            xml = objectify.fromstring(xml=self.response.content)
            if hasattr(xml, "ServiceExceptionReport") or hasattr(xml, "ServiceException"):
                self.error_msg = self.response.text
                return True
            else:
                return False
        except ParseError:
            return False


class OgcServiceGetCapabilitiesResult(MonitoringResult):
    needs_update: bool = models.BooleanField(
        default=False,
        editable=False,
        verbose_name=_("needs update"),
        help_text=_("signals if the ogc capabilities document has any changes"))

    class Meta(MonitoringResult.Meta):
        abstract = True

    def get_document_diff(self, new_document: str, original_document: str):
        """Computes the diff between two documents.

        Compares the currently stored document and compares its hash to the one
        in the response of the latest check.

        Args:
            new_document (str): Document of last request.
            original_document (bytes): Original document.
        Returns:
            str: The diff of the two documents, if hashes have differences
            None: If the hashes have no differences
        """
        new_capabilities_hash = hashlib.sha256(
            new_document.encode("UTF-8")).hexdigest()
        original_document_hash = hashlib.sha256(
            original_document.encode("UTF-8")).hexdigest()
        if new_capabilities_hash == original_document_hash:
            return
        else:
            original_lines = original_document.splitlines(keepends=True)
            new_lines = new_document.splitlines(keepends=True)
            # info on the created diff on https://docs.python.org/3.6/library/difflib.html#difflib.unified_diff
            diff = difflib.unified_diff(original_lines, new_lines)
            return diff

    def run_checks(self):
        self.check_url(service=self.service,
                       url=self.service.client.prepare_get_capabilitites_request().url)
        if self.check_service_exception():
            return
        if self.status_code == 200:
            diff_obj = self.get_document_diff(
                self.response.text,
                self.service.xml_backup_string)
            if diff_obj:
                self.needs_update = True


class WMSGetCapabilitiesResult(OgcServiceGetCapabilitiesResult):
    service: WebMapService = models.ForeignKey(
        to=WebMapService,
        on_delete=models.CASCADE,
        related_name="monitoring_results",
        related_query_name="monitoring_result",
        verbose_name=_("web map service"),
        help_text=_("this is the service which shall be monitored"))

    class Meta(OgcServiceGetCapabilitiesResult.Meta):
        # Inheritate meta
        pass


class LayerGetMapResult(MonitoringResult):
    layer: Layer = models.ForeignKey(
        to=Layer,
        on_delete=models.CASCADE,
        related_name="get_map_monitoring_results",
        related_query_name="get_map_monitoring_result",
        verbose_name=_("layer"),
        help_text=_("this is the layer which shall be monitored"))

    class Meta(MonitoringResult.Meta):
        # Inheritate meta
        pass

    def check_image(self):
        try:
            Image.open(BytesIO(self.response.content))
        except UnidentifiedImageError:
            self.error_msg = "Could not create image from response."

    def run_checks(self):
        self.check_url(service=self.layer.service,
                       url=self.layer.get_map_url())
        if self.check_service_exception():
            return
        if self.status_code == 200:
            self.check_image()


class LayerGetFeatureInfoResult(MonitoringResult):
    layer: Layer = models.ForeignKey(
        to=Layer,
        on_delete=models.CASCADE,
        related_name="get_feature_info_monitoring_results",
        related_query_name="get_feature_info_monitoring_result",
        verbose_name=_("layer"),
        help_text=_("this is the layer which shall be monitored"))

    class Meta(MonitoringResult.Meta):
        # Inheritate meta
        pass

    def run_checks(self):
        self.check_url(service=self.layer.service,
                       url=self.layer.get_feature_info_url())
        if self.check_service_exception():
            return
