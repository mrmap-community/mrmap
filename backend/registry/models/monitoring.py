import json
from datetime import timedelta
from io import BytesIO
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from uuid import uuid4

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.db import models
from django.contrib.gis.db import models as gis_models
from django.contrib.gis.geos import Polygon
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models.fields import BooleanField, CharField
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_celery_beat.models import PeriodicTask
from epsg_cache.utils import adjust_axis_order
from extras.scheduling import next_run_expected_at
from lxml import etree
from notify.enums import ProcessNameEnum, ProcessStatusEnum
from PIL import Image, UnidentifiedImageError
from registry.managers.monitoring import MonitoringRunManager
from registry.models.metadata import MimeType, ReferenceSystem
from registry.models.service import (CatalogueService, FeatureType, Layer,
                                     WebFeatureService, WebMapService)
from requests import Request, Response
from requests.exceptions import ConnectTimeout, ReadTimeout, RequestException

#: content types whose response body a probe keeps as an artifact of the
#: execution (#682). Everything else stays out of the storage on purpose:
#: the artifact endpoint serves what it stores inline and a stored document
#: must never carry active content, so html, svg and unknown types are not
#: kept even though their size would fit
STORED_RESPONSE_CONTENT_TYPES = frozenset({
    "image/png",
    "image/jpeg",
    "image/gif",
    "application/xml",
    "text/xml",
    "application/gml+xml",
    "application/json",
    "text/plain",
})

#: query parameters whose value names the caller rather than the request;
#: the uri of a probe is answered to the monitoring UI with these values
#: replaced (#682)
SENSITIVE_QUERY_PARAMS = frozenset({
    "token", "apikey", "api_key", "api-key", "key", "password", "passwd",
    "secret", "bearer", "signature",
})


def probe_response_artifact_path(instance, filename):
    """Where the stored response body of one probe result lives.

    The name below the result directory is fixed: nothing derived from a
    remote response - neither its filename nor its content type - reaches the
    path of the storage, the route names the result and the stored content
    type names the body (#682).
    """
    return 'probe_responses/{0}.{1}/{2}/response'.format(
        instance._meta.app_label, instance._meta.model_name, instance.pk)


class MonitoringSettingMixin:
    """Shared behaviour of the monitoring settings of a registered service.

    Concrete settings are based on django_celery_beat's `PeriodicTask` and are
    always bound to one service. The task to create a monitoring run and the
    queue to run it in are configured by the concrete setting.
    """

    #: dotted path of the task which creates a monitoring run for the setting
    MONITORING_TASK = None

    @property
    def next_run_expected_at(self):
        return next_run_expected_at(self)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if not self.pk:
            if not self.task:
                self.task = self.MONITORING_TASK
            if not self.queue:
                self.queue = "monitoring"
            if not self.name:
                self.name = str(uuid4())
            if not self.kwargs or self.kwargs == '{}':
                self.kwargs = json.dumps({
                    "name": str(self.name),
                })


class WebMapServiceMonitoringSetting(MonitoringSettingMixin, PeriodicTask):
    MONITORING_TASK = "registry.tasks.monitoring.create_wms_monitoring_run"

    service: WebMapService = models.ForeignKey(
        to=WebMapService,
        on_delete=models.CASCADE,
        related_name="web_map_service_monitorings",
        related_query_name="web_map_service_monitoring",
        verbose_name=_("web map service"),
        help_text=_("this is the service which shall be monitored"))


class WebFeatureServiceMonitoringSetting(MonitoringSettingMixin, PeriodicTask):
    MONITORING_TASK = "registry.tasks.monitoring.create_wfs_monitoring_run"

    service: WebFeatureService = models.ForeignKey(
        to=WebFeatureService,
        on_delete=models.CASCADE,
        related_name="web_feature_service_monitorings",
        related_query_name="web_feature_service_monitoring",
        verbose_name=_("web feature service"),
        help_text=_("this is the service which shall be monitored"))


