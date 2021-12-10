import time

from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.gis.db import models
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from extras.models import CommonInfo, GenericModelMixin
from MrMap.validators import geometry_is_empty, validate_get_capablities_uri
from PIL import Image
from registry.enums.security import EntityUnits
from registry.enums.service import (AuthTypeEnum, OGCOperationEnum,
                                    OGCServiceEnum)
from registry.managers.security import (AllowedOperationManager,
                                        AnalyzedResponseLogTableManager)
from registry.models.service import (FeatureType, Layer, OgcService,
                                     WebFeatureService, WebMapService)
from registry.tasks.security import async_analyze_log
from requests.auth import HTTPDigestAuth


def key_file_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/ext_auth_keys/service_<id>/<filename>
    return 'ext_auth_keys/service_{0}/{1}'.format(instance.secured_service_id, filename)


class ServiceAuthentication(GenericModelMixin, CommonInfo):
    username = models.CharField(max_length=255,
                                blank=True,  # to support empty inline formset posting
                                verbose_name=_("username"),
                                help_text=_("the username used for the authentication."))
    password = models.CharField(max_length=500,
                                blank=True,  # to support empty inline formset posting
                                verbose_name=_("password"),
                                help_text=_("the password used for the authentication."))
    auth_type = models.CharField(max_length=100,
                                 blank=True,  # to support empty inline formset posting
                                 choices=AuthTypeEnum.as_choices(),
                                 verbose_name=_("authentication type"),
                                 help_text=_("kind of authentication mechanism shall used."))
    test_url = models.URLField(validators=[validate_get_capablities_uri],
                               editable=False,
                               null=True,
                               verbose_name=_("Service url"),
                               help_text=_("this shall be the full get capabilities request url."))
    key_file = models.FileField(upload_to=key_file_path,
                                editable=False,
                                max_length=1024)
    service = models.OneToOneField(to=OgcService,
                                   verbose_name=_("web map service"),
                                   help_text=_(
                                       "the optional authentication type and credentials to request the service."),
                                   related_query_name="auth",
                                   related_name="auth",
                                   on_delete=models.CASCADE,
                                   blank=True)

    def save(self, *args, **kwargs):
        if self._state.adding and not self.key_file:
            key = Fernet.generate_key()
            self.key_file.save(name=f'{time.strftime("%Y_%m_%d-%I_%M_%S_%p")}.key',
                               content=ContentFile(key),
                               save=False)
            self.__encrypt()
            super().save(*args, **kwargs)
        else:
            # We check if password has become changed. If not we need to get the old password from the ciphered password
            # by set the decrypted password to the current ServiceAuthentication object.
            old_self = ServiceAuthentication.objects.get(pk=self.pk)
            if old_self.password == self.password:
                password = self.decrypt_password()
                self.password = password
            self.__encrypt()
            super().save(*args, *kwargs)

    def delete(self, *args, **kwargs):
        """ Overwrites default delete function

        Removes local stored file if it exists!

        Args;
            using:
            keep_parents:
        Returns:
            the deleted object
        """
        self.key_file.delete(save=False)
        return super().delete(*args, **kwargs)

    @property
    def key(self):
        try:
            return self.key_file.open().read()
        except FileNotFoundError:
            return None

    def __encrypt(self):
        """ Encrypt the login credentials using the stored key

        Returns:
            None
        """
        cipher_suite = Fernet(self.key)
        self.username = cipher_suite.encrypt(
            self.username.encode("ascii")).decode("ascii")
        self.password = cipher_suite.encrypt(
            self.password.encode("ascii")).decode("ascii")

    def decrypt_password(self):
        cipher_suite = Fernet(self.key)
        return cipher_suite.decrypt(self.password.encode("ascii")).decode("ascii")

    def decrypt(self):
        """ Decrypt the login credentials using the stored key

        Returns:
            username, password (tuple): the username and password in clear text
        """
        if self.key:
            cipher_suite = Fernet(self.key)
            password = cipher_suite.decrypt(
                self.password.encode("ascii")).decode("ascii")
            username = cipher_suite.decrypt(
                self.username.encode("ascii")).decode("ascii")
            return username, password
        return None, None

    def get_auth_for_request(self):
        username, password = self.decrypt()
        if self.auth_type == AuthTypeEnum.BASIC.value:
            auth = (username, password)
        elif self.auth_type == AuthTypeEnum.DIGEST.value:
            auth = HTTPDigestAuth(username=username,
                                  password=password)
        else:
            auth = None
        return auth


