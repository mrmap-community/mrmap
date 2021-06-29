import os

from django.contrib.gis.db import models
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db.models import Q, F
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from requests import Response

from main.models import CommonInfo, GenericModelMixin
from resourceNew.enums.service import OGCOperationEnum, AuthTypeEnum, OGCServiceEnum
from MrMap.validators import geometry_is_empty, validate_get_capablities_uri
from resourceNew.managers.security import ProxyLogManager
from resourceNew.models import Service, Layer, FeatureType
from cryptography.fernet import Fernet

from service.settings import EXTERNAL_AUTHENTICATION_FILEPATH


class ExternalAuthentication(GenericModelMixin, CommonInfo):
    secured_service = models.OneToOneField(to=Service,
                                           on_delete=models.CASCADE,
                                           related_name="external_authentication",
                                           related_query_name="external_authentication",
                                           verbose_name=_("secured service"),
                                           help_text=_("the service which uses this credentials."))
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

    class Meta:
        """
        # todo:
        constraints = [
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_empty_fields",
                check=Q(username=None) | Q(password=None) | Q(auth_type=None)
            )
        ]"""

    def __str__(self):
        return f"External authentication for {self.secured_service.__str__()}"

    def clean(self):
        """ Additional clean method. Cause we configured some fields to allow blank posting in model forms, such as used
        in the :class:`resourceNew.views.service.ServiceUpdateView` to support adding optional
        :class:`resourceNew.models.security.ExternalAuthentication` instances for a given
        :class:`resourceNew.models.service.Service`, we need to check in this custom clean() if there are empty posted
        fields.

        :raises: :class:`django.core.exceptions.ValidationError`: If username, password or auth_type where empty.
        """
        errors = {}
        # cause we support blank fields to support empty inline formset posting, we need to validate the blank fields
        # here
        if self.username or self.password or self.auth_type:
            if not self.username:
                errors.update({"username": _("username can't be leave empty.")})
            if not self.password:
                errors.update({"password": _("password can't be leave empty.")})
            if not self.auth_type:
                errors.update({"auth_type": _("auth type can't be leave empty.")})
        if errors:
            raise ValidationError(errors)

    @property
    def filepath(self):
        """the path of the key file for this external authentication"""
        return f"{EXTERNAL_AUTHENTICATION_FILEPATH}/service_{self.secured_service_id}.key"

    @property
    def key(self):
        """the key to decrypt this external authentication"""
        file = open(self.filepath, "rb")
        return file.read()

    def write_key_to_file(self, force_return: bool = False):
        """Generate and store a key for this external authentication to
        :attr:`.ExternalAuthentication.filepath`
        """
        key = Fernet.generate_key()
        file = None
        try:
            file = open(self.filepath, "wb")  # open file in write-bytes mode
            file.write(key)
            return key, True
        except FileNotFoundError:
            # directory might not exist yet
            tmp = self.filepath.split("/")
            del tmp[-1]
            dir_path = "/".join(tmp)
            os.mkdir(dir_path)

            # try again
            if force_return:
                raise FileNotFoundError("can't generate the key file for external authentication.")
            else:
                return self.write_key_to_file(force_return=True)
        finally:
            if file:
                file.close()

    def save(self, register_service=False, *args, **kwargs):
        if self._state.adding:
            key, success = self.write_key_to_file()
            if success:
                self.__encrypt()
                super().save(*args, **kwargs)
        else:
            # We check if password has become changed. If not we need to get the old password from the ciphered password
            # by set the decrypted password to the current ExternalAuthentication object.
            old_self = ExternalAuthentication.objects.get(pk=self.pk)
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
        try:
            os.remove(self.filepath)
        except FileNotFoundError:
            pass
        finally:
            super().delete(*args, **kwargs)

    def __encrypt(self):
        """ Encrypt the login credentials using the stored key

        Returns:
            None
        """
        cipher_suite = Fernet(self.key)
        self.username = cipher_suite.encrypt(self.username.encode("ascii")).decode("ascii")
        self.password = cipher_suite.encrypt(self.password.encode("ascii")).decode("ascii")

    def decrypt_password(self):
        cipher_suite = Fernet(self.key)
        return cipher_suite.decrypt(self.password.encode("ascii")).decode("ascii")

    def decrypt(self, ):
        """ Decrypt the login credentials using the stored key

        Returns:
            username, password (tuple): the username and password in clear text
        """
        cipher_suite = Fernet(self.key)
        password = cipher_suite.decrypt(self.password.encode("ascii")).decode("ascii")
        username = cipher_suite.decrypt(self.username.encode("ascii")).decode("ascii")
        return username, password


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
    """ A AllowedOperation represents a security configuration for a given :class:`resourceNew.models.service.Service`.

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
        * a set of :class:`resourceNew.models.security.ServiceAccessGroup`
        * to access a set of :class:`resourceNew.models.service.Layer` or :class:`resourceNew.models.FeatureType`
        * for one configured :class:`resourceNew.models.service.Service`
        * limited by the configured :class:`resourceNew.models.security.OGCOperation`
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
    secured_service = models.ForeignKey(to=Service,
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
                                                   verbose_name=_("secured feature types"),
                                                   help_text=_("Select one or more feature types."))
    description = models.CharField(max_length=512,
                                   verbose_name=_("description"),
                                   help_text=_("a short description what this allowed operation controls."))

    def __str__(self):
        return f"AllowedOperation ({self.pk}) for service {self.secured_service}"

    def save(self, *args, **kwargs):
        """Custom save function to update related :class:`resourceNew.models.security.ProxySetting` instance.
        IF there is a related :class:`resourceNew.models.security.ProxySetting` instance, the
        :attr:`.ProxySetting.camouflage` attribute is updated to the value ``True``
        ELSE we create a new :class:`resourceNew.models.security.ProxySetting` instance with the initial
        ``camouflage=True`` attribute.

        """
        super().save(*args, **kwargs)
        # Note: only use update if ProxySetting has NOT a custom save function. .update() is a bulk function which
        # does NOT call save() or triggers signals
        proxy_setting = ProxySetting.objects.filter(secured_service=self.secured_service).update(camouflage=True)
        if proxy_setting == 0:
            ProxySetting.objects.create(secured_service=self.secured_service,
                                        camouflage=True)


class ProxySetting(GenericModelMixin, CommonInfo):
    secured_service = models.OneToOneField(to=Service,
                                           on_delete=models.CASCADE,
                                           related_name="proxy_setting",
                                           related_query_name="proxy_setting",
                                           verbose_name=_("secured service"),
                                           help_text=_("the configured service for this proxy settings"))
    camouflage = models.BooleanField(default=False,
                                     verbose_name=_("camouflage"),
                                     help_text=_("if true, all related xml documents are secured, by replace all "
                                                 "hostname/internet addresses of the related service by the hostname of"
                                                 " the current mr. map instance."))
    log_response = models.BooleanField(default=False,
                                       verbose_name=_("log response", ),
                                       help_text=_("if true, all responses of the related service will be logged."))

    class Meta:
        constraints = [
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_log_response_without_camouflage",
                check=Q(camouflage=True, log_response=True) |
                      Q(camouflage=True, log_response=False) |
                      Q(camouflage=False, log_response=False)
            ),
        ]

    def clean(self):
        if self.log_response and not self.camouflage:
            raise ValidationError({"camouflage": _("log response without active camouflage is not supported.")})
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


class ProxyLog(GenericModelMixin, CommonInfo):
    service = models.ForeignKey(to=Service,
                                on_delete=models.PROTECT,
                                related_name="proxy_logs",
                                related_query_name="proxy_log")
    user = models.ForeignKey(to=settings.AUTH_USER_MODEL,
                             on_delete=models.PROTECT,
                             related_name="proxy_logs",
                             related_query_name="proxy_log")
    operation = models.CharField(max_length=100,
                                 choices=OGCOperationEnum.as_choices())
    uri = models.URLField(max_length=4096)
    query_params = models.JSONField(default=dict)
    post_body = models.JSONField(default=dict)
    timestamp = models.DateTimeField(auto_now_add=True)
    response_wfs_num_features = models.IntegerField(null=True,
                                                    blank=True)
    response_wms_megapixel = models.FloatField(null=True,
                                               blank=True)

    response_logging = ProxyLogManager()

    class Meta:
        ordering = ["-timestamp"]

    def log_response(self, response: Response):
        if self.service.is_service_type(OGCServiceEnum.WMS):
            pass
        elif self.service.is_service_type(OGCServiceEnum.WFS):
            pass

    def log_wms_response(self, response: Response):
        pass