class CatalogueServiceMonitoringSetting(MonitoringSettingMixin, PeriodicTask):
    MONITORING_TASK = "registry.tasks.monitoring.create_csw_monitoring_run"

    service: CatalogueService = models.ForeignKey(
        to=CatalogueService,
        on_delete=models.CASCADE,
        related_name="catalogue_service_monitorings",
        related_query_name="catalogue_service_monitoring",
        verbose_name=_("catalogue service"),
        help_text=_("this is the service which shall be monitored"))


class MonitoringRun(models.Model):
    """Baseclass of one monitoring run of a registered service.

    A run is created by the periodic task of a monitoring setting and dispatches
    the execution of its probes as soon as it is created.
    """

    date_created = models.DateTimeField(
        # Do not use this setting.
        # From django docs: Automatically set the field to now when the object is first created.
        # Useful for creation of timestamps. Note that the current date is always used;
        # it’s not just a default value that you can override.
        # So even if you set a value for this field when creating the object, it will be ignored.
        # If you want to be able to modify this field, set the following instead of auto_now_add=True:
        # auto_now_add=True,
        default=now,
        verbose_name=_('Created DateTime'),
        help_text=_('Datetime field when the run was created in UTC'),
        null=True,
        blank=True)
    date_done = models.DateTimeField(
        # Do not use this setting.
        # From django docs: Automatically set the field to now when the object is first created.
        # Useful for creation of timestamps. Note that the current date is always used;
        # it’s not just a default value that you can override.
        # So even if you set a value for this field when creating the object, it will be ignored.
        # If you want to be able to modify this field, set the following instead of auto_now_add=True:
        # auto_now_add=True,
        default=now,
        verbose_name=_('Done DateTime'),
        help_text=_('Datetime field when the run was done in UTC'),
        null=True,
        blank=True)

    objects = MonitoringRunManager()

    background_process = models.ForeignKey(
        to="notify.BackgroundProcess",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        # the field is defined on an abstract base model, so the names of the
        # relations have to be unique per concrete model
        related_name='%(class)s_processes',
        related_query_name='%(class)s_process',
        verbose_name=_('background process'),
        help_text=_('the background process which reports this run'))

    class Meta:
        abstract = True

    def dispatch_run(self) -> None:
        """Dispatch the celery task which executes the probes of this run."""
        raise NotImplementedError

    @classmethod
    def failing_probe_checks(cls) -> dict:
        """Describe the probe results which decide about the success of a run.

        Returns:
            dict: mapping of an annotation name to the result model and the
                query which matches failing results of this kind.
        """
        raise NotImplementedError

    def save(self, *args, **kwargs) -> None:
        adding = self._state.adding
        if adding and self.background_process_id is None:
            self.background_process = self.build_process()
        ret = super().save(*args, **kwargs)
        if adding:
            transaction.on_commit(
                lambda: self.dispatch_run()
            )
        return ret

    def build_process(self):
        """Build the process which reports this run in the background activity.

        Returns:
            BackgroundProcess: a pending process naming the monitored service
        """
        # imported here, because the process only reports this run and is not a
        # part of its result
        from notify.models import BackgroundProcess

        service = self.setting.service if self.setting_id else None
        title = getattr(service, 'title', None)
        return BackgroundProcess.objects.create(
            phase="Background process created",
            process_type=ProcessNameEnum.MONITORING.value,
            description=f"Monitoring of the service {title}"[:512] if title
            else "Monitoring of a registered service",
            related_resource_type=ContentType.objects.get_for_model(service)
            if service else None,
            related_id=service.pk if service else None)

    def report_process(self, status, phase=None, total_steps=None,
                       step_done=False):
        """Mirror the state of this run in the process which reports it.

        Args:
            status (ProcessStatusEnum): the status to report
            phase (str): current phase of the run, optional
            total_steps (int): amount of steps the run is made of, optional
            step_done (bool): whether a step of the run was done, optional

        Returns:
            int: amount of processes which were updated
        """
        from notify.models import BackgroundProcess

        return BackgroundProcess.objects.report(
            self.background_process_id, status, phase=phase,
            total_steps=total_steps, step_done=step_done)

    def fail_process(self, error):
        """Report that the checks of this run cannot be executed at all.

        A probe which raises does not reach the task which finishes a run, so
        without this report the run would stay as running in the overview
        of the background activity although it ended.
        """
        from notify.models import BackgroundProcess

        BackgroundProcess.objects.log(
            self.background_process_id, f"An error occurred: {error}")
        return self.report_process(
            ProcessStatusEnum.FAILED,
            phase=f"An error occurred: {str(error)[:400]}")