class OGCOperation(models.Model):
    operation = models.CharField(primary_key=True,
                                 max_length=30,
                                 choices=OGCOperationEnum.as_choices())

    def __str__(self):
        return self.operation


class AllowedOperationGroupRelation(models.Model):
    """ Custom M2M relation table model to protect referenced ServiceAccessGroup from deleting if they are referenced.

    """
    service_access_group = models.ForeignKey(to="ServiceAccessGroup",
                                             on_delete=models.PROTECT)
    allowed_operation = models.ForeignKey(to="AllowedOperation",
                                          on_delete=models.CASCADE)

    def __str__(self):
        return self.allowed_operation.__str__()


class ServiceAccessGroup(GenericModelMixin, Group, CommonInfo):
    description = models.CharField(max_length=512,
                                   verbose_name=_("description"),
                                   help_text=_("a short description what this group is for."))


class AllowedOperation(GenericModelMixin, CommonInfo):
    """ A AllowedOperation represents a security configuration for a given :class:`registry.models.service.Service`.

    :attr operations:  :class:`django.db.models.fields.related.ManyToManyField` field to configure allowed OGC
                       operations.
    :attr allowed_groups: :class:`django.db.models.fields.related.ManyToManyField` field to configure allowed groups to
                          access the configured service.
    :attr allowed_area: (optional) :class:`django.contrib.gis.db.models.fields.MultiPolygonField` to configure an
                        allowed area. If set, only the configured area is allowed to request.
    :attr secured_service: :class:`django.db.models.fields.related.ForeignKey` field to configure the secured service.
    :attr secured_layers: :class:`django.db.models.fields.related.ManyToManyField` field to configure all secured
                          layers.
    :attr secured_feature_types: :class:`django.db.models.fields.related.ManyToManyField` field to configure all secured
                          feature types.
    :attr description: :class:`django.db.models.fields.CharField` short description for better administrating different
                       :class:`~AllowedOperation` instances.

    One allowed operation is a configuration to allow
        * a set of :class:`registry.models.security.ServiceAccessGroup`
        * to access a set of :class:`registry.models.service.Layer` or :class:`registry.models.FeatureType`
        * for one configured :class:`registry.models.service.Service`
        * limited by the configured :class:`registry.models.security.OGCOperation`
        * and (optional) limited by a configured :class:`django.contrib.gis.geos.MultiPolygon`

    .. warning::
        IF there are two :class:`~AllowedOperation` instances for the same set of ``operations`` and ``allowed_groups``
        and one has no allowed area configured the one with ``allowed_area=None`` allows all areas.

    """
    operations = models.ManyToManyField(to=OGCOperation,
                                        related_name="allowed_operations",
                                        related_query_name="allowed_operation")
    # todo: to=Group? then we can add organizations
    allowed_groups = models.ManyToManyField(to=ServiceAccessGroup,
                                            through=AllowedOperationGroupRelation,
                                            related_name="allowed_operations",
                                            related_query_name="allowed_operation")
    allowed_area = models.MultiPolygonField(null=True,
                                            blank=True,
                                            validators=[geometry_is_empty])
    secured_wms = models.ForeignKey(to=WebMapService,
                                    null=True,
                                    blank=True,
                                    on_delete=models.CASCADE,
                                    related_name="allowed_operations",
                                    related_query_name="allowed_operation",
                                    verbose_name=_("secured service"),
                                    help_text=_("the service where some layers or feature types are secured of."))
    secured_wfs = models.ForeignKey(to=WebFeatureService,
                                    null=True,
                                    blank=True,
                                    on_delete=models.CASCADE,
                                    related_name="allowed_operations",
                                    related_query_name="allowed_operation",
                                    verbose_name=_("secured service"),
                                    help_text=_("the service where some layers or feature types are secured of."))
    secured_layers = models.ManyToManyField(to=Layer,
                                            related_name="allowed_operations",
                                            related_query_name="allowed_operation",
                                            verbose_name=_("secured layers"),
                                            help_text=_("Select one or more layers. Note that all sub layers of a "
                                                        "selected layer will also be secured."), )
    secured_feature_types = models.ManyToManyField(to=FeatureType,
                                                   related_name="allowed_operations",
                                                   related_query_name="allowed_operation",
                                                   verbose_name=_(
                                                       "secured feature types"),
                                                   help_text=_("Select one or more feature types."))
    description = models.CharField(max_length=512,
                                   verbose_name=_("description"),
                                   help_text=_("a short description what this allowed operation controls."))

    objects = AllowedOperationManager()

    def __str__(self):
        return f"AllowedOperation ({self.pk}) for service {self.secured_wms|self.secured_wfs}"

    def save(self, *args, **kwargs):
        """Custom save function to update related :class:`registry.models.security.ProxySetting` instance.
        IF there is a related :class:`registry.models.security.ProxySetting` instance, the
        :attr:`.ProxySetting.camouflage` attribute is updated to the value ``True``
        ELSE we create a new :class:`registry.models.security.ProxySetting` instance with the initial
        ``camouflage=True`` attribute.

        """
        super().save(*args, **kwargs)
        # Note: only use update if ProxySetting has NOT a custom save function. .update() is a bulk function which
        # does NOT call save() or triggers signals
        if self.secured_wms:
            proxy_setting = ProxySetting.objects.filter(
                secured_wms=self.secured_wms).update(camouflage=True)
            if proxy_setting == 0:
                ProxySetting.objects.create(secured_wms=self.secured_wms,
                                            camouflage=True)
        if self.secured_wfs:
            proxy_setting = ProxySetting.objects.filter(
                secured_wfs=self.secured_wfs).update(camouflage=True)
            if proxy_setting == 0:
                ProxySetting.objects.create(secured_wfs=self.secured_wfs,
                                            camouflage=True)


