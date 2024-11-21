from datetime import timedelta
from io import BytesIO
from typing import List

from django.contrib.gis.db import models
from django.contrib.gis.db import models as gis_models
from django.contrib.gis.geos import Polygon
from django.contrib.postgres.fields import ArrayField
from django.db import transaction
from django.db.models.fields import BooleanField, CharField
from django.utils.translation import gettext_lazy as _
from django_celery_beat.models import PeriodicTask
from django_celery_results.models import GroupResult, TaskResult
from epsg_cache.utils import adjust_axis_order
from lxml import etree
from PIL import Image, UnidentifiedImageError
from registry.models.metadata import MimeType, ReferenceSystem
from registry.models.service import Layer, WebMapService
from requests import Response
from requests.exceptions import ConnectTimeout, ReadTimeout, RequestException


def get_title_abstract_default():
    return list(["Title>", "Abstract>"])


def get_error_exceptions_default():
    return list(["ExceptionReport>", "ServiceException>"])


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
        if not self.pk and not self.task:
            self.task = "registry.tasks.monitoring.run_wms_monitoring"
        if not self.pk and not self.kwargs:
            self.kwargs = {
                "setting_pk": self.pk
            }
        if not self.pk and not self.queue:
            self.queue = "monitoring"


class WebMapServiceMonitoringRun(models.Model):
    setting: WebMapServiceMonitoringSetting = models.ForeignKey(
        to=WebMapServiceMonitoringSetting,
        on_delete=models.PROTECT,

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
    group_result = models.ForeignKey(
        to=GroupResult,
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )

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
    celery_task_result = models.OneToOneField(
        to=TaskResult,
        null=True,
        default=None,
        blank=True,
        editable=False,
        on_delete=models.SET_NULL
    )

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


class GetCapabilitiesProbeResult(WebMapServiceProbeResult):
    check_response_is_valid_xml_success = BooleanField(
        null=True, blank=True, default=None)
    check_response_is_valid_xml_message = models.TextField(
        null=True, blank=True, default=None)

    check_response_does_not_contain_success = BooleanField(
        null=True, blank=True, default=None)
    check_response_does_not_contain_message = models.TextField(
        null=True, blank=True, default=None)

    check_response_does_contain_success = BooleanField(
        null=True, blank=True, default=None)
    check_response_does_contain_message = models.TextField(
        null=True, blank=True, default=None)

    class Meta(WebMapServiceProbeResult.Meta):
        # Inheritate meta
        pass


class GetMapProbeResult(WebMapServiceProbeResult):
    check_response_image_success = BooleanField(
        null=True, blank=True, default=None)
    check_response_image_message = models.TextField(
        null=True, blank=True, default=None)

    check_response_does_not_contain_success = BooleanField(
        null=True, blank=True, default=None)
    check_response_does_not_contain_message = models.TextField(
        null=True, blank=True, default=None)

    class Meta(WebMapServiceProbeResult.Meta):
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
    setting = models.ForeignKey(
        to=WebMapServiceMonitoringSetting,
        on_delete=models.CASCADE,
        related_name='%(app_label)s_%(class)ss',
        related_query_name='%(app_label)s_%(class)s',
        verbose_name=_('Setting'),
        help_text=_('The related setting object')
    )

    check_response_does_not_contain = ArrayField(
        base_field=CharField(
            max_length=256
        ),
        default=get_error_exceptions_default
    )

    class Meta:
        abstract = True

    def check_does_not_contain(self, response: Response):
        self.result.check_response_does_not_contain_message = ""
        for string in self.check_response_does_not_contain:
            if response.text.find(string) > -1:
                self.result.check_response_does_not_contain_success = False
                self.result.check_response_does_not_contain_message += f"{string} is part of the response. "  # noqa

        if self.result.check_response_does_not_contain_success is not False:
            self.result.check_response_does_not_contain_success = True
            self.result.check_response_does_not_contain_message = "OK"


class GetCapabilitiesProbe(WebMapServiceProbe):
    check_response_is_valid_xml = BooleanField(default=True)

    check_response_does_contain = ArrayField(
        base_field=CharField(
            max_length=256
        ),
        default=get_title_abstract_default
    )

    def check_does_contain(self, response: Response):
        self.result.check_response_does_contain_message = ""
        for string in self.check_response_does_contain:
            if response.text.find(string) < 0:
                self.result.check_response_does_contain_success = False
                self.result.check_response_does_contain_message += f"{string} is not part of the response. "  # noqa

        if self.result.check_response_does_contain_success is not False:
            self.result.check_response_does_contain_success = True
            self.result.check_response_does_contain_message = "OK"

    def check_is_valid_xml(self, response: Response):
        try:
            etree.fromstring(response.content)
            self.result.check_response_is_valid_xml_success = True
            self.result.check_response_is_valid_xml_message = "OK"
        except Exception as e:
            self.result.check_response_is_valid_xml_success = False
            self.result.check_response_is_valid_xml_message = f"response is not a valide xml. {e}"  # noqa

    def run_checks(self, run: WebMapServiceMonitoringRun, celery_task_result: TaskResult, *args, **kwargs) -> GetMapProbeResult:
        result = GetCapabilitiesProbeResult.objects.create(
            run=run,
            celery_task_result=celery_task_result
        )
        self.result = result
        self.save()
        try:
            client = self.settings.service.client
            request = client.get_capabilitites_request()
            result.monitored_uri = request.url

            response = client.send_request(
                request=request, timeout=self.timeout)

            if response.status_code != 200:
                result.error_msg = response.text
            result.status_code = response.status_code

            if self.check_response_is_valid_xml:
                self.check_is_valid_xml(response=response)

            if self.check_response_does_contain:
                self.check_does_contain(response=response)

            if self.check_response_does_not_contain:
                self.check_does_not_contain(response=response)

            result.monitored_uri = response.url
            result.request_duration = response.elapsed if response else None

        except ConnectTimeout:
            result.message = f"The request timed out in {self.timeout} seconds while trying to connect to the remote server."  # noqa
        except ReadTimeout:
            self.error_msg = f"The server did not send any data in the allotted amount of time ({self.timeout} seconds)."  # noqa
        except RequestException as exception:
            self.status_code = response.status_code if response.status_code else None
            self.error_msg = str(exception)
        finally:
            result.save()
        return result


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

    check_response_is_image = BooleanField(default=True)

    def check_is_image(self, response: Response):
        try:
            Image.open(BytesIO(response.content))
            self.result.check_response_image_success = True
            self.result.check_response_image_message = "OK"
        except UnidentifiedImageError:
            self.result.check_response_image_success = False
            self.result.check_response_image_message = "Could not create image from response."

    def run_checks(self, run: WebMapServiceMonitoringRun, celery_task_result: TaskResult, *args, **kwargs) -> GetMapProbeResult:
        result = GetMapProbeResult.objects.create(
            run=run, celery_task_result=celery_task_result)
        self.result = result
        self.save()
        try:
            client = self.settings.service.client
            layers: list[Layer] = self.layers.with_inherited_attributes()
            bbox: Polygon = layers[0].bbox_inherited
            if client.capabilities.service_type.version == "1.3.0":
                bbox = adjust_axis_order(bbox)

            request = client.get_map_request(
                layers=[layer.identifier for layer in self.layers.all()],
                crs=str(self.reference_system),
                # TODO: use configured styles instead
                styles=",".join(["" for layer in layers]),
                height=self.height,
                width=self.width,
                format=str(self.format) if self.format else "image/png",
                bbox=(
                    str(bbox.extent[0]),
                    str(bbox.extent[1]),
                    str(bbox.extent[2]),
                    str(bbox.extent[3])
                )
            )
            result.monitored_uri = request.url

            response = client.send_request(
                request=request, timeout=self.timeout)

            if response.status_code != 200:
                result.error_msg = response.text
            result.status_code = response.status_code

            if self.check_response_is_image:
                self.check_is_image(response=response)

            if self.check_response_does_not_contain:
                self.check_does_not_contain(response=response)

            result.monitored_uri = response.url
            result.request_duration = response.elapsed if response else None

        except ConnectTimeout:
            result.message = f"The request timed out in {self.timeout} seconds while trying to connect to the remote server."  # noqa
        except ReadTimeout:
            self.error_msg = f"The server did not send any data in the allotted amount of time ({self.timeout} seconds)."  # noqa
        except RequestException as exception:
            self.status_code = response.status_code if response.status_code else None
            self.error_msg = str(exception)
        finally:
            result.save()
        return result