class WebMapServiceMonitoringRun(MonitoringRun):
    setting: WebMapServiceMonitoringSetting = models.ForeignKey(
        to=WebMapServiceMonitoringSetting,
        on_delete=models.CASCADE,
    )

    class Meta:
        # the newest run of one service answers its monitoring alerts - the
        # join over the setting leaves the index of this run table sorted for
        # the `ORDER BY date_created DESC LIMIT 1` of the top-N (#1030)
        indexes = [models.Index(fields=["setting", "-date_created"])]

    def dispatch_run(self) -> None:
        from registry.tasks.monitoring import run_wms_monitoring

        run_wms_monitoring.apply_async(args=(self.pk,))

    @classmethod
    def failing_probe_checks(cls) -> dict:
        return {
            "is_get_capabilities_failed": (
                GetCapabilitiesProbeResult,
                models.Q(check_response_is_valid_xml_success=False) |
                models.Q(check_response_does_contain_success=False) |
                models.Q(check_response_does_not_contain_success=False)
            ),
            "is_get_map_failed": (
                GetMapProbeResult,
                models.Q(check_response_image_success=False) |
                models.Q(check_response_does_not_contain_success=False)
            ),
        }


class WebFeatureServiceMonitoringRun(MonitoringRun):
    setting: WebFeatureServiceMonitoringSetting = models.ForeignKey(
        to=WebFeatureServiceMonitoringSetting,
        on_delete=models.CASCADE,
    )

    class Meta:
        # the newest run of one service answers its monitoring alerts - the
        # join over the setting leaves the index of this run table sorted for
        # the `ORDER BY date_created DESC LIMIT 1` of the top-N (#1030)
        indexes = [models.Index(fields=["setting", "-date_created"])]

    def dispatch_run(self) -> None:
        from registry.tasks.monitoring import run_wfs_monitoring

        run_wfs_monitoring.apply_async(args=(self.pk,))

    @classmethod
    def failing_probe_checks(cls) -> dict:
        return {
            "is_get_capabilities_failed": (
                WebFeatureServiceGetCapabilitiesProbeResult,
                models.Q(check_response_is_valid_xml_success=False) |
                models.Q(check_response_does_contain_success=False) |
                models.Q(check_response_does_not_contain_success=False)
            ),
            "is_get_feature_failed": (
                WebFeatureServiceGetFeatureProbeResult,
                models.Q(check_response_is_valid_xml_success=False) |
                models.Q(check_response_does_contain_success=False) |
                models.Q(check_response_does_not_contain_success=False)
            ),
        }


class CatalogueServiceMonitoringRun(MonitoringRun):
    setting: CatalogueServiceMonitoringSetting = models.ForeignKey(
        to=CatalogueServiceMonitoringSetting,
        on_delete=models.CASCADE,
    )

    class Meta:
        # the newest run of one service answers its monitoring alerts - the
        # join over the setting leaves the index of this run table sorted for
        # the `ORDER BY date_created DESC LIMIT 1` of the top-N (#1030)
        indexes = [models.Index(fields=["setting", "-date_created"])]

    def dispatch_run(self) -> None:
        from registry.tasks.monitoring import run_csw_monitoring

        run_csw_monitoring.apply_async(args=(self.pk,))

    @classmethod
    def failing_probe_checks(cls) -> dict:
        return {
            "is_get_capabilities_failed": (
                CatalogueServiceGetCapabilitiesProbeResult,
                models.Q(check_response_is_valid_xml_success=False) |
                models.Q(check_response_does_contain_success=False) |
                models.Q(check_response_does_not_contain_success=False)
            ),
            "is_get_records_failed": (
                CatalogueServiceGetRecordsProbeResult,
                models.Q(check_response_is_valid_xml_success=False) |
                models.Q(check_response_does_contain_success=False) |
                models.Q(check_response_does_not_contain_success=False)
            ),
        }