class ProxySetting(GenericModelMixin, CommonInfo):
    camouflage = models.BooleanField(default=False,
                                     verbose_name=_("camouflage"),
                                     help_text=_("if true, all related xml documents are secured, by replace all "
                                                 "hostname/internet addresses of the related service by the hostname of"
                                                 " the current mr. map instance."))
    log_response = models.BooleanField(default=False,
                                       verbose_name=_("log response", ),
                                       help_text=_("if true, all responses of the related service will be logged."))
    wms = models.OneToOneField(to=WebMapService,
                               on_delete=models.CASCADE,
                               related_name="web_map_service",
                               related_query_name="web_map_service",
                               verbose_name=_("proxy settings"),
                               help_text=_("the security proxy settings for this service."))
    wfs = models.OneToOneField(to=WebFeatureService,
                               on_delete=models.CASCADE,
                               related_name="web_feature_service",
                               related_query_name="web_feature_service",
                               verbose_name=_("proxy settings"),
                               help_text=_("the security proxy settings for this service."))

    class Meta:
        constraints = [
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_log_response_without_camouflage",
                check=Q(camouflage=True, log_response=True) | Q(
                    camouflage=True, log_response=False) | Q(camouflage=False, log_response=False)
            ),
        ]

    def clean(self):
        if self.log_response and not self.camouflage:
            raise ValidationError(
                {"camouflage": _("log response without active camouflage is not supported.")})
        if not self.camouflage and self.secured_service.allowed_operations.exists():
            url = f"{AllowedOperation.get_table_url()}?id__in="
            for pk in self.secured_service.allowed_operations.all().values_list("pk", flat=True):
                if url.endswith('?id__in='):
                    url += f'{pk}'
                else:
                    url += f',{pk}'
            raise ValidationError(
                {"camouflage": format_html(_("There are configured allowed operation objects. Camouflage can not"
                                             " be disabled. See all allowed operations <a href=%(url)s>here</a>")
                                           % {"url": url})
                 }
            )


def request_body_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/security_proxy/logs/requests/service_<id>/<username>/<filename>
    return 'security_proxy/logs/requests/service_{0}/{1}/{2}'.format(instance.service.id,
                                                                     instance.user.username,
                                                                     filename)


