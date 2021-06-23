import os

from django.contrib.gis.db import models
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from main.models import CommonInfo, GenericModelMixin
from resourceNew.enums.service import OGCOperationEnum, AuthTypeEnum
from MrMap.validators import geometry_is_empty, validate_get_capablities_uri
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
        return f"{EXTERNAL_AUTHENTICATION_FILEPATH}/service_{self.secured_service_id}.key"

    @property
    def key(self):
        file = open(self.filepath, "rb")
        return file.read()

    def write_key_to_file(self, force_return: bool = False):
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
        key, success = self.write_key_to_file()
        if success:
            self.__encrypt()
            super().save(*args, **kwargs)
        # todo: handle updates... in forms we should not decrypt the password... just check if password has changed
        #  if so we encrypt it again...

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

    def decrypt(self):
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


class ServiceAccessGroup(Group, CommonInfo):
    description = models.CharField(max_length=512,
                                   verbose_name=_("description"),
                                   help_text=_("a short description what this group is for."))


class AllowedOperation(GenericModelMixin, CommonInfo):
    """ Configures the operation(s) which allows one or more groups to access a :class:`resourceNew.models.Service`.

    operations: a list of allowed ``OGCOperation`` objects
    allowed_groups: a list of groups which are allowed to perform the operations from the ``operations`` field on all
                    ``Service`` objects from the secured_service list.

    """
    operations = models.ManyToManyField(to=OGCOperation,
                                        related_name="allowed_operations",
                                        related_query_name="allowed_operation")
    allowed_groups = models.ManyToManyField(to=ServiceAccessGroup,
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
            )
            # todo: check if secured_service.allowed_operations.exists; if so camouflage shall always be true
        ]

    def clean(self):
        if self.log_response and not self.camouflage:
            raise ValidationError({"camouflage": _("log response without active camouflage is not supported.")})
        if not self.camouflage and self.secured_service.allowed_operations.exists():
            raise ValidationError({"camouflage": _("There are configured allowed operation objects. Camouflage can not"
                                                   "be disabled.")})


class ProxyLog(GenericModelMixin, CommonInfo):
    service = models.ForeignKey(to=Service,
                                on_delete=models.CASCADE,
                                related_name="proxy_logs",
                                related_query_name="proxy_log")
    user = models.ForeignKey(to=settings.AUTH_USER_MODEL,
                             on_delete=models.CASCADE,
                             related_name="proxy_logs",
                             related_query_name="proxy_log")
    operation = models.CharField(max_length=100,
                                 choices=OGCOperationEnum.as_choices())
    uri = models.URLField(max_length=4096)
    post_body = models.TextField(null=True,
                                 blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    response_wfs_num_features = models.IntegerField(null=True,
                                                    blank=True)
    response_wms_megapixel = models.FloatField(null=True,
                                               blank=True)

    class Meta:
        ordering = ["-timestamp"]