class ProbeResult(models.Model):
    status_code: int = models.SmallIntegerField(
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
        # Do not use this setting.
        # From django docs: Automatically set the field to now when the object is first created.
        # Useful for creation of timestamps. Note that the current date is always used;
        # it’s not just a default value that you can override.
        # So even if you set a value for this field when creating the object, it will be ignored.
        # If you want to be able to modify this field, set the following instead of auto_now_add=True:
        # auto_now_add=True,
        default=now,
        verbose_name=_('Created DateTime'),
        help_text=_('Datetime field when the task result was created in UTC'))
    date_done = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Completed DateTime'),
        help_text=_('Datetime field when the task was completed in UTC'))

    response_body = models.FileField(
        upload_to=probe_response_artifact_path,
        max_length=1024,
        null=True,
        blank=True,
        editable=False,
        verbose_name=_("response body"),
        help_text=_(
            "the body of the response as the service answered it at "
            "execution time, if it was safe and small enough to keep"))
    response_content_type = models.CharField(
        max_length=256,
        blank=True,
        default="",
        editable=False,
        verbose_name=_("response content type"),
        help_text=_("the content type the service answered with"))
    response_size = models.BigIntegerField(
        null=True,
        blank=True,
        editable=False,
        verbose_name=_("response size"),
        help_text=_("the amount of bytes the response body carried"))
    request_error = models.TextField(
        null=True,
        blank=True,
        editable=False,
        verbose_name=_("request error"),
        help_text=_(
            "the failure which prevented the request from being answered"))
    error_detail = models.TextField(
        null=True,
        blank=True,
        editable=False,
        verbose_name=_("error detail"),
        help_text=_(
            "an excerpt of the body which answered a failed request"))

    class Meta:
        abstract = True
        ordering = ['-date_done', ]
        get_latest_by = ('date_done')

    @property
    def has_response_artifact(self) -> bool:
        """Whether the body of this response is stored as an artifact.

        The stored name answers this; whether the storage still holds the
        file is the question of the artifact endpoint itself (#1150 showed
        that a name without a file happens).
        """
        return bool(self.response_body)

    @property
    def response_artifact_expired(self) -> bool:
        """Whether the retention of the stored artifact has passed.

        The sweep which takes the artifacts back runs on its schedule, so
        between the retention moment and the sweep the artifact is still
        there but already of no use; the artifact endpoint refuses it as
        gone. A retention of 0 keeps the artifacts until an operator
        removes them.
        """
        retention_days = settings.MONITORING_PROBE_RESPONSE_RETENTION_DAYS
        if retention_days <= 0 or not self.has_response_artifact:
            return False
        if self.date_created is None:
            return False
        return self.date_created < now() - timedelta(days=retention_days)

    @property
    def redacted_monitored_uri(self) -> str:
        """The uri which was monitored, without the values which name a caller.

        The uri of a probe is the request an inspector may want to copy; a
        service may carry its credentials in the userinfo of the authority
        or in a query parameter, and those values do not belong into the
        answer of an api (#682).
        """
        if not self.monitored_uri:
            return ""
        parsed = urlparse(self.monitored_uri)
        netloc = parsed.netloc
        if "@" in netloc:
            userinfo, _, host = netloc.rpartition("@")
            user, sep, password = userinfo.partition(":")
            if sep and password:
                # the user may stay to name the account which hit the
                # service, the password never: without the separator there
                # is no secret in the userinfo to hide (#682)
                netloc = f"{user}:***@{host}"
            else:
                netloc = f"{userinfo}@{host}"
        if parsed.query:
            pairs = parse_qsl(parsed.query, keep_blank_values=True)
            query = urlencode([
                (name, "***" if name.lower() in SENSITIVE_QUERY_PARAMS
                 else value)
                for name, value in pairs])
            parsed = parsed._replace(query=query)
        return urlunparse(parsed._replace(netloc=netloc))


