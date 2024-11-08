import difflib
import hashlib
from datetime import timedelta
from io import BytesIO
from typing import List

from django.contrib.gis.db import models
from django.contrib.gis.db import models as gis_models
from django.contrib.postgres.fields import ArrayField, IntegerRangeField
from django.db import transaction
from django.db.models.fields import BooleanField, CharField
from django.utils.translation import gettext_lazy as _
from django_celery_beat.models import IntervalSchedule, PeriodicTask
from django_celery_results.models import TaskResult
from lxml import objectify
from lxml.etree import ParseError
from PIL import Image, UnidentifiedImageError
from registry.models.metadata import MimeType, ReferenceSystem
from registry.models.service import Layer, WebMapService
from registry.settings import MONITORING_REQUEST_TIMEOUT
from requests import Request, Response
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

    # def check_url(self, service: WebMapService, url):
    #     try:
    #         self.monitored_uri = url
    #         self.response = service.client.send_request(
    #             request=Request(method="GET", url=url), timeout=MONITORING_REQUEST_TIMEOUT)
    #         self.status_code = self.response.status_code
    #         if self.status_code != 200:
    #             self.error_msg = self.response.text
    #     except ConnectTimeout:
    #         self.status_code = 900
    #         self.error_msg = "The request timed out in {MONITORING_REQUEST_TIMEOUT} seconds while trying to connect to the remote server."
    #     except ReadTimeout:
    #         self.status_code = 901
    #         self.error_msg = f"The server did not send any data in the allotted amount of time ({
    #             MONITORING_REQUEST_TIMEOUT} seconds)."
    #     except RequestException as exception:
    #         self.status_code = self.response.status_code if self.response.status_code else 902
    #         self.error_msg = str(exception)
    #     finally:
    #         self.request_duration = self.response.elapsed if self.response else None

    # def check_service_exception(self):
    #     try:
    #         xml = objectify.fromstring(xml=self.response.content)
    #         if hasattr(xml, "ServiceExceptionReport") or hasattr(xml, "ServiceException"):
    #             self.error_msg = self.response.text
    #             return True
    #         else:
    #             return False
    #     except ParseError:
    #         return False


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
                       url=self.service.client.get_capabilitites_request().url)
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


class WebMapServiceMonitoringSetting(PeriodicTask):
    service: WebMapService = models.ForeignKey(
        to=WebMapService,
        on_delete=models.CASCADE,
        related_name="web_map_service_monitorings",
        related_query_name="web_map_service_monitoring",
        verbose_name=_("web map service"),
        help_text=_("this is the service which shall be monitored"))

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if not self.task:
            self.task = "registry.tasks.monitoring.run_wms_monitoring"
        if not self.kwargs:
            self.kwargs = {
                "setting_pk": self.pk
            }
        if not self.queue:
            self.queue = "monitoring"


class WebMapServiceMonitoringRun(models.Model):
    setting: WebMapServiceMonitoringSetting = models.ForeignKey(
        to=WebMapServiceMonitoringSetting,
    )
    date_created = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created DateTime'),
        help_text=_('Datetime field when the run was created in UTC'),
        null=True,
        blank=True)
    date_done = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Done DateTime'),
        help_text=_('Datetime field when the run was done in UTC'),
        null=True,
        blank=True)

    def save(self, trigger_run_wms_monitoring=True, *args, **kwargs) -> None:
        ret = super().save(*args, **kwargs)
        if trigger_run_wms_monitoring:
            from registry.tasks.monitoring import run_wms_monitoring
            transaction.on_commit(
                lambda: run_wms_monitoring.apply_async(
                    settings_pk=self.settings.pk,
                    run_pk=self.pk
                )
            )
        return ret


class ProbeResult(models.Model):
    status_code: int = models.IntegerField(
        editable=False,
        null=True,
        blank=True,
        default=None,
        verbose_name=_("HTTP status code"),
        help_text=_("The http status code of the response"))
    success = models.BooleanField(default=False)
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
    date_created = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created DateTime'),
        help_text=_('Datetime field when the task result was created in UTC'))
    date_done = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Completed DateTime'),
        help_text=_('Datetime field when the task was completed in UTC'))

    class Meta:
        abstract = True
        ordering = ['-date_done', ]
        get_latest_by = ('date_done')