class HttpRequestLog(models.Model):
    timestamp = models.DateTimeField()
    elapsed = models.DurationField()
    method = models.CharField(max_length=20)
    url = models.URLField(max_length=4096)
    body = models.FileField(upload_to=request_body_path, max_length=1024)
    headers = models.JSONField(default=dict)
    user = models.ForeignKey(to=settings.AUTH_USER_MODEL,
                             on_delete=models.PROTECT,
                             related_name="http_request_logs",
                             related_query_name="http_request_log")
    wms = models.ForeignKey(to=WebMapService,
                            on_delete=models.PROTECT,
                            related_name="http_request_logs",
                            related_query_name="http_request_log")
    wfs = models.ForeignKey(to=WebFeatureService,
                            on_delete=models.PROTECT,
                            related_name="http_request_logs",
                            related_query_name="http_request_log")

    def delete(self, *args, **kwargs):
        self.body.delete(save=False)
        d = super().delete(*args, **kwargs)
        return d


def response_content_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/security_proxy/logs/responses/service_<id>/<username>/<filename>
    return 'security_proxy/logs/responses/service_{0}/{1}/{2}'.format(instance.request.service.id,
                                                                      instance.request.user.username,
                                                                      filename)


class HttpResponseLog(models.Model):
    status_code = models.IntegerField(default=0)
    reason = models.CharField(max_length=50)
    elapsed = models.DurationField()
    headers = models.JSONField(default=dict)
    url = models.URLField(max_length=4096)
    content = models.FileField(
        upload_to=response_content_path, max_length=1024)
    request = models.OneToOneField(to=HttpRequestLog,
                                   on_delete=models.PROTECT,
                                   related_name="response",
                                   related_query_name="response")

    def save(self, *args, **kwargs):
        adding = False
        if self._state.adding:
            adding = True
        super().save(*args, **kwargs)
        if adding:
            transaction.on_commit(lambda: async_analyze_log.apply_async(
                args=(self.pk, ),
                kwargs={'created_by_user_pk': get_user_model().objects.values_list("pk", flat=True).get(username="system"),
                        'owner_pk': self.request.service.owner_id}))

    def delete(self, *args, **kwargs):
        self.content.delete(save=False)
        return super().delete(*args, **kwargs)


class AnalyzedResponseLog(GenericModelMixin, CommonInfo):
    response = models.OneToOneField(to=HttpResponseLog,
                                    on_delete=models.PROTECT,
                                    related_name="analyzed_response",
                                    related_query_name="analyzed_response")
    entity_count = models.FloatField(help_text="Stores the response entity count. "
                                               "For WMS this will be the indiscreet number of megapixels that are "
                                               "returned by the service. "
                                               "For WFS this will be discrete number of feature types that are returned"
                                               " by the service.")
    entity_total_count = models.FloatField(help_text="Stores the response entity total count. "
                                                     "For WMS this will be the indiscreet number of megapixels that are"
                                                     " returned by the service. "
                                                     "For WFS this will be discrete number of feature types that are "
                                                     "returned by the service.")
    entity_unit = models.CharField(max_length=5,
                                   choices=EntityUnits.as_choices(
                                       drop_empty_choice=True),
                                   help_text="The unit in which the entity count is stored.")
    objects = AnalyzedResponseLogTableManager()

    def analyze_response(self):
        if self.response.request.service.is_service_type(OGCServiceEnum.WMS):
            self._analyze_wms_response()
        elif self.response.request.service.is_service_type(OGCServiceEnum.WFS):
            self._analyze_wfs_response()

    def _analyze_wms_response(self):
        img = Image.open(self.response.content.open(mode='rb'))
        tmp = Image.new("RGBA", img.size, (255, 255, 255, 255))
        tmp.paste(img)
        img = tmp

        # Get alpha channel pixel values as list
        all_pixel_vals = list(img.getdata(3))
        # Count all alpha pixel (value == 0)
        num_alpha_pixels = all_pixel_vals.count(0)

        # Compute data pixels
        self.entity_count = round(
            (len(all_pixel_vals) - num_alpha_pixels) / 1000000, 4)
        # Compute full image pixel count (including transparent pixels)
        self.entity_total_count = round((img.height * img.width) / 1000000, 4)
        self.entity_unit = EntityUnits.MEGA_PIXEL.value

        # TODO: implement GetFeatureInfo analyzing

    def _analyze_wfs_response(self):
        # TODO: implement csv analyzing
        # TODO: implement kml analyzing
        # TODO: implement geojson analyzing
        # TODO: implement xml/gml analyzing
        pass
