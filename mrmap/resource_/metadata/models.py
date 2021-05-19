from django.db import models
from django.utils.translation import gettext_lazy as _
from uuid import uuid4

from main.models import GenericModelMixin, CommonInfo
from resource_.service_.models import Layer, FeatureType, Service
from structure.models import Contact


class ReferenceSystem(models.Model):
    pass
    # todo


class Dimension(models.Model):
    pass
    # todo


class MetadataContact(Contact):
    name = models.CharField(verbose_name=_("Name"),
                            default="",
                            help_text=_("The name of the organization"),
                            max_length=256)

    class Meta:
        ordering = ["name"]


class Keyword(models.Model):
    keyword = models.CharField(max_length=255,
                               unique=True,
                               db_index=True)

    def __str__(self):
        return self.keyword

    class Meta:
        ordering = ["keyword"]


class MetadataTermsOfUse(models.Model):
    """ Abstract model class to define some fields which describes the terms of use for an metadata

    """
    access_constraints = models.TextField(default='',
                                          help_text=_("Zugriffsbeschränkungen"))
    fees = models.TextField(default="",
                            verbose_name=_("fees"),
                            help_text=_("Kosten Nutzungsbedingungen"))

    class Meta:
        abstract = True


class AbstractMetadata(GenericModelMixin, CommonInfo):
    """ Abstract model class to define general fields for all concrete metadata models. """
    id = models.UUIDField(primary_key=True,
                          default=uuid4,
                          editable=False)
    file_identifier = models.CharField(max_length=1000,
                                       default="",
                                       verbose_name=_("file identifier"),
                                       help_text=_("the parsed file identifier from the iso metadata xml "
                                                   "(gmd:fileIdentifier) OR for example if it is a layer/featuretype"
                                                   "the uuid of the described layer/featuretype shall be used to "
                                                   "identify the generated iso metadata xml."))
    title = models.CharField(max_length=1000,
                             verbose_name=_("title"),
                             help_text=_("a short descriptive title for this metadata"))
    abstract = models.TextField(default='',
                                verbose_name=_("abstract"),
                                help_text=_("brief summary of the content of this metadata"))
    is_broken = models.BooleanField(default=False)
    is_custom = models.BooleanField(default=False)
    hits = models.IntegerField(default=0,
                               verbose_name=_("hits"),
                               help_text=_("how many times this metadata was requested by a client"))
    keywords = models.ManyToManyField(to=Keyword,
                                      related_name="%(class)s_metadata",
                                      related_query_name="%(class)s_metadata",
                                      verbose_name=_("keywords"))

    class Meta:
        abstract = True
        ordering = ["title"]

    def __str__(self):
        return self.title


class ServiceMetadata(MetadataTermsOfUse, AbstractMetadata):
    """ Concrete model class to store the parsed metadata information from the capabilities document of a given layer

        OR to store the information of the parsed iso metadata which was linked in the capabilities document.

    """
    service = models.OneToOneField(to=Service,
                                   on_delete=models.CASCADE,
                                   related_name="service_metadata",
                                   related_query_name="service_metadata",
                                   verbose_name=_("described service"),
                                   help_text=_("choice the service you want to describe with this metadata"))
    # 2048 is the technically specified max length of an url. Some services urls scratches this limit.
    service_metadata_original_uri = models.URLField(max_length=4094,
                                                    blank=True,
                                                    null=True)
    service_contact = models.ForeignKey(to=MetadataContact,
                                        on_delete=models.SET_NULL,
                                        related_name="service_metadata",
                                        related_query_name="service_metadata",
                                        verbose_name=_("contact"),
                                        help_text=_(""))
    metadata_contact = models.ForeignKey(to=MetadataContact,
                                         on_delete=models.SET_NULL,
                                         related_name="service_metadata",
                                         related_query_name="service_metadata",
                                         verbose_name=_("contact"),
                                         help_text=_(""))

    class Meta:
        verbose_name = _("service metadata")
        verbose_name_plural = _("service metadata")


class LayerMetadata(AbstractMetadata):
    """ Concrete model class to store the parsed metadata information from the capabilities document of a given layer.

        **Use cases**
            * 1. The stored information of this class will be transformed to iso metadata xml, which are stored in the
                 :class:`resource.Document` model.
            * 2. Searching for layer information

        # todo: if an instance of this model is created an instance of the model `Document`, who stores the generated
                xml, shall be created.
        # todo: if an instance of this model is updated the related instance of the model `Document` shall be updated.
    """
    layer = models.OneToOneField(to=Layer,
                                 on_delete=models.CASCADE,
                                 related_name="layer_metadata",
                                 related_query_name="layer_metadata",
                                 verbose_name=_("described layer"),
                                 help_text=_("choice the layer you want to describe with this metadata"))
    reference_systems = models.ManyToManyField(to=ReferenceSystem,
                                               related_name="layer_metadata",
                                               related_query_name="layer_metadata",
                                               blank=True,
                                               verbose_name=_("reference systems"))
    dimensions = models.ManyToManyField(to=Dimension,
                                        related_name="layer_metadata",
                                        related_query_name="layer_metadata",
                                        blank=True,
                                        verbose_name=_("dimensions"))

    class Meta:
        verbose_name = _("layer metadata")
        verbose_name_plural = _("layer metadata")


class FeatureTypeMetadata(models.Model):
    feature_type = models.OneToOneField(to=FeatureType,
                                        on_delete=models.CASCADE,
                                        related_name="feature_type_metadata",
                                        related_query_name="feature_type_metadata",
                                        verbose_name=_("described feature type"),
                                        help_text=_("choice the feature type you want to describe with this metadata"))

    class Meta:
        verbose_name = _("feature type metadata")
        verbose_name_plural = _("feature type metadata")


class DatasetMetadata(AbstractMetadata):
    dataset_contact = models.ForeignKey(to=MetadataContact,
                                        on_delete=models.SET_NULL,
                                        related_name="dataset_metadata",
                                        related_query_name="service_metadata",
                                        verbose_name=_("contact"),
                                        help_text=_(""))
    metadata_contact = models.ForeignKey(to=MetadataContact,
                                         on_delete=models.SET_NULL,
                                         related_name="dataset_metadata",
                                         related_query_name="dataset_metadata",
                                         verbose_name=_("contact"),
                                         help_text=_(""))
    origin = models.CharField(max_length=255,
                              choices='upload, capabilities, metador',
                              help_text=_("where this metadata comes from"))