class XmlContentCheckResult(models.Model):
    """Mixin of probe results which validate the xml content of a response."""

    check_response_is_valid_xml_success = BooleanField(
        null=True, blank=True, default=None)
    check_response_is_valid_xml_message = models.TextField(
        null=True, blank=True, default=None)

    check_response_does_contain_success = BooleanField(
        null=True, blank=True, default=None)
    check_response_does_contain_message = models.TextField(
        null=True, blank=True, default=None)

    class Meta:
        abstract = True


class ExceptionResponseCheckResult(models.Model):
    """Mixin of probe results which reject error messages in a response."""

    check_response_does_not_contain_success = BooleanField(
        null=True, blank=True, default=None)
    check_response_does_not_contain_message = models.TextField(
        null=True, blank=True, default=None)

    class Meta:
        abstract = True


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


class GetCapabilitiesProbeResult(
        WebMapServiceProbeResult,
        XmlContentCheckResult,
        ExceptionResponseCheckResult):

    class Meta(WebMapServiceProbeResult.Meta):
        # Inheritate meta
        pass


class GetMapProbeResult(
        WebMapServiceProbeResult,
        ExceptionResponseCheckResult):
    check_response_image_success = BooleanField(
        null=True, blank=True, default=None)
    check_response_image_message = models.TextField(
        null=True, blank=True, default=None)

    class Meta(WebMapServiceProbeResult.Meta):
        # Inheritate meta
        pass


class WebFeatureServiceProbeResult(ProbeResult):
    run = models.ForeignKey(
        to=WebFeatureServiceMonitoringRun,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)ss",
        related_query_name="%(app_label)s_%(class)s",
        verbose_name=_("Run"),
    )

    class Meta(ProbeResult.Meta):
        abstract = True


class WebFeatureServiceGetCapabilitiesProbeResult(
        WebFeatureServiceProbeResult,
        XmlContentCheckResult,
        ExceptionResponseCheckResult):

    class Meta(WebFeatureServiceProbeResult.Meta):
        # Inheritate meta
        pass


class WebFeatureServiceGetFeatureProbeResult(
        WebFeatureServiceProbeResult,
        XmlContentCheckResult,
        ExceptionResponseCheckResult):

    class Meta(WebFeatureServiceProbeResult.Meta):
        # Inheritate meta
        pass


class CatalogueServiceProbeResult(ProbeResult):
    run = models.ForeignKey(
        to=CatalogueServiceMonitoringRun,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)ss",
        related_query_name="%(app_label)s_%(class)s",
        verbose_name=_("Run"),
    )

    class Meta(ProbeResult.Meta):
        abstract = True


class CatalogueServiceGetCapabilitiesProbeResult(
        CatalogueServiceProbeResult,
        XmlContentCheckResult,
        ExceptionResponseCheckResult):

    class Meta(CatalogueServiceProbeResult.Meta):
        # Inheritate meta
        pass


class CatalogueServiceGetRecordsProbeResult(
        CatalogueServiceProbeResult,
        XmlContentCheckResult,
        ExceptionResponseCheckResult):

    class Meta(CatalogueServiceProbeResult.Meta):
        # Inheritate meta
        pass