class WebMapServiceProbeResult(ProbeResult):
    run = models.ForeignKey(
        to=WebMapServiceMonitoringRun,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)ss",
        related_query_name="%(app_label)s_%(class)s",
        verbose_name=_("Run"),
    )

    class Meta(ProbeResult.Meta):
        abstract = True


class GetMapProbeResult(WebMapServiceProbeResult):
    check_response_image_success = BooleanField(
        null=True, blank=True, default=None)
    check_response_image_message = models.TextField(
        null=True, blank=True, default=None)

    check_response_does_not_contain_success = BooleanField(
        null=True, blank=True, default=None)
    check_response_does_not_contain_message = models.TextField(
        null=True, blank=True, default=None)

    class Meta(WebMapServiceProbeResult):
        # Inheritate meta
        pass


class Probe(models.Model):
    timeout = models.IntegerField(
        default=30,
        blank=True,
    )

    class Meta:
        abstract = True


class WebMapServiceProbe(Probe):
    settings = models.ForeignKey(
        to=WebMapServiceMonitoringSetting,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s",
        related_query_name="%(app_label)s_%(class)ss",
        verbose_name=_("Run"),
    )

    class Meta:
        abstract = True


class GetCapabilititesProbe(WebMapServiceProbe):
    check_response_is_valid_xml = BooleanField()
    check_response_does_not_contain = ArrayField(
        base_field=CharField(
            max_length=256
        ),
        default=["ExceptionReport>", "ServiceException>"]
    )
    check_response_does_contain = ArrayField(
        base_field=CharField(
            max_length=256
        ),
        default=["Title>", "Abstract>"]
    )


class GetMapProbe(WebMapServiceProbe):
    layers: List[Layer] = models.ManyToManyField(
        to=Layer
    )
    format = models.ForeignKey(
        to=MimeType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    reference_system = models.ForeignKey(
        to=ReferenceSystem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    height = models.IntegerField(default=256)
    width = models.IntegerField(default=256)
    bbox_lat_lon = gis_models.PolygonField(
        null=True,  # to support inherited bbox from ancestor layer null=True
        blank=True,
        verbose_name=_("bounding box"),
    )

    check_response_is_image = BooleanField()
    check_response_does_not_contain: List[str] = ArrayField(
        base_field=CharField(
            max_length=256
        ),
        default=["ExceptionReport>", "ServiceException>",
                 "ServiceExceptionReport>"]
    )

    def check_is_image(self, response: Response):
        try:
            Image.open(BytesIO(response.content))
            self.result.check_response_image_success = True
            self.result.check_response_image_message = "OK"
        except UnidentifiedImageError:
            self.result.check_response_image_success = False
            self.result.check_response_image_message = "Could not create image from response."

    def check_does_not_contain(self, response: Response):
        for string in self.check_does_not_contain:
            if response.text.find(string) != -1:
                self.result.check_response_does_not_contain_success = False
                self.result.check_response_does_not_contain_message += f"{
                    string} is part of the response. "

        if self.result.check_response_does_not_contain_success is not False:
            self.result.check_response_does_not_contain_success = True
            self.result.check_response_does_not_contain_message = "OK"

    def run_checks(self, run: WebMapServiceMonitoringRun) -> GetMapProbeResult:
        result = GetMapProbeResult.objects.create(run=run)
        self.result = result
        self.save()
        try:
            client = self.monitoring.service.client
            request = client.get_map_request(
                layers=[layer.identifier for layer in self.layers],
                crs=str(self.reference_system),
                height=self.height,
                width=self.width,
                format=str(self.format) if self.format else "image/png",
                bbox=(),  # TODO: get inherited bbox from most parent layer
            )

            response = client.send_request(
                request=request, timeout=self.timeout)

            if response.status_code != 200:
                result.error_msg = response.text
            result.status_code = response.status_code

            if self.check_response_is_image:
                self.check_is_image(response=response)

            if self.check_response_does_not_contain:
                self.check_does_not_contain(response=response)

        except ConnectTimeout:
            result.message = f"The request timed out in {self.timeout} seconds while trying to connect to the remote server."  # noqa
        except ReadTimeout:
            self.error_msg = f"The server did not send any data in the allotted amount of time ({self.timeout} seconds)."  # noqa
        except RequestException as exception:
            self.status_code = response.status_code if response.status_code else None
            self.error_msg = str(exception)
        finally:
            result.monitored_uri = response.url
            result.request_duration = response.elapsed if response else None
        result.save()
        return result
