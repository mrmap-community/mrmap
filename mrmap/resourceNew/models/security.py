from django.contrib.gis.db import models
from django.contrib.auth.models import Group
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from main.models import CommonInfo
from resourceNew.enums.service import OGCOperationEnum
from MrMap.validators import geometry_is_empty
from resourceNew.models import Service, Layer, FeatureType


class OGCOperation(models.Model):
    operation = models.CharField(primary_key=True, max_length=255, choices=OGCOperationEnum.as_choices())

    def __str__(self):
        return self.operation


class ServiceAccessGroup(Group, CommonInfo):
    pass


class AllowedOperation(CommonInfo):
    """ Configures the operation(s) which allows one or more groups to access a :class:`service.models.Resource`.

    id: the id of the ``SecuredOperation`` object
    operations: a list of allowed ``OGCOperation`` objects
    allowed_groups: a list of groups which are allowed to perform the operations from the ``operations`` field on all
                    ``Metadata`` objects from the secured_metadata list.
    root_metadata: holds the root node of the secured_metadata set. With that we solve another problem. The deletion
                   trigger, if the `Metadata` object is deleted. Then the `SecuredOperation` will be also deleted.
    secured_metadata: a list of all `Metadata`` objects for which the restrictions, based on ``operations`` list,
                      applies to.
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
                                            blank=True,
                                            related_name="allowed_operations",
                                            related_query_name="allowed_operation",
                                            verbose_name=_("secured layers"),
                                            help_text=_("a list of layers which are secured by this allowed "
                                                        "operation object"))
    secured_feature_types = models.ManyToManyField(to=FeatureType,
                                                   blank=True,
                                                   related_name="allowed_operations",
                                                   related_query_name="allowed_operation",
                                                   verbose_name=_("secured feature types"),
                                                   help_text=_("a list of feature types which are secured by this "
                                                               "allowed operation object"))


class ProxySettings(CommonInfo):
    configured_service = models.OneToOneField(to=Service,
                                              on_delete=models.CASCADE,
                                              related_name="proxy_settings",
                                              related_query_name="proxy_setting",
                                              verbose_name=_("configured service"),
                                              help_text=_("the configured service for this proxy settings"))
    camouflage = models.BooleanField(default=False,
                                     verbose_name=_("camouflage"),
                                     help_text=_("if true, all related xml documents are secured, by replace all "
                                                 "hostname/internet addresses of the related service by the hostname of"
                                                 " the current mr. map instance."))
    log_response = models.BooleanField(default=False,
                                       verbose_name=_("log response",),
                                       help_text=_("if true, all responses of the related service will be logged."))


class ProxyLog(CommonInfo):
    service = models.ForeignKey(to=Service,
                                on_delete=models.CASCADE)
    user = models.ForeignKey(to=settings.AUTH_USER_MODEL,
                             on_delete=models.CASCADE)
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