class Probe(models.Model):
    """Baseclass of a probe which validates one request of a service.

    Concrete probes define the request to send and the checks to apply on the
    response. The result of a probe is stored in the `result_model`.
    """

    timeout = models.IntegerField(
        default=30,
        blank=True,
    )

    check_response_does_not_contain = models.CharField(
        max_length=256,
        default="ExceptionReport>,ServiceException>",
        blank=True,
        verbose_name=_("Check response does not contain"),
        help_text=_(
            "comma seperated search strings like: ExceptionReport>,ServiceException>")
    )

    #: model which stores the result of this kind of probe
    result_model = None

    class Meta:
        abstract = True

    def build_request(self, client) -> Request:
        """Build the request which is send to the monitored service."""
        raise NotImplementedError

    def run_response_checks(self, response: Response) -> None:
        """Apply the configured checks on the response of the probe."""
        raise NotImplementedError

    #: the amount of characters of a failed response body which are kept as
    #: the detail of the failure; an inspector reads an excerpt, the whole
    #: body belongs to the artifact when it is stored as one
    ERROR_DETAIL_MAX_LENGTH = 2048

    def store_response_artifact(self, result: ProbeResult, response: Response) -> None:
        """Keep what the service answered, as far as it is safe to keep.

        The size and the content type of the response are always recorded -
        they answer why a body was not kept. The body itself is stored only
        for the content types the inspector renders and only up to the
        configured maximum size; the stored bytes are exactly the bytes the
        probe saw, so an inspector looks at the execution and not at whatever
        the service answers today (#682).
        """
        body = response.content or b""
        result.response_size = len(body)
        content_type = response.headers.get(
            "Content-Type", "").split(";")[0].strip().lower()
        result.response_content_type = content_type
        if not body or content_type not in STORED_RESPONSE_CONTENT_TYPES:
            return
        if len(body) > settings.MONITORING_PROBE_RESPONSE_MAX_SIZE:
            return
        result.response_body = ContentFile(body, name="response")

    def check_does_not_contain(self, response: Response):
        self.result.check_response_does_not_contain_message = ""
        for string in self.check_response_does_not_contain.split(','):
            if response.text.find(string) > -1:
                self.result.check_response_does_not_contain_success = False
                self.result.check_response_does_not_contain_message += f"{string} is part of the response. "  # noqa

        if self.result.check_response_does_not_contain_success is not False:
            self.result.check_response_does_not_contain_success = True
            self.result.check_response_does_not_contain_message = "OK"

    def check_does_contain(self, response: Response):
        self.result.check_response_does_contain_message = ""
        for string in self.check_response_does_contain.split(','):
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

    def run_checks(self, run: MonitoringRun, *args, **kwargs) -> ProbeResult:
        """Execute the probe and store the outcome in the result model.

        Args:
            run (MonitoringRun): the monitoring run which belongs to the setting
                of this probe

        Returns:
            ProbeResult: the result of this probe
        """

        result = self.result_model.objects.create(
            run=run,
        )
        self.result = result
        self.save()
        try:
            client = self.setting.service.client
            request = self.build_request(client)
            result.monitored_uri = request.url

            response = client.send_request(
                request=request, timeout=self.timeout)

            if response.status_code != 200:
                # an excerpt of the body which refused: the full body is only
                # kept where it is safe to keep it, see store_response_artifact
                result.error_detail = (
                    (response.text or "")[:self.ERROR_DETAIL_MAX_LENGTH]
                    or None)
            result.status_code = response.status_code

            self.run_response_checks(response=response)

            result.monitored_uri = response.url
            result.request_duration = response.elapsed if response else None
            self.store_response_artifact(result=result, response=response)

        except ConnectTimeout:
            result.request_error = f"The request timed out in {self.timeout} seconds while trying to connect to the remote server."  # noqa
        except ReadTimeout:
            result.request_error = f"The server did not send any data in the allotted amount of time ({self.timeout} seconds)."  # noqa
        except RequestException as exception:
            result.request_error = str(exception)
        finally:
            result.save()
        return result


class CapabilitiesProbe(Probe):
    """Probe which requests and validates the capabilities of a service."""

    check_response_is_valid_xml = BooleanField(default=True)

    check_response_does_contain = CharField(
        max_length=256,
        default="Title>,Abstract>",
        blank=True,
        verbose_name=_("Check response does contain"),
        help_text=_("comma seperated search strings like: Title>,Abstract>")
    )

    class Meta:
        abstract = True

    def build_request(self, client) -> Request:
        return client.get_capabilities_request()

    def run_response_checks(self, response: Response) -> None:
        if self.check_response_is_valid_xml:
            self.check_is_valid_xml(response=response)

        if self.check_response_does_contain:
            self.check_does_contain(response=response)

        if self.check_response_does_not_contain:
            self.check_does_not_contain(response=response)


class WebMapServiceProbe(Probe):
    setting = models.ForeignKey(
        to=WebMapServiceMonitoringSetting,
        on_delete=models.CASCADE,
        related_name='%(app_label)s_%(class)ss',
        related_query_name='%(app_label)s_%(class)s',
        verbose_name=_('Setting'),
        help_text=_('The related setting object')
    )

    class Meta:
        abstract = True


class GetCapabilitiesProbe(WebMapServiceProbe, CapabilitiesProbe):
    result_model = GetCapabilitiesProbeResult


class GetMapProbe(WebMapServiceProbe):
    layers = models.ManyToManyField(to=Layer)
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

    result_model = GetMapProbeResult

    def run_response_checks(self, response: Response) -> None:
        if self.check_response_is_image:
            self.check_is_image(response=response)

        if self.check_response_does_not_contain:
            self.check_does_not_contain(response=response)

    def build_request(self, client) -> Request:
        layers: list[Layer] = self.layers.with_inherited_attributes_cte()
        bbox: Polygon = layers[0].bbox_lat_lon_inherited
        if client.service_version == "1.3.0":
            bbox = adjust_axis_order(bbox)

        return client.get_map_request(
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


class WebFeatureServiceProbe(Probe):
    setting = models.ForeignKey(
        to=WebFeatureServiceMonitoringSetting,
        on_delete=models.CASCADE,
        related_name='%(app_label)s_%(class)ss',
        related_query_name='%(app_label)s_%(class)s',
        verbose_name=_('Setting'),
        help_text=_('The related setting object')
    )

    class Meta:
        abstract = True


class WebFeatureServiceGetCapabilitiesProbe(
        WebFeatureServiceProbe, CapabilitiesProbe):
    result_model = WebFeatureServiceGetCapabilitiesProbeResult


class WebFeatureServiceGetFeatureProbe(WebFeatureServiceProbe):
    """Probe which requests features of the monitored web feature service."""

    feature_types = models.ManyToManyField(to=FeatureType)

    max_features = models.IntegerField(
        default=1,
        verbose_name=_("max features"),
        help_text=_(
            "the maximum number of features the request shall return"))

    reference_system = models.ForeignKey(
        to=ReferenceSystem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    check_response_is_valid_xml = BooleanField(default=True)

    check_response_does_contain = CharField(
        max_length=256,
        default="FeatureCollection",
        blank=True,
        verbose_name=_("Check response does contain"),
        help_text=_("comma seperated search strings like: FeatureCollection")
    )

    result_model = WebFeatureServiceGetFeatureProbeResult

    def run_response_checks(self, response: Response) -> None:
        if self.check_response_is_valid_xml:
            self.check_is_valid_xml(response=response)

        if self.check_response_does_contain:
            self.check_does_contain(response=response)

        if self.check_response_does_not_contain:
            self.check_does_not_contain(response=response)

    def build_request(self, client) -> Request:
        return client.get_feature_kvp_request(
            type_names=[
                feature_type.identifier
                for feature_type in self.feature_types.all()],
            max_features=self.max_features,
            srs_name=str(self.reference_system) if self.reference_system else None,
        )


class CatalogueServiceProbe(Probe):
    setting = models.ForeignKey(
        to=CatalogueServiceMonitoringSetting,
        on_delete=models.CASCADE,
        related_name='%(app_label)s_%(class)ss',
        related_query_name='%(app_label)s_%(class)s',
        verbose_name=_('Setting'),
        help_text=_('The related setting object')
    )

    class Meta:
        abstract = True


class CatalogueServiceGetCapabilitiesProbe(
        CatalogueServiceProbe, CapabilitiesProbe):
    result_model = CatalogueServiceGetCapabilitiesProbeResult


class CatalogueServiceGetRecordsProbe(CatalogueServiceProbe):
    """Probe which requests records of the monitored catalogue service."""

    type_names = models.CharField(
        max_length=256,
        default="gmd:MD_Metadata",
        blank=True,
        verbose_name=_("type names"),
        help_text=_(
            "the type names of the records which shall be requested"))

    result_type = models.CharField(
        max_length=100,
        default="results",
        verbose_name=_("result type"),
        help_text=_("the result type of the get records request"))

    element_set_name = models.CharField(
        max_length=100,
        default="summary",
        verbose_name=_("element set name"),
        help_text=_(
            "the element set name of the records which shall be returned"))

    max_records = models.IntegerField(
        default=1,
        verbose_name=_("max records"),
        help_text=_(
            "the maximum number of records the request shall return"))

    check_response_is_valid_xml = BooleanField(default=True)

    check_response_does_contain = CharField(
        max_length=256,
        default="GetRecordsResponse",
        blank=True,
        verbose_name=_("Check response does contain"),
        help_text=_("comma seperated search strings like: GetRecordsResponse")
    )

    result_model = CatalogueServiceGetRecordsProbeResult

    def run_response_checks(self, response: Response) -> None:
        if self.check_response_is_valid_xml:
            self.check_is_valid_xml(response=response)

        if self.check_response_does_contain:
            self.check_does_contain(response=response)

        if self.check_response_does_not_contain:
            self.check_does_not_contain(response=response)

    def build_request(self, client) -> Request:
        return client.get_records_request(
            type_names=self.type_names,
            result_type=self.result_type,
            element_set_name=self.element_set_name,
            max_records=self.max_records,
        )


#: every concrete probe result model which can carry a response artifact;
#: the retention sweep walks it and the artifact route answers bodies for it
PROBE_RESULT_MODELS = (
    GetCapabilitiesProbeResult,
    GetMapProbeResult,
    WebFeatureServiceGetCapabilitiesProbeResult,
    WebFeatureServiceGetFeatureProbeResult,
    CatalogueServiceGetCapabilitiesProbeResult,
    CatalogueServiceGetRecordsProbeResult,
)

#: the result models by the lowercased model name which the artifact route
#: addresses them with; the serializers reverse their artifact url through it
PROBE_RESULT_MODELS_BY_NAME = {
    model._meta.model_name: model for model in PROBE_RESULT_MODELS}


def purge_expired_probe_response_artifacts(retention_days=None) -> dict:
    """Takes back the stored probe responses whose retention has passed.

    The rows of the probe results stay: the lists of the monitoring history
    answer their checks and the recorded content type and size of the
    response, only the body and its name in the storage go (#682). A row
    whose file the storage does not hold anymore (#1150) is cleared as well -
    the name of a missing file guards nothing worth keeping. A retention of
    0 keeps every artifact until an operator removes it.
    """
    days = (settings.MONITORING_PROBE_RESPONSE_RETENTION_DAYS
            if retention_days is None else retention_days)
    if days <= 0:
        return {"retention_days": days, "purged": 0}

    cutoff = now() - timedelta(days=days)
    purged = 0
    for result_model in PROBE_RESULT_MODELS:
        named = result_model.objects.exclude(response_body="").exclude(
            response_body=None)
        for result in named.filter(date_created__lt=cutoff):
            try:
                result.response_body.delete(save=False)
            except (FileNotFoundError, OSError):
                pass  # the storage does not hold it - which is what to clear
            result.response_body = None
            result.save(update_fields=["response_body"])
            purged += 1
    return {"retention_days": days, "purged": purged}
